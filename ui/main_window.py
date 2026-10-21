"""Hauptfenster des LiedManager 2.0.

Das Fenster koordiniert nur noch: Suche, Titel, Audio-Bereich, die Leisten (Aufnahme, Pausentimer)
und die Seitenleiste links mit den Reitern „Kamera“ und „Bilder“. Die eigentliche Arbeit steckt in
``services/`` und den Panel-Klassen (``player_panel``, ``recording_panel``, ``pausentimer_panel``,
``camera_panel``, ``images_panel``).
"""
import logging
import os

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QWidget,
)

from database import DatabaseManager
from paths import resolve_db_path
from version import __version__
from services import atem
from services.playback import AudioPlayback
from services.powerpoint import PausentimerController
from services.recorder import AudioRecorder
from services.settings import app_settings
from ui import theme as t
from ui import widgets as w
from ui.camera_panel import CameraPanel
from ui.gallery_window import GalleryWindow
from ui.images_panel import ImageDropFilter, ImagesPanel
from ui.pausentimer_panel import PausentimerPanel
from ui.player_panel import PlayerPanel
from ui.presentation_window import ImagePresentationWindow
from ui.recording_panel import RecordingPanel
from ui.settings_dialog import SettingsDialog
from ui.side_panel import TAB_IMAGES, SidePanel
from ui.sync_ui import SyncController
from ui.web_remote_ui import RemoteController
from ui.updater_ui import UpdateController

log = logging.getLogger(__name__)

BTN, GAP = t.BTN, t.GAP


class MainWindow(QMainWindow):
    """PyQt6-Hauptfenster des LiedManager 2.0."""

    AUDIO_EMPTY, AUDIO_SELECT, AUDIO_PLAYER, AUDIO_NOTFOUND = range(4)
    AUDIO_NAMES = ("Piano", "GL3")  # Anzeigenamen von Audio 1 und Audio 2

    WIDTH = 420
    PAD_X = 24
    PAD_Y = 20
    PANEL_H = 64
    TITLE_H = 24

    Y_SEARCH = PAD_Y
    Y_TITLE = Y_SEARCH + BTN + GAP
    Y_AUDIO = Y_TITLE + TITLE_H + GAP
    Y_REC = Y_AUDIO + PANEL_H + GAP
    Y_PT = Y_REC + PANEL_H + GAP

    COLLAPSED_HEIGHT = (Y_PT + PausentimerPanel.BORDER + PausentimerPanel.HEADER_HEIGHT
                        + PausentimerPanel.BOTTOM_PAD)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LiedManager {__version__}")
        self.setFixedWidth(SidePanel.WIDTH + self.WIDTH)
        self.setFixedHeight(self.COLLAPSED_HEIGHT)

        self.db = DatabaseManager()
        self.presentation_window = None
        self.gallery_window = None
        self.current_song_summary = None
        self.current_song_full = None
        self._last_searched_query = ""
        self._results = []

        self.playback = AudioPlayback(self)
        self.recorder = AudioRecorder(self)
        self.pausentimer = PausentimerController(self)

        self._build_ui()
        self._connect_services()
        self._refresh_audio_section()
        self.remote = RemoteController(self)     # Steuerung über die eigene Website – startet nur, wenn eingeschaltet
        self.sync = SyncController(self)         # teilt Datenbank-Änderungen über den Sync-Server (im Hintergrund)
        self.updates = UpdateController(self)   # Update-Suche (GitHub-Releases); startet erst auf Anforderung

        # Bilder dürfen überall auf das Programm gezogen werden; die Seitenleiste wechselt dann auf „Bilder“
        self.setAcceptDrops(True)
        self._image_drop_filter = ImageDropFilter(self.add_images, self)

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _build_ui(self):
        # Links die Seitenleiste (Kamera / Bilder), rechts die bisherige Karte mit Suche, Audio und Pausentimer
        self.root = QWidget(self)
        self.root.setObjectName("Root")
        self.root.setStyleSheet(f"QWidget#Root {{ background: {t.CARD_BG}; }}")
        self.setCentralWidget(self.root)

        self.camera_panel = CameraPanel()
        self.images_panel = ImagesPanel()
        self.side_panel = SidePanel(self.camera_panel, self.images_panel)   # wächst mit dem Fenster (Ansagen aufgeklappt)

        self.card = QWidget(self.root)
        self.card.setObjectName("Card")
        self.card.setStyleSheet(f"QWidget#Card {{ background: {t.CARD_BG}; }}")
        self.card.setFont(t.body_font())
        self.card.setFixedWidth(self.WIDTH)

        row = QHBoxLayout(self.root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.side_panel)
        row.addWidget(self.card)
        self.side_panel.collapsed_changed.connect(self._on_side_collapsed)
        self.side_panel.set_collapsed(app_settings().value("side_collapsed", False, type=bool))

        self.search_input = self._build_search_field()
        self.settings_button = w.icon_button(
            w.ICON_GEAR, t.ACCENT, 20, "Einstellungen", style=t.round_button_style()
        )
        self.settings_button.clicked.connect(self.open_settings)
        self.title_label = self._build_title_label()
        self.audio_section = self._build_audio_section()
        self.results_list = self._build_results_list()
        self.recording_panel = RecordingPanel(self.recorder)
        self.pausentimer_panel = PausentimerPanel()

        for child in (self.search_input, self.settings_button, self.title_label,
                      self.audio_section, self.results_list, self.recording_panel,
                      self.pausentimer_panel):
            child.setParent(self.card)
        self.results_list.hide()
        self.title_label.hide()

        # ESC wirkt im ganzen Hauptfenster, egal welches Element gerade den Fokus hat
        self._esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._esc_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._esc_shortcut.activated.connect(self._on_escape_shortcut)

    def _connect_services(self):
        # Wiedergabe
        self.playback.progress.connect(self.player_panel.set_progress)
        self.playback.playing_changed.connect(self.player_panel.set_playing)
        self.player_panel.toggle_requested.connect(self.playback.toggle)
        self.player_panel.seek_requested.connect(self.playback.seek_percent)
        self.player_panel.stop_requested.connect(self._stop_playback)

        # Auf dem Beamer ist immer nur eines zu sehen
        self.camera_panel.fullscreen_opening.connect(lambda: self.close_beamer_windows(keep="camera"))

        # Seitenleiste
        self.images_panel.open_requested.connect(self.open_gallery)
        self.images_panel.escape_requested.connect(self.handle_escape)
        self.images_panel.images_changed.connect(
            lambda: self.side_panel.set_images_count(self.images_panel.count()))

        # Fehlermeldungen
        self.recorder.error.connect(lambda msg: self._show_error("Aufnahme", msg))
        self.pausentimer.error.connect(lambda msg: self._show_error("Pausentimer", msg))

        # Pausentimer
        self.pausentimer_panel.start_clicked.connect(self._on_pausentimer_start_clicked)
        self.pausentimer_panel.end_time_changed.connect(self.pausentimer.set_end_time)
        self.pausentimer_panel.toggled.connect(self._on_pausentimer_toggled)
        self.pausentimer.running_changed.connect(self.pausentimer_panel.set_running)
        self.pausentimer.running_changed.connect(
            lambda running: self.close_beamer_windows() if running else None)   # Pausenfolie ersetzt Lied/Bilder/Kamera

    def _show_error(self, title: str, message: str):
        QMessageBox.warning(self, title, message)

    def _build_search_field(self):
        search_input = QLineEdit()
        search_input.setPlaceholderText("Suche")
        search_input.setToolTip("Suche nach Liednummer (z. B. 12 oder p012), Titel oder Textstelle\n"
                                "Enter: suchen · nochmal Enter: Beamer-Bild öffnen\n"
                                "Mehrere Treffer: Doppelklick oder Enter wählt das Lied vor\n"
                                "Esc oder Doppelklick: Beamer-Bild schließen, dann Suche leeren und Audio entfernen")
        search_input.setClearButtonEnabled(False)
        search_input.addAction(
            w.themed_icon(w.ICON_SEARCH, t.TEXT_MUTED, 17),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        search_input.setStyleSheet(t.input_style("QLineEdit", "0 12px"))
        search_input.installEventFilter(self)
        search_input.textChanged.connect(self._on_search_text_changed)
        search_input.returnPressed.connect(self._on_search_return_pressed)
        return search_input

    def _build_results_list(self):
        results_list = w.SmoothListWidget()          # sanftes Mausrad-Scrollen wie bei den Bildern
        results_list.setStyleSheet(t.list_style())
        results_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Tastatur bleibt im Suchfeld
        results_list.setUniformItemSizes(True)
        results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        results_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        # Einfachklick markiert nur; Doppelklick (oder Enter) wählt das Lied vor – wie bei den Bildern
        results_list.itemDoubleClicked.connect(self._on_result_clicked)
        return results_list

    def _build_title_label(self):
        title_label = w.ElidingLabel("")
        title_label.setStyleSheet(f"""
            font-family: {t.SERIF};
            font-weight: 700;
            font-size: 17px;
            color: {t.TEXT_PRIMARY};
        """)
        title_label.setHint("Klicken: Liednummer ins Suchfeld übernehmen")
        title_label.clicked.connect(self._on_title_clicked)
        return title_label

    def _make_pill_button(self, label):
        btn = QPushButton(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        btn.setFixedHeight(BTN)
        btn.setCheckable(True)
        btn.setStyleSheet(t.pill_button_style())
        btn.setToolTip(f"{label} abspielen")
        return btn

    def _build_audio_section(self):
        self.audio_stack = QStackedWidget()
        self.audio_stack.addWidget(QWidget())                # AUDIO_EMPTY
        self.audio_stack.addWidget(self._build_select_page())  # AUDIO_SELECT
        self.player_panel = PlayerPanel()
        self.audio_stack.addWidget(self.player_panel)        # AUDIO_PLAYER
        self.audio_stack.addWidget(self._build_notfound_page())  # AUDIO_NOTFOUND
        return self.audio_stack

    def _build_select_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP)
        vcenter = Qt.AlignmentFlag.AlignVCenter

        self.pill_audio1 = self._make_pill_button(self.AUDIO_NAMES[0])
        self.pill_audio2 = self._make_pill_button(self.AUDIO_NAMES[1])
        self.pill_audio1.clicked.connect(lambda: self._play_audio_slot(0))
        self.pill_audio2.clicked.connect(lambda: self._play_audio_slot(1))
        layout.addWidget(self.pill_audio1, 1, vcenter)
        layout.addWidget(self.pill_audio2, 1, vcenter)

        self.no_audio_label = QLabel("Keine Audiodatei vorhanden")
        self.no_audio_label.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FS}px;")
        self.no_audio_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_audio_label.setToolTip("Zu diesem Lied ist keine Audiodatei gespeichert")
        layout.addWidget(self.no_audio_label, 1, vcenter)
        return page

    def _build_notfound_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel("Kein Lied gefunden")
        label.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FS}px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return page

    # ------------------------------------------------------------------
    # Geometrie & Fenster-Ereignisse
    # ------------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)

        content_width = self.WIDTH - (2 * self.PAD_X)
        right = self.PAD_X + content_width

        self.search_input.setGeometry(self.PAD_X, self.Y_SEARCH, content_width - BTN - GAP, BTN)
        self.settings_button.setGeometry(right - BTN, self.Y_SEARCH, BTN, BTN)
        self.title_label.setGeometry(self.PAD_X, self.Y_TITLE, content_width, self.TITLE_H)
        self.audio_section.setGeometry(self.PAD_X, self.Y_AUDIO, content_width, self.PANEL_H)

        list_h = self.Y_REC + self.PANEL_H - self.Y_TITLE
        self.results_list.setGeometry(self.PAD_X, self.Y_TITLE, content_width, list_h)
        self.recording_panel.setGeometry(self.PAD_X, self.Y_REC, content_width, self.PANEL_H)

        pt_height = self.pausentimer_panel.collapsed_height()
        if self.pausentimer_panel.is_open():
            pt_height += self.pausentimer_panel.open_extra_height()
        self.pausentimer_panel.setGeometry(self.PAD_X, self.Y_PT, content_width, pt_height)

    def closeEvent(self, event):
        # Laufende Aufnahme sichern, statt eine Temp-Datei zurückzulassen
        self.recorder.stop_and_save(self.recording_panel.preacher_input.text())
        self.playback.stop()
        self.camera_panel.stop_streams()
        if self.presentation_window:
            self.presentation_window.close()
        if self.gallery_window:
            self.gallery_window.close()
        self.sync.shutdown()
        self.remote.shutdown()
        self.db.close()
        atem.wait_idle()
        event.accept()

    # ------------------------------------------------------------------
    # Pausentimer
    # ------------------------------------------------------------------
    def _on_pausentimer_toggled(self, is_open: bool):
        extra = (self.pausentimer_panel.open_extra_height() + PausentimerPanel.BOTTOM_PAD) if is_open else 0
        self.setFixedHeight(self.COLLAPSED_HEIGHT + extra)
        self.updateGeometry()

    def _on_pausentimer_start_clicked(self):
        if self.pausentimer.running:
            self.pausentimer.stop()
        else:
            self.pausentimer.start(self.pausentimer_panel.lines(), self.pausentimer_panel.end_time())

    # ------------------------------------------------------------------
    # Tastatur & Suche
    # ------------------------------------------------------------------
    def focus_search(self):
        self.activateWindow()
        self.search_input.setFocus()

    def eventFilter(self, obj, event):
        if obj is self.search_input and event.type() == QEvent.Type.MouseButtonDblClick:
            self.handle_escape()  # Doppelklick ins Suchfeld = wie Esc
            return True
        if obj is self.search_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.handle_escape()
                return True
            if (self.gallery_window is not None and self.gallery_window.isVisible()
                    and key in (Qt.Key.Key_PageDown, Qt.Key.Key_PageUp)):
                self.gallery_window.step(1 if key == Qt.Key.Key_PageDown else -1)
                return True
            if self.results_list.isVisible() and self.results_list.count() > 0:
                row = self.results_list.currentRow()
                if key == Qt.Key.Key_Down:
                    self.results_list.setCurrentRow(min(row + 1, self.results_list.count() - 1))
                    return True
                if key == Qt.Key.Key_Up:
                    self.results_list.setCurrentRow(max(row - 1, 0))
                    return True
        return super().eventFilter(obj, event)

    def _on_escape_shortcut(self):
        if self.pausentimer_panel.text_edit.hasFocus():  # beim Tippen der Ansagen nicht die Suche leeren
            return
        self.handle_escape()

    def handle_escape(self):
        """ESC: schließt zuerst das Beamer-Bild, dann ein Kamera-Vollbild; sonst Audio stoppen und Suche leeren."""
        if self.gallery_window is not None and self.gallery_window.isVisible():
            self.close_gallery()  # Bilder-Galerie liegt oben -> zuerst schließen
            self.focus_search()
            return

        if self.presentation_window is not None and self.presentation_window.isVisible():
            self.close_presentation()
            self.focus_search()
            return

        if self.camera_panel.close_all_fullscreen():  # offenes Kamera-Vollbild zuerst schließen
            self.focus_search()
            return

        self.playback.stop()
        self._set_audio_state(self.AUDIO_EMPTY)
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self._hide_search_list()
        self._last_searched_query = ""
        self.search_input.setFocus()

    def _on_sync_requested(self, url: str, token: str):
        """„Jetzt abgleichen“ im Einstellungsdialog: Adresse/Token sind schon gespeichert, der Zeitgeber wird gestartet."""
        self.sync.configure()
        self.sync.run_now(url, token)

    def _on_sync_force_requested(self, url: str, token: str):
        """„Alles neu hochladen“ (im Dialog bereits bestätigt): die lokale Datenbank wird der Stand für alle Geräte."""
        self.sync.configure()
        self.sync.run_now(url, token, force=True)

    def _on_side_collapsed(self, collapsed: bool):
        """Kamera/Bilder ein- oder ausgeklappt: Fensterbreite anpassen und die Wahl merken."""
        new_width = (SidePanel.COLLAPSED_WIDTH if collapsed else SidePanel.WIDTH) + self.WIDTH
        old_width = self.maximumWidth()
        self.setFixedWidth(new_width)
        if self.isVisible() and old_width != new_width:
            x = self.x() + old_width - new_width            # die rechte Kante bleibt stehen: es klappt nach links aus
            screen = self.screen()
            if screen is not None:
                x = max(x, screen.availableGeometry().left())    # nie links aus dem Bildschirm heraus
            self.move(x, self.y())
        app_settings().setValue("side_collapsed", collapsed)

    def open_settings(self):
        dialog = SettingsDialog(self, updates_available=self.updates.available)
        dialog.update_check_requested.connect(lambda: self.updates.check(manual=True))
        self.updates.status_changed.connect(dialog.set_update_status)
        dialog.sync_requested.connect(self._on_sync_requested)
        dialog.sync_force_requested.connect(self._on_sync_force_requested)
        dialog.set_sync_status(self.sync.status)
        self.sync.status_changed.connect(dialog.set_sync_status)
        dialog.set_site_status(self.remote.site_status)
        self.remote.site_status_changed.connect(dialog.set_site_status)
        accepted = dialog.exec()
        self.remote.site_status_changed.disconnect(dialog.set_site_status)
        self.updates.status_changed.disconnect(dialog.set_update_status)
        self.sync.status_changed.disconnect(dialog.set_sync_status)
        if accepted:
            self.camera_panel.update_streams_from_settings()
            self.playback.apply_output_device()
            self._reload_database_if_changed()
            self.sync.configure()
            self.sync.run_now()
            self.remote.configure()

    def _reload_database_if_changed(self):
        """Lädt die Datenbank neu, wenn in den Einstellungen eine andere ausgewählt wurde."""
        new_path = resolve_db_path()
        same = os.path.normcase(os.path.abspath(new_path)) == os.path.normcase(os.path.abspath(self.db.db_name))
        if same:
            return
        log.info("Datenbank gewechselt: %s", new_path)
        self.playback.stop()
        self.db.close()
        self.db = DatabaseManager(new_path)

        # alles zurücksetzen, was zum alten Datenbestand gehörte
        self.current_song_summary = None
        self.current_song_full = None
        self._results = []
        self._last_searched_query = ""
        self.results_list.clear()
        self.title_label.hide()
        self._hide_search_list()
        self._set_audio_state(self.AUDIO_EMPTY)
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self.search_input.setFocus()

        if not self.db.available:
            QMessageBox.warning(self, "Datenbank fehlt",
                                f"Die ausgewählte Datenbank wurde nicht gefunden:\n{new_path}")

    def _on_search_text_changed(self, text):
        if not text.strip():
            self._hide_search_list()
            self._last_searched_query = ""

    def _hide_search_list(self):
        self.results_list.hide()
        self.audio_section.show()
        self.recording_panel.show()
        if self.current_song_summary:
            self.title_label.show()

    def _on_search_return_pressed(self):
        text = self.search_input.text().strip()
        if not text:
            if self.current_song_full:
                self.open_presentation()
            return

        if self.results_list.isVisible() and self.results_list.count() > 0:
            item = self.results_list.currentItem() or self.results_list.item(0)
            self._on_result_clicked(item)
            return

        if self.current_song_summary is not None and text.lower() == self._last_searched_query:
            self.open_presentation()
            return

        self._execute_search(text)

    def _execute_search(self, text):
        self.results_list.clear()
        self._last_searched_query = text.strip().lower()
        songs = self.db.search_songs(text)

        if not songs:
            self._hide_search_list()
            self._set_audio_state(self.AUDIO_NOTFOUND)
            return

        if len(songs) == 1:
            self._hide_search_list()
            self._load_song(songs[0])
            return

        self._results = songs
        self.title_label.hide()
        self.audio_section.setVisible(False)
        self.recording_panel.setVisible(False)

        for index, song in enumerate(songs):
            label = f"Nr. {song.nummer}"
            if song.titel and song.titel != "None":
                label += f" - {song.titel}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.results_list.addItem(item)

        self.results_list.setCurrentRow(0)
        self.results_list.show()

    def _on_result_clicked(self, item):
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is not None and 0 <= index < len(self._results):
            self._hide_search_list()
            self._load_song(self._results[index])

    def _on_title_clicked(self):
        if self.current_song_summary:
            self._remember_query(self.current_song_summary.nummer)
            self.title_label.show()
            self.audio_section.setVisible(True)
            # Audio-Auswahl wieder anzeigen (z. B. nach Esc) – eine laufende Wiedergabe bleibt unberührt
            if self.current_song_full and self.audio_stack.currentIndex() in (self.AUDIO_EMPTY, self.AUDIO_NOTFOUND):
                self._refresh_audio_section()
            self.search_input.setFocus()

    def _remember_query(self, nummer):
        """Zeigt die Liednummer im Suchfeld an, ohne eine neue Suche auszulösen."""
        if not nummer:
            return
        self.search_input.blockSignals(True)
        self.search_input.setText(str(nummer))
        self.search_input.blockSignals(False)
        self._last_searched_query = str(nummer).strip().lower()

    # ------------------------------------------------------------------
    # Lied laden / anzeigen
    # ------------------------------------------------------------------
    def _load_song(self, song):
        self.playback.stop()
        self.current_song_summary = song
        self.current_song_full = self.db.get_song_full_data(song.rowid)

        text = f"{song.nummer}"
        if song.titel and song.titel != "None":
            text += f" - {song.titel}"
        self.title_label.setText(text)
        self.title_label.setVisible(bool(text))
        self._refresh_audio_section()
        self.audio_section.setVisible(True)
        self.recording_panel.setVisible(True)
        self._remember_query(song.nummer)
        self.search_input.setFocus()

    # ------------------------------------------------------------------
    # Bilder-Ablage (Drag & Drop) und Beamer-Galerie
    # ------------------------------------------------------------------
    def add_images(self, paths):
        """Bilder (oder Ordner voller Bilder) in die Ablage legen und auf den Reiter „Bilder“ wechseln."""
        added, failed = self.images_panel.add_paths(paths)
        if added:
            self.side_panel.show_tab(TAB_IMAGES)
        if failed:
            names = "\n".join(f"• {name}" for name in failed[:8])
            if len(failed) > 8:
                names += f"\n… und {len(failed) - 8} weitere"
            QMessageBox.warning(self, "Bilder", f"Diese Dateien konnten nicht als Bild gelesen werden:\n\n{names}")

    def open_gallery(self, start_index=0):
        """Zeigt die abgelegten Bilder ab ``start_index`` auf dem Beamer (dort per Klick weiter, Button zum Schließen)."""
        paths = self.images_panel.paths()
        if not paths:
            return
        atem.switch("presentation")
        screen_index = app_settings().value("beamer_screen", 0, type=int)
        self.close_beamer_windows()      # neues Bild ersetzt alles, was vorher auf dem Beamer war
        self.gallery_window = GalleryWindow(paths, start_index, screen_index, main_window=self)
        self.gallery_window.close_requested.connect(self._on_gallery_close_requested)
        self.gallery_window.index_changed.connect(self.images_panel.select_row)   # heller Rahmen folgt dem Beamer
        self.images_panel.select_row(start_index)
        self.gallery_window.show_on_target_screen()

    def close_presentation(self):
        if self.presentation_window is not None:
            window, self.presentation_window = self.presentation_window, None
            window.close()

    def close_beamer_windows(self, keep=None):
        """Schließt alles, was gerade auf dem Beamer-Bildschirm steht (Lied, Bilder-Galerie, Kamera-Vollbild).

        ``keep``: "presentation", "gallery" oder "camera" – das, was gleich neu angezeigt wird und deshalb bleibt.
        """
        if keep != "presentation":
            self.close_presentation()
        if keep != "gallery":
            self.close_gallery()
        if keep != "camera":
            self.camera_panel.close_all_fullscreen()

    def close_gallery(self):
        if self.gallery_window is not None:
            window, self.gallery_window = self.gallery_window, None
            window.close()
            window.deleteLater()

    def _on_gallery_close_requested(self):
        self.close_gallery()
        self.focus_search()

    def open_presentation(self):
        if not self.current_song_full:
            return

        atem.switch("presentation")
        screen_index = app_settings().value("beamer_screen", 0, type=int)
        self.close_beamer_windows(keep="presentation")   # Galerie und Kamera-Vollbild weichen dem Lied

        if self.presentation_window is None:
            self.presentation_window = ImagePresentationWindow(
                self.current_song_full, screen_index, main_window=self
            )
        else:
            self.presentation_window.target_screen_index = screen_index
            self.presentation_window.main_window = self
            self.presentation_window.load_song(self.current_song_full)

        self.presentation_window.show_on_target_screen()

    # ------------------------------------------------------------------
    # Audio-Bereich
    # ------------------------------------------------------------------
    def _audio_blob(self, slot_index):
        idx = 5 + slot_index
        if not self.current_song_full or idx >= len(self.current_song_full):
            return None
        data = self.current_song_full[idx]
        return data if data and isinstance(data, (bytes, bytearray)) else None

    def _refresh_audio_section(self):
        if not self.current_song_full:
            self._set_audio_state(self.AUDIO_EMPTY)
            return

        has1 = self._audio_blob(0) is not None
        has2 = self._audio_blob(1) is not None
        self.pill_audio1.setVisible(has1)
        self.pill_audio2.setVisible(has2)
        self.no_audio_label.setVisible(not (has1 or has2))
        self.pill_audio1.setChecked(False)
        self.pill_audio2.setChecked(False)
        self._set_audio_state(self.AUDIO_SELECT)

    def _set_audio_state(self, index):
        self.audio_stack.setCurrentIndex(index)

    def _play_audio_slot(self, slot_index):
        data = self._audio_blob(slot_index)
        if data is None:
            return
        self.player_panel.set_track_name(self.AUDIO_NAMES[slot_index])
        self.playback.play_bytes(data)
        self._set_audio_state(self.AUDIO_PLAYER)

    def _stop_playback(self):
        self.playback.stop()
        if self.current_song_full:
            self._refresh_audio_section()
        else:
            self._set_audio_state(self.AUDIO_EMPTY)
