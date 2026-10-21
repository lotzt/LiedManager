"""Einstellungsdialog: Anzeige, Audio, Kamera, ATEM, Datenbank (mit Abgleich), Remote, Update (gleiches Design wie das Hauptfenster)."""
import os
import threading

from PyQt6.QtCore import QStandardPaths, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtMultimedia import QMediaDevices
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from paths import custom_pausentimer_dir, default_db_path
from services import atem, devices, songlog
from version import __version__
from services.settings import app_settings
from ui import theme as t
from ui.sync_ui import KEY_SYNC_ENABLED, KEY_SYNC_TOKEN, KEY_SYNC_URL, STATUS_OFF
from ui.updater_ui import KEY_CHECK_ON_START
from ui.web_remote_ui import KEY_SITE_ENABLED, KEY_SITE_TOKEN, KEY_SITE_URL
from ui.widgets import round_combo_popup

FIELD_H = 40
CARD_PAD = 18
CARD_GAP = 16


class SettingsDialog(QDialog):
    """Einstellungsdialog für Anzeige, ATEM-Kanäle, Kameras, Audio, Daten, Abgleich und Steuerung."""

    atem_test_done = pyqtSignal(bool, str)
    update_check_requested = pyqtSignal()
    sync_requested = pyqtSignal(str, str)   # Adresse und Token aus den Feldern: sofort abgleichen
    sync_force_requested = pyqtSignal(str, str)   # dasselbe, aber „Alles neu hochladen“ (bestätigt)

    def __init__(self, parent=None, updates_available: bool = False):
        super().__init__(parent)
        self._updates_available = updates_available
        self.setWindowTitle("LiedManager – Einstellungen")
        self.setMinimumSize(640, 480)
        self.resize(640, 600)          # die endgültige Höhe ergibt sich aus der höchsten Seite (_fit_height)
        self.setStyleSheet(t.panel_style("Card") + t.primary_button_style("PrimaryButton"))

        self.settings = app_settings()
        self._build_ui()
        self.atem_test_done.connect(self._on_atem_test_done)
        self.load_settings()
        self._fit_height()

    # ------------------------------------------------------------------
    # Bausteine
    # ------------------------------------------------------------------
    @staticmethod
    def _field(caption: str, widget: QWidget, hint: str = "") -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(caption)
        label.setStyleSheet(t.caption_style())
        layout.addWidget(label)
        layout.addWidget(widget)
        if hint:
            layout.addSpacing(4)
            hint_label = QLabel(hint)
            hint_label.setWordWrap(True)
            hint_label.setStyleSheet(t.hint_style())
            layout.addWidget(hint_label)
        return box

    @staticmethod
    def _card(*items) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(CARD_PAD, CARD_PAD, CARD_PAD, CARD_PAD)
        layout.setSpacing(CARD_GAP)
        for item in items:
            if isinstance(item, QWidget):
                layout.addWidget(item)
            else:
                layout.addLayout(item)
        return card

    @staticmethod
    def _page(*cards) -> QWidget:
        """Eine Seite des Dialogs. Sie liegt in einer Bildlauf-Fläche: Reicht der Platz nicht (lange Hinweistexte,
        kleiner Bildschirm), wird gescrollt, statt Felder oder Text abzuschneiden."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 4)
        layout.setSpacing(14)
        for card in cards:
            layout.addWidget(card)
        layout.addStretch()
        page.setAutoFillBackground(False)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }"
                             "QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(page)
        return scroll

    @staticmethod
    def _combo() -> QComboBox:
        combo = QComboBox()
        combo.setFixedHeight(FIELD_H)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.setStyleSheet(t.combo_style())
        round_combo_popup(combo)  # aufklappende Liste mit runden Ecken
        return combo

    @staticmethod
    def _line_edit(placeholder: str = "") -> QLineEdit:
        edit = QLineEdit()
        edit.setFixedHeight(FIELD_H)
        edit.setPlaceholderText(placeholder)
        edit.setStyleSheet(t.input_style("QLineEdit", "0 12px"))
        return edit

    @staticmethod
    def _checkbox(text: str) -> QCheckBox:
        box = QCheckBox(text)
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        box.setStyleSheet(t.checkbox_style())
        return box

    @staticmethod
    def _spinbox(low: int = 1, high: int = 20) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setFixedSize(92, FIELD_H)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setStyleSheet(t.spinbox_style())
        return spin

    @staticmethod
    def _outline_button(text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(FIELD_H)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoDefault(False)
        btn.setStyleSheet(t.pill_button_style(radius=t.RADIUS))
        return btn

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(0)

        heading = QLabel("Einstellungen")
        heading.setStyleSheet(
            f"font-family: {t.SERIF}; font-weight: 700; font-size: 20px; color: {t.TEXT_PRIMARY};"
        )
        root.addWidget(heading)
        self._heading = heading
        root.addSpacing(14)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        self.pages = QStackedWidget()
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        entries = (
            ("Anzeige", self.create_display_tab()),
            ("Audio", self.create_audio_tab()),
            ("Kamera", self.create_camera_tab()),
            ("ATEM", self.create_atem_tab()),
            ("Datenbank", self.create_data_tab()),
            ("Remote", self.create_remote_tab()),
            ("Update", self.create_update_tab()),
        )
        for index, (label, page) in enumerate(entries):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.setAutoDefault(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(t.pill_button_style(radius=18, font_size=13) + "QPushButton { padding: 0 12px; }")
            btn.setToolTip(f"Einstellungen: {label}")
            self.tab_group.addButton(btn, index)
            tab_row.addWidget(btn)
            self.pages.addWidget(page)
        tab_row.addStretch()
        self.tab_group.idClicked.connect(self.pages.setCurrentIndex)
        self.tab_group.button(0).setChecked(True)
        root.addLayout(tab_row)
        root.addWidget(self.pages, 1)

        root.addSpacing(16)
        footer = QHBoxLayout()
        footer.setSpacing(t.GAP)
        version_label = QLabel(f"Version {__version__}")
        version_label.setStyleSheet(t.hint_style())
        footer.addWidget(version_label)
        footer.addStretch()
        cancel = self._outline_button("Abbrechen")
        cancel.setMinimumWidth(120)
        cancel.clicked.connect(self.reject)
        cancel.setToolTip("Änderungen verwerfen")
        save = QPushButton("Speichern")
        save.setObjectName("PrimaryButton")
        save.setFixedHeight(FIELD_H)
        save.setMinimumWidth(130)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setDefault(True)
        save.clicked.connect(self.save_and_close)
        save.setToolTip("Einstellungen übernehmen")
        footer.addWidget(cancel)
        footer.addWidget(save)
        root.addLayout(footer)

    def _fit_height(self) -> None:
        """Macht den Dialog so hoch, dass die höchste Seite (Datenbank) ganz zu sehen ist und nicht gescrollt werden muss.
        Nur auf sehr kleinen Bildschirmen wird gekürzt – dann greift die Bildlauf-Fläche."""
        width = self.width() - 48
        need = 0
        for index in range(self.pages.count()):
            page = self.pages.widget(index).widget()
            height = page.heightForWidth(width) if page.hasHeightForWidth() else page.sizeHint().height()
            need = max(need, height, page.sizeHint().height())
        chrome = 44 + self._heading.sizeHint().height() + 14 + 36 + 16 + FIELD_H + 16   # Ränder, Titel, Reiter, Fußzeile
        screen = self.screen() or QApplication.primaryScreen()
        limit = screen.availableGeometry().height() - 60 if screen is not None else 900
        self.resize(self.width(), max(480, min(need + chrome, limit)))

    def create_display_tab(self):
        self.screen_combo = self._combo()
        self.populate_screens()
        self.fullscreen_checkbox = self._checkbox("Präsentationen im rahmenlosen Vollbild starten")
        self.fullscreen_checkbox.setChecked(True)
        self.screen_combo.setToolTip("Auf diesem Bildschirm erscheinen Beamer-Bild und Kamera-Vollbild")
        self.fullscreen_checkbox.setToolTip("Aus: das Beamer-Bild öffnet sich als normales, verschiebbares Fenster")

        self.season_combo = self._combo()
        for label, key in (("Frühling", "frühling"), ("Sommer", "sommer"),
                           ("Herbst", "herbst"), ("Winter", "winter")):
            self.season_combo.addItem(label, key)
        self.season_combo.setToolTip("Welche Pausenfolie (PowerPoint-Vorlage) der Pausentimer verwendet\n"
                                     "Genutzt wird die Datei „pausentimer_<Jahreszeit>.pptx“")
        self.open_presentations_btn = self._outline_button("Ordner für Pausenfolien öffnen")
        self.open_presentations_btn.clicked.connect(self.open_presentation_folder)
        self.open_presentations_btn.setToolTip(
            "Öffnet den Ordner für deine Pausenfolien im Datei-Manager\n"
            "Hier liegen die Dateien „pausentimer_<Jahreszeit>.pptx“ (Vorlagen werden nicht mitgeliefert)")

        self.songlog_checkbox = self._checkbox("Gespielte Lieder in einer Textdatei speichern")
        self.songlog_checkbox.setToolTip(
            "Jedes Lied, das auf dem Beamer gezeigt wird, kommt mit Nummer und Titel in die Datei „Gespielte Lieder.txt“ (nach Datum geordnet)")
        self.test_mode_checkbox = self._checkbox("Testmodus – nichts speichern")
        self.test_mode_checkbox.setToolTip(
            "Zum Ausprobieren und Proben: Lieder werden nicht in die Liste geschrieben.\n"
            "Im Fenstertitel steht dann „Testmodus“. Nach dem Test wieder ausschalten.")
        self.open_songlog_btn = self._outline_button("Liste der gespielten Lieder öffnen")
        self.open_songlog_btn.setToolTip("Zeigt die Datei „Gespielte Lieder.txt“ im Datei-Manager (dort steht alles, mit Wochentag und Datum)")
        self.open_songlog_btn.clicked.connect(self.open_songlog_folder)

        return self._page(
            self._card(
                self._field("Präsentations-Bildschirm (Zweitmonitor)", self.screen_combo),
                self.fullscreen_checkbox,
            ),
            self._card(
                self._field("Pausentimer-Vorlage / Jahreszeit", self.season_combo),
                self.open_presentations_btn,
            ),
            self._card(self.songlog_checkbox, self.test_mode_checkbox, self.open_songlog_btn),
        )

    def create_atem_tab(self):
        self.atem_enabled_checkbox = self._checkbox("Blackmagic ATEM Mischer automatisch ansteuern")

        self.atem_enabled_checkbox.setToolTip("Schaltet den Mischer bei Präsentation, Pausentimer und Kameras automatisch um")
        self.atem_ip_input = self._line_edit("z. B. 192.168.10.240")
        self.atem_ip_input.setToolTip("Netzwerk-Adresse des ATEM Mischers")
        self.atem_test_btn = self._outline_button("Verbindung testen")
        self.atem_test_btn.clicked.connect(self.test_atem_connection)
        self.atem_test_btn.setToolTip("Prüft, ob der Mischer unter dieser Adresse erreichbar ist")
        ip_row = QHBoxLayout()
        ip_row.setSpacing(t.GAP)
        ip_row.addWidget(self.atem_ip_input, 1)
        ip_row.addWidget(self.atem_test_btn)
        ip_box = QWidget()
        ip_box_layout = QVBoxLayout(ip_box)
        ip_box_layout.setContentsMargins(0, 0, 0, 0)
        ip_box_layout.setSpacing(6)
        ip_caption = QLabel("IP-Adresse des ATEM Switchers")
        ip_caption.setStyleSheet(t.caption_style())
        ip_box_layout.addWidget(ip_caption)
        ip_box_layout.addLayout(ip_row)

        self.atem_status_label = QLabel()
        self._set_atem_status("idle", "Noch nicht getestet")

        self.atem_pres_spin = self._spinbox()
        self.atem_cam_spin = self._spinbox()
        self.atem_default_spin = self._spinbox()
        self.atem_pres_spin.setToolTip("Mischer-Eingang für Beamer-Bild und Pausentimer")
        self.atem_cam_spin.setToolTip("Mischer-Eingang für die Kamera-Bilder")
        self.atem_default_spin.setToolTip("Mischer-Eingang, auf den beim Beenden zurückgeschaltet wird")
        grid = QGridLayout()
        grid.setHorizontalSpacing(t.GAP)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        rows = (
            ("Präsentation / Pausentimer", self.atem_pres_spin),
            ("Seitenleisten-Kamera", self.atem_cam_spin),
            ("Standard beim Schließen", self.atem_default_spin),
        )
        for row, (text, spin) in enumerate(rows):
            label = QLabel(text)
            label.setStyleSheet(f"font-size: {t.FS}px; color: {t.TEXT_LABEL};")
            grid.addWidget(label, row, 0)
            grid.addWidget(spin, row, 1)
        channels_caption = QLabel("Kanal-Zuordnung")
        channels_caption.setStyleSheet(t.caption_style())

        first_items = [self.atem_enabled_checkbox]
        if not atem.available():
            missing = QLabel("Das ATEM-Modul (PyATEMMax) ist nicht installiert – die Umschaltung ist deshalb inaktiv. Es wird beim nächsten Start automatisch installiert.")
            missing.setWordWrap(True)
            missing.setStyleSheet(t.hint_style())
            first_items.append(missing)
        first_items += [ip_box, self.atem_status_label]

        return self._page(
            self._card(*first_items),
            self._card(channels_caption, grid),
        )

    def create_camera_tab(self):
        self.cam1_combo = self._combo()
        self.cam2_combo = self._combo()
        self.populate_video_devices()
        self.cam1_combo.setToolTip("Videoquelle für das obere Kamerabild")
        self.cam2_combo.setToolTip("Videoquelle für das untere Kamerabild")
        return self._page(
            self._card(
                self._field("Live Kamera 1 (Videoquelle)", self.cam1_combo),
                self._field("Live Kamera 2 (Videoquelle)", self.cam2_combo),
            ),
        )

    def create_audio_tab(self):
        self.audio_device_combo = self._combo()
        self.mic_device_combo = self._combo()
        self.populate_audio_devices()
        self.audio_device_combo.setToolTip("Hierüber werden Piano und GL3 abgespielt (Systemstandard = normale Ausgabe)")
        self.mic_device_combo.setToolTip("Mikrofon für die Aufnahme (Systemstandard = normales Mikrofon)")

        default_dir = os.path.join(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation),
            "LiedManager Aufnahmen",
        )
        self.rec_path_input = self._line_edit(default_dir)
        self.rec_path_browse_btn = self._outline_button("Durchsuchen …")
        self.rec_path_browse_btn.clicked.connect(self.browse_recording_path)
        self.rec_path_input.setToolTip("Ordner, in dem fertige Aufnahmen als WAV-Datei gespeichert werden")
        self.rec_path_browse_btn.setToolTip("Ordner auswählen")
        path_row = QHBoxLayout()
        path_row.setSpacing(t.GAP)
        path_row.addWidget(self.rec_path_input, 1)
        path_row.addWidget(self.rec_path_browse_btn)
        path_box = QWidget()
        path_layout = QVBoxLayout(path_box)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)
        path_caption = QLabel("Speicherort für Aufnahmen")
        path_caption.setStyleSheet(t.caption_style())
        path_layout.addWidget(path_caption)
        path_layout.addLayout(path_row)

        return self._page(
            self._card(
                self._field("Audio-Ausgabegerät (Soundkarte / PA)", self.audio_device_combo),
                self._field("Mikrofon-Eingabegerät (Aufnahme)", self.mic_device_combo),
            ),
            self._card(path_box),
        )

    def _build_sync_card(self) -> QFrame:
        """Abgleich der Datenbank mit dem eigenen Server (gehört in den Reiter „Datenbank“)."""
        intro = QLabel("Die Datenbank bleibt auf jedem Gerät lokal. Über deinen Server werden nur Änderungen an den "
                       "Liedern geteilt – automatisch beim Start und danach jede Minute, solange eine Verbindung besteht.")
        intro.setWordWrap(True)
        intro.setStyleSheet(t.hint_style())
        self.sync_checkbox = self._checkbox("Abgleich über meinen Server einschalten")
        self.sync_checkbox.setToolTip(
            "Ein: die Datenbank wird mit deinem Server abgeglichen.\n"
            "Aus: die Verbindung wird getrennt; Adresse und Token bleiben gespeichert. Die Datenbank bleibt lokal nutzbar.")
        self.sync_url_input = self._line_edit("https://deine-domain.de/sync/sync.php")
        self.sync_url_input.setToolTip(
            "Adresse der Datei sync.php auf deinem Server (muss mit https:// beginnen).\n"
            "Auf allen Geräten dieselbe Adresse und dasselbe Token eintragen.\n"
            "Beim ersten Mal gilt der aktuelle Stand als Ausgangspunkt.")
        self.sync_token_input = self._line_edit("Token (steht in sync.php)")
        self.sync_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.sync_token_input.setToolTip("Das geheime Token aus der Datei sync.php auf dem Server. Auf allen Geräten gleich.")
        self.sync_now_btn = self._outline_button("Jetzt abgleichen")
        self.sync_now_btn.setToolTip("Sendet eigene Änderungen und holt die der anderen Geräte – im Hintergrund")
        self.sync_now_btn.clicked.connect(self._sync_now_clicked)
        self.sync_force_btn = self._outline_button("Alles neu hochladen")
        self.sync_force_btn.setToolTip(
            "Macht die Datenbank auf diesem Gerät zum verbindlichen Stand für alle Geräte:\n"
            "Alle Lieder werden hochgeladen, Lieder, die hier fehlen, werden überall gelöscht.\n"
            "Nach dem Austausch der Datenbank nutzen – vorher eine Sicherungskopie anlegen.")
        self.sync_force_btn.clicked.connect(self._sync_force_clicked)
        self.sync_checkbox.toggled.connect(self._sync_toggled)
        self.sync_url_input.editingFinished.connect(self._save_sync_fields)
        self.sync_token_input.editingFinished.connect(self._save_sync_fields)
        self.sync_status_label = QLabel(STATUS_OFF)
        self.sync_status_label.setWordWrap(True)
        self.sync_status_label.setStyleSheet(t.hint_style())
        buttons = QHBoxLayout()
        buttons.setSpacing(t.GAP)
        buttons.addWidget(self.sync_now_btn)
        buttons.addWidget(self.sync_force_btn)
        buttons.addStretch()
        return self._card(intro, self.sync_checkbox, self._field("Server-Adresse", self.sync_url_input),
                          self._field("Token", self.sync_token_input), buttons, self.sync_status_label)

    def create_data_tab(self):
        self.db_path_input = self._line_edit(default_db_path())
        self.db_path_input.setToolTip("Leer lassen: die Datenbank wird automatisch gesucht (Platzhalter zeigt den Standardpfad)")
        self.db_path_browse_btn = self._outline_button("Durchsuchen …")
        self.db_path_browse_btn.clicked.connect(self.browse_database_path)
        self.db_path_browse_btn.setToolTip("Datenbank-Datei auswählen\nWird beim Speichern sofort geladen, Wiedergabe und Liedauswahl werden zurückgesetzt")
        self.db_path_reset_btn = self._outline_button("Automatisch")
        self.db_path_reset_btn.clicked.connect(lambda: self.db_path_input.clear())
        self.db_path_reset_btn.setToolTip("Auswahl entfernen – die Datenbank wird wieder automatisch gesucht")
        db_row = QHBoxLayout()
        db_row.setSpacing(t.GAP)
        db_row.addWidget(self.db_path_input, 1)
        db_row.addWidget(self.db_path_browse_btn)
        db_row.addWidget(self.db_path_reset_btn)
        db_box = QWidget()
        db_layout = QVBoxLayout(db_box)
        db_layout.setContentsMargins(0, 0, 0, 0)
        db_layout.setSpacing(6)
        db_caption = QLabel("Lieder-Datenbank (LiedManager.db)")
        db_caption.setStyleSheet(t.caption_style())
        db_layout.addWidget(db_caption)
        db_layout.addLayout(db_row)

        return self._page(
            self._card(db_box),
            self._build_sync_card(),
        )

    def create_update_tab(self):
        self.update_checkbox = self._checkbox("Beim Start nach Updates suchen")
        self.update_checkbox.setToolTip("Fragt beim Programmstart bei GitHub nach einer neueren Version (nur wenn online)")
        self.update_check_btn = self._outline_button("Jetzt nach Updates suchen")
        self.update_check_btn.setToolTip("Prüft sofort, ob es eine neuere Version gibt")
        self.update_check_btn.clicked.connect(self.update_check_requested)
        self.update_status_label = QLabel()
        self.update_status_label.setWordWrap(True)
        self.update_status_label.setStyleSheet(t.hint_style())
        update_row = QHBoxLayout()
        update_row.setSpacing(t.GAP)
        update_row.addWidget(self.update_check_btn)
        update_row.addWidget(self.update_status_label, 1)
        if self._updates_available:
            self.set_update_status(f"Installiert: Version {__version__}")
        else:
            self.update_check_btn.setEnabled(False)
            self.update_checkbox.setEnabled(False)
            self.set_update_status("In dieser Version nicht eingerichtet (Start aus dem Quellcode).")

        return self._page(self._card(self.update_checkbox, update_row))

    def create_remote_tab(self):
        """Reiter „Remote“: LiedManager per Handy über die eigene Website bedienen."""
        intro = QLabel("Bedienung per Handy von überall: LiedManager verbindet sich mit deiner Website (remote.php) und "
                       "holt dort die Befehle ab. Dazu muss das Programm laufen und online sein. Die PIN für den "
                       "Browser legst du in remote.php fest.")
        intro.setWordWrap(True)
        intro.setStyleSheet(t.hint_style())
        self.site_checkbox = self._checkbox("Remote über meine Website einschalten")
        self.site_checkbox.setToolTip(
            "Verbindet LiedManager mit deiner Website (remote.php). Dann bedienst du das Programm per Handy von überall –\n"
            "mit HTTPS und PIN. LiedManager muss dafür laufen und online sein. Die PIN legst du in remote.php fest.")
        self.site_url_input = self._line_edit("https://deine-domain.de/steuerung/remote.php")
        self.site_url_input.setToolTip("Adresse von remote.php auf deiner Website (mit https://). Dieselbe Adresse öffnest du im Browser.")
        self.site_token_input = self._line_edit("Token (steht in remote.php)")
        self.site_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.site_token_input.setToolTip("Das geheime Token aus der Datei remote.php auf dem Server (mindestens 16 Zeichen).")
        self.site_checkbox.toggled.connect(self._site_toggled)
        self.site_url_input.editingFinished.connect(self._save_site_fields)
        self.site_token_input.editingFinished.connect(self._save_site_fields)
        self.site_status_label = QLabel(STATUS_OFF)
        self.site_status_label.setWordWrap(True)
        self.site_status_label.setStyleSheet(t.hint_style())
        self.site_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return self._page(
            self._card(intro, self.site_checkbox, self._field("Adresse der Website", self.site_url_input),
                       self._field("Token", self.site_token_input), self.site_status_label),
        )

    def set_site_status(self, text: str) -> None:
        self.site_status_label.setText(text)

    def set_sync_status(self, text: str) -> None:
        self.sync_status_label.setText(text)

    def _save_site_fields(self):
        s = self.settings
        s.setValue(KEY_SITE_URL, self.site_url_input.text().strip())
        s.setValue(KEY_SITE_TOKEN, self.site_token_input.text().strip())
        s.sync()

    def _site_toggled(self, on: bool):
        """Remote sofort ein- oder ausschalten: beim Ausschalten wird die Verbindung getrennt und die Anzeige geleert."""
        self._save_site_fields()
        self.settings.setValue(KEY_SITE_ENABLED, on)
        self.settings.sync()
        remote = getattr(self.parent(), "remote", None)
        if remote is not None:
            remote.configure()
            self.site_status_label.setText(remote.site_status)

    def _sync_toggled(self, on: bool):
        """Abgleich sofort ein- oder ausschalten: Adresse und Token bleiben, nur die Verbindung wird getrennt."""
        self._save_sync_fields()
        self.settings.setValue(KEY_SYNC_ENABLED, on)
        self.settings.sync()
        self._update_sync_buttons()
        sync = getattr(self.parent(), "sync", None)
        if sync is not None:
            sync.configure()
            self.sync_status_label.setText(sync.status)
        elif not on:
            self.sync_status_label.setText(STATUS_OFF)

    def _update_sync_buttons(self):
        on = self.sync_checkbox.isChecked()
        self.sync_now_btn.setEnabled(on)
        self.sync_force_btn.setEnabled(on)

    def _save_sync_fields(self):
        """Adresse und Token sofort speichern – sie bleiben auch erhalten, wenn der Dialog mit „Abbrechen“ geschlossen wird."""
        s = self.settings
        s.setValue(KEY_SYNC_URL, self.sync_url_input.text().strip())
        s.setValue(KEY_SYNC_TOKEN, self.sync_token_input.text().strip())
        s.sync()

    def _sync_now_clicked(self):
        self._save_sync_fields()
        self.sync_requested.emit(self.sync_url_input.text().strip(), self.sync_token_input.text().strip())

    def _sync_force_clicked(self):
        url = self.sync_url_input.text().strip()
        if not url:
            self.set_sync_status("Bitte zuerst die Server-Adresse und das Token eintragen.")
            return
        answer = QMessageBox.question(
            self, "Alles neu hochladen?",
            "Die Datenbank auf diesem Gerät wird zum Stand für ALLE Geräte:\n\n"
            "• Alle Lieder werden zum Server hochgeladen (kann dauern).\n"
            "• Lieder, die in dieser Datenbank fehlen, werden auf allen Geräten gelöscht.\n"
            "• Andere Geräte überschreiben ihre Lieder mit diesem Stand.\n\n"
            "Das lässt sich nicht rückgängig machen. Hast du eine Sicherungskopie der Datenbank?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._save_sync_fields()
        self.sync_force_requested.emit(url, self.sync_token_input.text().strip())

    def set_update_status(self, text: str) -> None:
        self.update_status_label.setText(text)

    # ------------------------------------------------------------------
    # Geräte-Listen
    # ------------------------------------------------------------------
    def populate_screens(self):
        for index, screen in enumerate(QApplication.screens()):
            geo = screen.geometry()
            self.screen_combo.addItem(
                f"Bildschirm {index + 1} ({geo.width()}×{geo.height()}) – {screen.name()}", index
            )

    def populate_audio_devices(self):
        self.audio_device_combo.addItem("Systemstandard", "")
        for device in QMediaDevices.audioOutputs():
            self.audio_device_combo.addItem(device.description(), devices.device_key(device))
        self.mic_device_combo.addItem("Systemstandard", "")
        for device in QMediaDevices.audioInputs():
            self.mic_device_combo.addItem(device.description(), devices.device_key(device))

    def populate_video_devices(self):
        self.cam1_combo.addItem("Keine Kamera", userData=None)
        self.cam2_combo.addItem("Keine Kamera", userData=None)
        for device in QMediaDevices.videoInputs():
            name = device.description()
            self.cam1_combo.addItem(name, userData=device)
            self.cam2_combo.addItem(name, userData=device)

    def browse_recording_path(self):
        path = QFileDialog.getExistingDirectory(
            self, "Speicherort für Aufnahmen auswählen", self.rec_path_input.text()
        )
        if path:
            self.rec_path_input.setText(path)

    def browse_database_path(self):
        start = self.db_path_input.text().strip() or default_db_path()
        path, _ = QFileDialog.getOpenFileName(
            self, "Datenbank auswählen", start,
            "Datenbanken (*.db *.sqlite *.sqlite3);;Alle Dateien (*)",
        )
        if path:
            self.db_path_input.setText(path)

    def open_songlog_folder(self):
        path = songlog.file_path()
        if not path.exists():
            path.write_text("", encoding="utf-8")            # erst anlegen, damit der Knopf immer etwas zeigt
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_presentation_folder(self):
        folder = custom_pausentimer_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ------------------------------------------------------------------
    # ATEM-Test (im Hintergrund, damit der Dialog nicht einfriert)
    # ------------------------------------------------------------------
    def _set_atem_status(self, kind: str, text: str):
        color = {"ok": t.ACCENT_LIGHT, "error": t.REC_RED, "busy": t.TEXT_SECONDARY}.get(kind, t.TEXT_MUTED)
        self.atem_status_label.setText(f"●  {text}")
        self.atem_status_label.setStyleSheet(
            f"font-size: {t.FS_SMALL}px; font-weight: 500; color: {color}; background: transparent; border: 0;"
        )

    def test_atem_connection(self):
        ip = self.atem_ip_input.text().strip()
        if not ip:
            self._set_atem_status("error", "Bitte zuerst eine IP-Adresse eingeben")
            return
        self.atem_test_btn.setEnabled(False)
        self._set_atem_status("busy", "Verbindung wird getestet …")
        threading.Thread(target=self._run_atem_test, args=(ip,), daemon=True).start()

    def _run_atem_test(self, ip: str):
        ok, message = atem.test_connection(ip)
        try:
            self.atem_test_done.emit(ok, message)
        except RuntimeError:  # Dialog wurde währenddessen geschlossen
            pass

    def _on_atem_test_done(self, ok: bool, message: str):
        self.atem_test_btn.setEnabled(True)
        self._set_atem_status("ok" if ok else "error", "Verbunden" if ok else f"Keine Verbindung – {message}")

    # ------------------------------------------------------------------
    # Laden / Speichern
    # ------------------------------------------------------------------
    @staticmethod
    def _select_data(combo: QComboBox, key):
        index = combo.findData(key)
        if index >= 0:
            combo.setCurrentIndex(index)

    def load_settings(self):
        s = self.settings
        self.screen_combo.setCurrentIndex(s.value("beamer_screen", 0, type=int))
        self.fullscreen_checkbox.setChecked(s.value("fullscreen_mode", True, type=bool))
        self._select_data(self.season_combo, s.value("presentation_season", "frühling", type=str))
        self.songlog_checkbox.setChecked(s.value(songlog.KEY_ENABLED, True, type=bool))
        self.test_mode_checkbox.setChecked(s.value(songlog.KEY_TEST_MODE, False, type=bool))

        self.atem_enabled_checkbox.setChecked(s.value("atem_enabled", False, type=bool))
        self.atem_ip_input.setText(s.value("atem_ip", "", type=str))
        self.atem_pres_spin.setValue(s.value("atem_pres_channel", 3, type=int))
        self.atem_cam_spin.setValue(s.value("atem_cam_channel", 4, type=int))
        self.atem_default_spin.setValue(s.value("atem_default_channel", 1, type=int))

        self._select_data(self.audio_device_combo, s.value(devices.KEY_OUTPUT, "", type=str))
        self._select_data(self.mic_device_combo, s.value(devices.KEY_INPUT, "", type=str))
        self.rec_path_input.setText(s.value("recording_path", "", type=str))
        self.update_checkbox.setChecked(s.value(KEY_CHECK_ON_START, True, type=bool))
        self.db_path_input.setText(s.value("database_path", "", type=str))
        self.sync_url_input.setText(s.value(KEY_SYNC_URL, "", type=str))
        self.sync_token_input.setText(s.value(KEY_SYNC_TOKEN, "", type=str))
        self.sync_checkbox.blockSignals(True)
        flag = s.value(KEY_SYNC_ENABLED, None)
        self.sync_checkbox.setChecked(bool(self.sync_url_input.text()) if flag is None else str(flag).lower() in ("true", "1"))
        self.sync_checkbox.blockSignals(False)
        self._update_sync_buttons()
        self.site_checkbox.blockSignals(True)
        self.site_checkbox.setChecked(s.value(KEY_SITE_ENABLED, False, type=bool))
        self.site_checkbox.blockSignals(False)
        self.site_url_input.setText(s.value(KEY_SITE_URL, "", type=str))
        self.site_token_input.setText(s.value(KEY_SITE_TOKEN, "", type=str))
        if getattr(self.parent(), "remote", None) is not None:
            self.site_status_label.setText(self.parent().remote.site_status)

        for combo, key in ((self.cam1_combo, "camera_1_name"), (self.cam2_combo, "camera_2_name")):
            saved = s.value(key, "", type=str)
            if saved:
                index = combo.findText(saved)
                if index >= 0:
                    combo.setCurrentIndex(index)

    def save_and_close(self):
        s = self.settings
        s.setValue("beamer_screen", self.screen_combo.currentIndex())
        s.setValue("fullscreen_mode", self.fullscreen_checkbox.isChecked())
        s.setValue("presentation_season", self.season_combo.currentData())
        s.setValue(songlog.KEY_ENABLED, self.songlog_checkbox.isChecked())
        s.setValue(songlog.KEY_TEST_MODE, self.test_mode_checkbox.isChecked())

        s.setValue("atem_enabled", self.atem_enabled_checkbox.isChecked())
        s.setValue("atem_ip", self.atem_ip_input.text().strip())
        s.setValue("atem_pres_channel", self.atem_pres_spin.value())
        s.setValue("atem_cam_channel", self.atem_cam_spin.value())
        s.setValue("atem_default_channel", self.atem_default_spin.value())

        s.setValue(devices.KEY_OUTPUT, self.audio_device_combo.currentData() or "")
        s.setValue(devices.KEY_INPUT, self.mic_device_combo.currentData() or "")
        s.setValue("recording_path", self.rec_path_input.text().strip())
        s.setValue("database_path", self.db_path_input.text().strip())
        s.setValue(KEY_SYNC_URL, self.sync_url_input.text().strip())
        s.setValue(KEY_SYNC_TOKEN, self.sync_token_input.text().strip())
        s.setValue(KEY_SYNC_ENABLED, self.sync_checkbox.isChecked())
        s.setValue(KEY_SITE_ENABLED, self.site_checkbox.isChecked())
        s.setValue(KEY_SITE_URL, self.site_url_input.text().strip())
        s.setValue(KEY_SITE_TOKEN, self.site_token_input.text().strip())
        s.setValue(KEY_CHECK_ON_START, self.update_checkbox.isChecked())

        s.setValue("camera_1_name", self.cam1_combo.currentText())
        s.setValue("camera_2_name", self.cam2_combo.currentText())
        s.sync()
        self.accept()
