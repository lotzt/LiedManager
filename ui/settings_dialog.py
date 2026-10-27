"""Einstellungsdialog: Anzeige, Audio, Kamera, Mischpult, Datenbank (mit Abgleich), Remote, Update (gleiches Design wie das Hauptfenster)."""
import os
import threading

from PyQt6.QtCore import QStandardPaths, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtMultimedia import QMediaDevices
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from paths import custom_pausentimer_dir, default_db_path
from services import atem, autostart, ccli, ccli_melden, devices, songlog, xair
from version import __version__
from services.settings import app_settings
from ui import theme as t
from ui.sync_ui import KEY_SYNC_AUTO, KEY_SYNC_TOKEN, KEY_SYNC_URL, STATUS_OFF
from ui.updater_ui import KEY_CHECK_ON_START
from services.remote_relay import device_name
from ui.recording_upload_ui import (KEY_UPLOAD_DAYS, KEY_UPLOAD_ENABLED, KEY_WP_ENABLED, KEY_WP_PASSWORD, KEY_WP_URL,
                                    KEY_WP_USER, upload_days)
from ui.web_remote_ui import KEY_DEVICE_NAME, KEY_SITE_ENABLED, KEY_SITE_TOKEN, KEY_SITE_URL
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
        self.setMinimumSize(800, 480)
        self.resize(880, 600)          # die endgültige Höhe ergibt sich aus der höchsten Seite (_fit_height)
        self.setStyleSheet(t.panel_style("Card") + t.primary_button_style("PrimaryButton"))

        self.settings = app_settings()
        self._build_ui()
        self.atem_test_done.connect(self._on_atem_test_done)
        self.ccli_ask.connect(self._on_ccli_ask)
        self.ccli_progress.connect(self._on_ccli_progress)
        self.load_settings()
        self._fit_fields()
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
    def _two_fields(*fields: QWidget) -> QWidget:
        """Mehrere Felder nebeneinander in einer Zeile (spart Platz); das erste ist etwas breiter."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.GAP)
        for index, field in enumerate(fields):
            layout.addWidget(field, 3 if index == 0 else 2)
        return row

    @staticmethod
    def _info_button(text: str) -> QToolButton:
        """Kleiner „i“-Knopf: die Erklärung erscheint beim Darüberfahren (statt als Text im Dialog)."""
        button = QToolButton()
        button.setText("i")
        button.setFixedSize(20, 20)
        button.setCursor(Qt.CursorShape.WhatsThisCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip(text)
        button.setStyleSheet(
            f"QToolButton {{ border: 1px solid {t.BORDER}; border-radius: 10px; background: transparent; "
            f"color: {t.TEXT_MUTED}; font-size: 11px; font-weight: 700; }}"
            f"QToolButton:hover {{ border-color: {t.ACCENT}; color: {t.ACCENT_LIGHT}; }}")
        return button

    @classmethod
    def _card(cls, *items, title: str = "", info: str = "") -> QFrame:
        """Rahmen mit einfacher Überschrift; längere Erklärungen stehen im „i“-Knopf (Hover)."""
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(CARD_PAD, CARD_PAD, CARD_PAD, CARD_PAD)
        layout.setSpacing(CARD_GAP)
        if title:
            header = QHBoxLayout()
            header.setSpacing(8)
            heading = QLabel(title)
            heading.setStyleSheet(f"font-size: {t.FS + 2}px; font-weight: 700; color: {t.TEXT_PRIMARY}; "
                                  "background: transparent; border: 0;")
            header.addWidget(heading)
            header.addStretch()
            if info:
                header.addWidget(cls._info_button(info))
            layout.addLayout(header)
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
        spin.setFixedSize(92, FIELD_H)            # wird nach dem Aufbau an den Inhalt angepasst (siehe _fit_fields)
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
            ("Pausentimer", self.create_pause_tab()),
            ("Audio", self.create_audio_tab()),
            ("Kamera", self.create_camera_tab()),
            ("Mischpult", self.create_atem_tab()),
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
            btn.setStyleSheet(t.pill_button_style(radius=18, font_size=13) + "QPushButton { padding: 0 10px; }")
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

    def _fit_fields(self) -> None:
        """Zahlenfelder (mit Einheit wie „ min“, „ px“, „ %“), Auswahllisten und Eingabefelder so breit machen, dass ihr
        Inhalt ganz sichtbar ist – auf Windows sind die Schriften breiter als am Mac. Gemessen wird mit der größeren von
        Widget-Schrift und Stylesheet-Schrift (halbfett), dazu ein Sicherheitszuschlag."""
        from PyQt6.QtGui import QFont, QFontMetrics
        from PyQt6.QtWidgets import QComboBox, QFontComboBox

        def width_of(widget, text: str) -> int:
            widget.ensurePolished()
            fonts = [QFont(widget.font())]
            styled = QFont(widget.font())
            styled.setPixelSize(t.FS)
            styled.setWeight(QFont.Weight.DemiBold)
            fonts.append(styled)
            return max(QFontMetrics(font).horizontalAdvance(text) for font in fonts)

        for spin in self.findChildren(QSpinBox):
            texts = [spin.prefix() + str(value) + spin.suffix() for value in (spin.minimum(), spin.maximum())]
            if spin.specialValueText():
                texts.append(spin.specialValueText())
            need = max(width_of(spin, text) for text in texts) + 12 + 34 + 24   # Innenabstand + Pfeile + Luft
            spin.setFixedWidth(max(spin.width(), need))
        for combo in self.findChildren(QComboBox):
            if isinstance(combo, QFontComboBox):        # Schriftlisten: feste, bequeme Breite (sonst sehr breit)
                continue
            widest = max((width_of(combo, combo.itemText(i)) for i in range(combo.count())), default=0)
            combo.setMinimumWidth(min(440, max(combo.minimumWidth(), widest + 12 + 40 + 16)))
        for edit in self.findChildren(QLineEdit):
            if edit.parent() is not None and isinstance(edit.parent(), (QSpinBox, QComboBox)):
                continue                                # innere Felder von Zahlenfeldern und Listen
            text = max(edit.text(), edit.placeholderText(), key=len)
            if text:
                edit.setMinimumWidth(min(280, max(edit.minimumWidth(), width_of(edit, text) + 24 + 16)))   # nicht breiter als die Seite

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
        self.open_presentations_btn = self._outline_button("Vorlagen-Ordner")
        self.open_presentations_btn.clicked.connect(self.open_presentation_folder)
        self.open_presentations_btn.setToolTip(
            "Öffnet den Ordner für deine Pausenfolien im Datei-Manager\n"
            "Hier liegen die Dateien „pausentimer_<Jahreszeit>.pptx“ (Vorlagen werden nicht mitgeliefert)")

        self.songlog_checkbox = self._checkbox("Gespielte Lieder in einer Textdatei speichern")
        self.songlog_checkbox.setToolTip(
            "Jedes Lied, das auf dem Beamer gezeigt wird, kommt mit Nummer und Titel in die Datei „Gespielte Lieder.txt“ (nach Datum geordnet)")
        self.history_btn = self._outline_button("Liedhistorie")
        self.history_btn.setToolTip("Zeigt die gespielten Lieder nach Tag, mit Suche und den am häufigsten gespielten")
        self.history_btn.clicked.connect(self.show_history)
        self.ccli_report_btn = self._outline_button("Bei CCLI melden")
        self.ccli_report_btn.setToolTip(
            "Öffnet CCLI „Suchen & Melden“ (reporting.ccli.com) in einem Browser, du loggst dich dort ein. Danach gibt das Programm\n"
            "jede CCLI-Nummer ein, sucht und klickt „Lied melden“. Nach dem ersten Lied fragt es, ob alles stimmt.\n"
            "Die Meldeliste (nur CCLI-Nummern) entsteht dabei automatisch aus den gespielten Liedern. Lieder aus den Zeiten\n"
            "unter „Nicht melden“ werden übersprungen. Gemeldetes wird nicht aufbewahrt.")
        self.ccli_report_btn.clicked.connect(self.start_ccli_report)
        self.no_report_input = self._line_edit("z. B. So 09:00–10:00; Mi 18:30–19:30")
        self.no_report_input.setToolTip(
            "In diesen Zeiten gezeigte Lieder bleiben in der Liedhistorie, werden aber nicht bei CCLI gemeldet.\n"
            "Mehrere Zeiten mit „;“ trennen. Wochentage: Mo, Di, Mi, Do, Fr, Sa, So. Leer = alles melden.")
        self.ccli_status_label = QLabel()
        self.ccli_status_label.setWordWrap(True)
        self.ccli_status_label.setStyleSheet(t.hint_style())
        self.ccli_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._show_ccli_pending()                      # wie die anderen Statuszeilen: nie leer

        self.autostart_checkbox = self._checkbox("LiedManager beim Anmelden am Computer automatisch starten")
        self.autostart_checkbox.setToolTip(
            "Startet das Programm automatisch, sobald du dich an diesem Computer anmeldest (nur für deinen Benutzer).\n"
            "Windows: Autostart-Eintrag · Mac: Anmeldeobjekt (LaunchAgent)")
        self.autostart_checkbox.setVisible(autostart.supported())

        return self._page(
            self._card(self.autostart_checkbox, title="Programmstart",
                       info="Ob LiedManager beim Anmelden am Computer von selbst startet."),
            self._card(
                self._field("Bildschirm", self.screen_combo),
                self.fullscreen_checkbox,
                title="Beamer", info="Auf diesem Bildschirm (Zweitmonitor) erscheinen Beamer-Bild und Kamera-Vollbild.",
            ),
            self._card(self.songlog_checkbox, self.history_btn,
                       title="Gespielte Lieder",
                       info="Jedes gezeigte Lied kommt mit Nummer und Titel in die Liste. Daraus entsteht die CCLI-Meldung (Reiter Remote)."),
        )

    def create_pause_tab(self):
        """Eigener Reiter: Pausenfolie (Art, Jahreszeit, Vorlage, Vorschau, Bibelvers, Ablauf, Musik, Schrift)."""
        from ui.pause_settings import PauseSettings
        self.pause_settings = PauseSettings(self)
        return self._page(*self.pause_settings.cards())

    def create_atem_tab(self):
        self.atem_enabled_checkbox = self._checkbox("Automatisch ansteuern")

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
        ip_caption = QLabel("IP-Adresse")
        ip_caption.setStyleSheet(t.caption_style())
        ip_box_layout.addWidget(ip_caption)
        ip_box_layout.addLayout(ip_row)

        self.atem_status_label = QLabel()
        self._set_atem_status("idle", "Noch nicht getestet")

        self.atem_pres_spin = self._spinbox()
        self.atem_cam_spin = self._spinbox()
        self.atem_default_spin = self._spinbox()
        self.atem_start_spin = self._spinbox(0, 20)
        self.atem_start_spin.setSpecialValueText("Schwarz")          # 0 = Schwarzbild (Black) des Mischers
        self.atem_start_spin.setToolTip("Darauf schaltet der Mischer, sobald LiedManager startet (0 = Schwarz)")
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
            ("Beim Programmstart", self.atem_start_spin),
        )
        for row, (text, spin) in enumerate(rows):
            label = QLabel(text)
            label.setStyleSheet(f"font-size: {t.FS}px; color: {t.TEXT_LABEL};")
            grid.addWidget(label, row, 0)
            grid.addWidget(spin, row, 1)

        first_items = [self.atem_enabled_checkbox]
        if not atem.available():
            missing = QLabel("ATEM-Modul (PyATEMMax) fehlt – wird beim nächsten Start installiert.")
            missing.setWordWrap(True)
            missing.setStyleSheet(t.hint_style())
            first_items.append(missing)
        first_items += [ip_box, self.atem_status_label]

        self.xair_enabled_checkbox = self._checkbox("Über die Webseite steuern")
        self.xair_enabled_checkbox.setToolTip("Lauter, leiser und Mute für die Kanäle 1 bis 8 – in der Web-Fernsteuerung im Reiter „Kamera“")
        self.xair_ip_input = self._line_edit("z. B. 192.168.10.50")
        self.xair_ip_input.setToolTip("Netzwerk-Adresse des Pults (im X AIR Edit unter Setup → Network, am besten fest vergeben)")

        return self._page(
            self._card(*first_items, title="ATEM-Mischer",
                       info="Schaltet den Mischer bei Präsentation, Pausentimer und Kameras automatisch um."),
            self._card(grid, title="ATEM-Eingänge", info="Welcher Mischer-Eingang für welchen Zweck gilt."),
            self._card(self.xair_enabled_checkbox, self._field("IP-Adresse", self.xair_ip_input), title="Behringer X AIR",
                       info="Lauter, leiser, Mute und „Alles stumm“ für die Kanäle 1–8 in der Web-Fernsteuerung. "
                            "Das Pult muss im selben Netzwerk sein. Erste Versuche bitte bei leiser Anlage."),
        )

    def create_camera_tab(self):
        self.cam1_combo = self._combo()
        self.cam2_combo = self._combo()
        self.populate_video_devices()
        self.cam1_combo.setToolTip("Videoquelle für das obere Kamerabild")
        self.cam2_combo.setToolTip("Videoquelle für das untere Kamerabild")
        return self._page(
            self._card(
                self._field("Kamera 1", self.cam1_combo),
                self._field("Kamera 2", self.cam2_combo),
                title="Kameras", info="Videoquelle für das obere und das untere Kamerabild.",
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
        path_caption = QLabel("Speicherort")
        path_caption.setStyleSheet(t.caption_style())
        path_layout.addWidget(path_caption)
        path_layout.addLayout(path_row)

        return self._page(
            self._card(
                self._field("Ausgabe (Soundkarte / PA)", self.audio_device_combo),
                self._field("Mikrofon (Aufnahme)", self.mic_device_combo),
                title="Audio", info="Über die Ausgabe laufen Piano und GL3. „Systemstandard“ = normale Ausgabe bzw. normales Mikrofon.",
            ),
            self._card(path_box, title="Aufnahmen", info="In diesem Ordner werden fertige Aufnahmen als WAV-Datei gespeichert."),
        )

    def _build_sync_card(self) -> QFrame:
        """Abgleich der Datenbank mit dem eigenen Server (gehört in den Reiter „Datenbank“)."""
        self.sync_auto_checkbox = self._checkbox("Automatisch abgleichen (beim Start und jede Minute)")
        self.sync_auto_checkbox.setToolTip(
            "Ein: Änderungen werden automatisch gesendet und geholt.\n"
            "Aus: die Verbindung bleibt eingerichtet, es wird aber nur auf Knopfdruck abgeglichen\n"
            "(Jetzt abgleichen / Alles neu hochladen).")
        self.sync_auto_checkbox.toggled.connect(self._sync_auto_toggled)
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
        self.sync_url_input.editingFinished.connect(self._apply_sync_fields)
        self.sync_token_input.editingFinished.connect(self._apply_sync_fields)
        self.sync_status_label = QLabel(STATUS_OFF)
        self.sync_status_label.setWordWrap(True)
        self.sync_status_label.setStyleSheet(t.hint_style())
        token_row = QHBoxLayout()                      # Token und die beiden Abgleich-Knöpfe in einer Reihe
        token_row.setSpacing(t.GAP)
        token_row.addWidget(self.sync_token_input, 1)
        token_row.addWidget(self.sync_now_btn)
        token_row.addWidget(self.sync_force_btn)
        token_box = QWidget()
        token_layout = QVBoxLayout(token_box)
        token_layout.setContentsMargins(0, 0, 0, 0)
        token_layout.setSpacing(6)
        token_caption = QLabel("Token")
        token_caption.setStyleSheet(t.caption_style())
        token_layout.addWidget(token_caption)
        token_layout.addLayout(token_row)
        return self._card(self.sync_auto_checkbox,
                          self._field("Server-Adresse", self.sync_url_input),
                          token_box, self.sync_status_label,
                          title="Abgleich mit Server",
                          info="Die Datenbank bleibt auf jedem Gerät lokal; über deinen Server werden nur Änderungen an den Liedern "
                               "geteilt – automatisch beim Start und danach jede Minute. Auf allen Geräten dieselbe Adresse und dasselbe Token.")

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
        db_caption = QLabel("Datei")
        db_caption.setStyleSheet(t.caption_style())
        db_layout.addWidget(db_caption)
        db_layout.addLayout(db_row)

        return self._page(
            self._card(db_box, title="Datenbank", info="Die Lieder-Datenbank (LiedManager.db) dieses Geräts."),
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

        return self._page(self._card(self.update_checkbox, update_row, title="Updates",
                                      info="Fragt beim Programmstart bei GitHub nach einer neueren Version (nur wenn online)."))

    def create_remote_tab(self):
        """Reiter „Remote“: LiedManager per Handy über die eigene Website bedienen."""
        self.site_checkbox = self._checkbox("Remote über meine Website einschalten")
        self.site_checkbox.setToolTip(
            "Verbindet LiedManager mit deiner Website (remote.php). Dann bedienst du das Programm per Handy von überall –\n"
            "mit HTTPS und PIN. LiedManager muss dafür laufen und online sein. Die PIN legst du in remote.php fest.")
        self.site_url_input = self._line_edit("https://deine-domain.de/steuerung/remote.php")
        self.site_url_input.setToolTip("Adresse von remote.php auf deiner Website (mit https://). Dieselbe Adresse öffnest du im Browser.")
        self.site_token_input = self._line_edit("Token (steht in remote.php)")
        self.site_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.site_token_input.setToolTip("Das geheime Token aus der Datei remote.php auf dem Server (mindestens 16 Zeichen).")
        self.device_name_input = self._line_edit("z. B. Kirche, Büro, Laptop")
        self.device_name_input.setToolTip(
            "Mit diesem Namen meldet sich der Computer bei der Website. Laufen mehrere Computer, wählst du im Browser\n"
            "oben aus, welcher bedient wird – Steuerung und Bilder gehen nur an diesen.")
        self.device_name_input.editingFinished.connect(self._save_device_name)
        self.site_checkbox.toggled.connect(self._site_toggled)
        self.site_url_input.editingFinished.connect(self._save_site_fields)
        self.site_token_input.editingFinished.connect(self._save_site_fields)
        self.site_status_label = QLabel(STATUS_OFF)
        self.site_status_label.setWordWrap(True)
        self.site_status_label.setStyleSheet(t.hint_style())
        self.site_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.wp_checkbox = self._checkbox("Aufnahmen automatisch in die WordPress-Mediathek hochladen")
        self.wp_checkbox.toggled.connect(self._wp_toggled)
        self.wp_url_input = self._line_edit("https://deine-domain.de")
        self.wp_url_input.setToolTip("Adresse deiner WordPress-Seite (mit https://, ohne /wp-admin)")
        self.wp_user_input = self._line_edit("WordPress-Benutzername")
        self.wp_password_input = self._line_edit("Anwendungspasswort")
        self.wp_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.wp_password_input.setToolTip("WordPress → Benutzer → Profil → „Anwendungspasswörter“: Namen eingeben (z. B. LiedManager), "
                                          "„Neues Anwendungspasswort hinzufügen“, den angezeigten Code hier einfügen.")
        for edit in (self.wp_url_input, self.wp_user_input, self.wp_password_input):
            edit.editingFinished.connect(self._save_wp_fields)
        # Nur Aufnahmen von diesen Wochentagen hochladen (z. B. nur Sonntag)
        self.upload_day_boxes = []
        days_row = QHBoxLayout()
        days_row.setSpacing(10)
        for number, short in enumerate(("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"), 1):
            box = self._checkbox(short)
            box.setToolTip(f"Aufnahmen vom {('Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag')[number - 1]} hochladen")
            box.toggled.connect(self._save_upload_days)
            box.setProperty("day", number)
            self.upload_day_boxes.append(box)
            days_row.addWidget(box)
        days_row.addStretch(1)
        self.upload_days_box = QWidget()
        days_layout = QVBoxLayout(self.upload_days_box)
        days_layout.setContentsMargins(0, 0, 0, 0)
        days_layout.setSpacing(6)
        days_caption = QLabel("Nur Aufnahmen von diesen Tagen hochladen")
        days_caption.setStyleSheet(t.caption_style())
        days_layout.addWidget(days_caption)
        days_layout.addLayout(days_row)
        self.upload_status_label = QLabel("Aus")
        self.upload_status_label.setWordWrap(True)
        self.upload_status_label.setStyleSheet(t.hint_style())
        self.upload_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return self._page(
            self._card(self.site_checkbox,
                       self._two_fields(self._field("Adresse der Website", self.site_url_input),
                                        self._field("Token", self.site_token_input),
                                        self._field("Name dieses Computers", self.device_name_input)),
                       self.site_status_label,
                       title="Remote-Steuerung",
                       info="Bedienung per Handy von überall: LiedManager verbindet sich mit deiner Website (remote.php) und holt "
                            "dort die Befehle ab. Das Programm muss laufen und online sein. Die PIN für den Browser legst du in remote.php fest."),
            self._card(self.wp_checkbox,
                       self._two_fields(self._field("WordPress-Adresse", self.wp_url_input),
                                        self._field("Benutzername", self.wp_user_input),
                                        self._field("Anwendungspasswort", self.wp_password_input)),
                       self.upload_days_box,
                       self.upload_status_label,
                       title="Aufnahmen hochladen",
                       info="Benutzer mit Rolle „Autor“ oder höher. Das Anwendungspasswort erstellst du in WordPress unter Benutzer → Profil. "
                            "Ist ffmpeg installiert, wird die Aufnahme vorher in eine kleine MP3 umgewandelt (Mono, 64 kbit/s)."),
            self._card(self.ccli_report_btn,
                       self._field("Nicht melden (Zeiten)", self.no_report_input),
                       self.ccli_status_label,
                       title="CCLI-Meldung",
                       info="Meldet die gespielten Lieder (nur CCLI-Nummern) bei CCLI „Suchen & Melden“. Lieder aus den Zeiten unter "
                            "„Nicht melden“ werden übersprungen. Voraussetzung: „Gespielte Lieder“ unter Anzeige ist eingeschaltet."),
        )

    def set_upload_status(self, text: str) -> None:
        self.upload_status_label.setText(text)

    def _save_wp_fields(self):
        s = self.settings
        s.setValue(KEY_WP_URL, self.wp_url_input.text().strip())
        s.setValue(KEY_WP_USER, self.wp_user_input.text().strip())
        s.setValue(KEY_WP_PASSWORD, self.wp_password_input.text().strip())
        s.sync()

    def _save_upload_days(self, *_args):
        days = [str(box.property("day")) for box in self.upload_day_boxes if box.isChecked()]
        if not days:                                  # mindestens ein Tag: sonst bliebe unklar, ob „keiner“ oder „alle“ gemeint ist
            sender = self.sender()
            if sender is not None:
                sender.blockSignals(True)
                sender.setChecked(True)
                sender.blockSignals(False)
                days = [str(sender.property("day"))]
        self.settings.setValue(KEY_UPLOAD_DAYS, ",".join(days))
        self.settings.sync()

    def _wp_toggled(self, on: bool):
        """Ein Schalter: Aufnahmen nach dem Speichern automatisch in die WordPress-Mediathek hochladen."""
        self._save_wp_fields()
        self.settings.setValue(KEY_WP_ENABLED, on)
        self.settings.setValue(KEY_UPLOAD_ENABLED, on)
        self.settings.sync()
        uploader = getattr(self.parent(), "uploader", None)
        if uploader is not None:
            uploader.configure()
            self.upload_status_label.setText(uploader.status)

    def set_site_status(self, text: str) -> None:
        self.site_status_label.setText(text)

    def set_sync_status(self, text: str) -> None:
        self.sync_status_label.setText(text)

    def _save_device_name(self):
        self.settings.setValue(KEY_DEVICE_NAME, self.device_name_input.text().strip())
        self.settings.sync()
        remote = getattr(self.parent(), "remote", None)
        if remote is not None and remote.site_enabled():
            remote.configure()                 # unter dem neuen Namen neu verbinden

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

    def _apply_sync_fields(self):
        """Adresse oder Token geändert: speichern und die Verbindung sofort darauf einstellen (keine Adresse = Abgleich aus)."""
        self._save_sync_fields()
        self._update_sync_buttons()
        sync = getattr(self.parent(), "sync", None)
        if sync is not None:
            sync.configure()
            self.sync_status_label.setText(sync.status)
        elif not self.sync_url_input.text().strip():
            self.sync_status_label.setText(STATUS_OFF)

    def _sync_auto_toggled(self, on: bool):
        """Automatischen Abgleich sofort ein- oder ausschalten, ohne die Verbindung zu trennen."""
        self.settings.setValue(KEY_SYNC_AUTO, on)
        self.settings.sync()
        sync = getattr(self.parent(), "sync", None)
        if sync is not None:
            sync.configure()
            self.sync_status_label.setText(sync.status)

    def _update_sync_buttons(self):
        on = bool(self.sync_url_input.text().strip())
        self.sync_auto_checkbox.setEnabled(on)
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

    def show_history(self):
        from ui.history_dialog import HistoryDialog
        HistoryDialog(self).exec()

    @staticmethod
    def _songs(count: int) -> str:
        return f"{count} Lied" if count == 1 else f"{count} Lieder"

    def _show_ccli_pending(self) -> None:
        open_count = len(ccli.read_report())
        self.ccli_status_label.setText(
            f"{open_count} CCLI-{'Nummer wartet' if open_count == 1 else 'Nummern warten'} auf die Meldung."
            if open_count else "Keine offenen CCLI-Meldungen.")

    ccli_ask = pyqtSignal(str, str)           # Titel, Text → Rückfrage im Hauptthread
    ccli_progress = pyqtSignal(str)

    def done(self, result):
        self._ccli_stop = True                      # laufende CCLI-Meldung beenden, wenn der Dialog geschlossen wird
        event = getattr(self, "_ccli_event", None)
        if event is not None:
            self._ccli_answer = "stop"
            event.set()
        super().done(result)

    def start_ccli_report(self):
        if getattr(self, "_ccli_thread", None) is not None and self._ccli_thread.is_alive():
            return
        if not ccli_melden.playwright_available():
            from paths import FROZEN
            self.ccli_status_label.setText(
                "„Bei CCLI melden“ fehlt in diesem Build (Playwright war beim Bauen nicht installiert)." if FROZEN else
                f"Dafür fehlt Playwright. Einmalig im Terminal: {ccli_melden.INSTALL_HINT}")
            return
        db = getattr(self.parent(), "db", None)
        # Meldeliste immer erst aktualisieren: neu gespielte Lieder kommen hinter noch offene Nummern
        path, _count, without = ccli.export_report(db.db_name if db is not None and db.available else None)
        todo = ccli_melden.pending(path)
        if not todo:
            self.ccli_status_label.setText("Nichts zu melden." if not without else
                                           f"Nichts zu melden – {self._songs(without)} ohne CCLI-Nummer.")
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Bei CCLI melden")
        box.setText(f"{self._songs(len(todo))} werden bei CCLI gemeldet.")
        box.setInformativeText(
            "Es öffnet sich ein Browser mit CCLI „Suchen & Melden“. Falls nötig, dort einloggen."
            + (f"\n\n{self._songs(without)} ohne CCLI-Nummer werden übersprungen." if without else ""))
        start = box.addButton("Browser öffnen", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not start:
            return
        self._ccli_stop = False
        self._ccli_answer, self._ccli_event = "", threading.Event()
        self.ccli_report_btn.setEnabled(False)
        self.ccli_status_label.setText("Browser wird geöffnet …")
        self._ccli_thread = threading.Thread(target=self._ccli_worker, args=(path,), daemon=True)
        self._ccli_thread.start()

    def _ccli_ask(self, title: str, text: str, buttons: tuple) -> str:
        """Aus dem Arbeitsthread: Rückfrage im Hauptthread stellen und auf die Antwort warten."""
        self._ccli_event.clear()
        self._ccli_buttons = buttons
        self.ccli_ask.emit(title, text)
        self._ccli_event.wait()
        return self._ccli_answer

    def _on_ccli_ask(self, title: str, text: str):
        """Rückfrage im selben Stil wie die übrigen Meldungen: kurzer Satz, Erklärung darunter, deutsche Knöpfe.
        Der letzte Knopf ist immer „Abbrechen/Aufhören“ (auch mit Esc)."""
        main, _, info = text.partition("\n")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(main)
        if info:
            box.setInformativeText(info)
        added = {}
        for index, (key, label) in enumerate(self._ccli_buttons):
            last = index == len(self._ccli_buttons) - 1
            button = box.addButton(label, QMessageBox.ButtonRole.RejectRole if last else QMessageBox.ButtonRole.AcceptRole)
            added[button] = key
            if index == 0:
                box.setDefaultButton(button)
        box.exec()
        self._ccli_answer = added.get(box.clickedButton(), self._ccli_buttons[-1][0])
        self._ccli_event.set()

    def _ccli_worker(self, path):
        try:
            counts = ccli_melden.run(
                path,
                wait_login=lambda: self._ccli_ask(
                    "Bei CCLI melden", "Bist du bei CCLI eingeloggt?\n"
                    "Im Browser ist CCLI „Suchen & Melden“ geöffnet. Falls nötig, dort einloggen – danach hier „Weiter“.",
                    (("ok", "Weiter"), ("stop", "Abbrechen"))) == "ok",
                after_first=lambda number, status: self._ccli_ask(
                    "Bei CCLI melden", f"CCLI-Nummer {number} wurde gemeldet.\n"
                    "Bitte im Browser prüfen, ob das richtige Lied gemeldet ist.",
                    (("next", "Weiter"), ("auto", "Rest automatisch"), ("stop", "Aufhören"))),
                progress=lambda i, n, text: self.ccli_progress.emit(f"{i}/{n} {text}"),
                should_stop=lambda: self._ccli_stop)
            summary = f"{counts['gemeldet']} gemeldet, {counts['fehler']} Fehler, {counts['offen']} offen."
        except ccli_melden.MeldenError as exc:
            summary = str(exc)
        except Exception as exc:
            summary = f"Meldung abgebrochen: {exc}"
        self.ccli_progress.emit("\x00" + summary)

    def _on_ccli_progress(self, text: str):
        if text.startswith("\x00"):
            self.ccli_status_label.setText(text[1:])
            self.ccli_report_btn.setEnabled(True)
        else:
            self.ccli_status_label.setText(text)

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
        self.pause_settings.load()
        self.songlog_checkbox.setChecked(s.value(songlog.KEY_ENABLED, True, type=bool))
        self.autostart_checkbox.setChecked(autostart.is_enabled())      # Zustand direkt beim System nachsehen
        self.no_report_input.setText(songlog.format_windows(songlog.no_report_windows()))

        self.atem_enabled_checkbox.setChecked(s.value("atem_enabled", False, type=bool))
        self.atem_ip_input.setText(s.value("atem_ip", "", type=str))
        self.xair_enabled_checkbox.setChecked(s.value(xair.KEY_ENABLED, False, type=bool))
        self.xair_ip_input.setText(s.value(xair.KEY_IP, "", type=str))
        self.atem_pres_spin.setValue(s.value("atem_pres_channel", 3, type=int))
        self.atem_cam_spin.setValue(s.value("atem_cam_channel", 4, type=int))
        self.atem_default_spin.setValue(s.value("atem_default_channel", 1, type=int))
        self.atem_start_spin.setValue(s.value("atem_start_channel", 0, type=int))

        self._select_data(self.audio_device_combo, s.value(devices.KEY_OUTPUT, "", type=str))
        self._select_data(self.mic_device_combo, s.value(devices.KEY_INPUT, "", type=str))
        self.rec_path_input.setText(s.value("recording_path", "", type=str))
        self.update_checkbox.setChecked(s.value(KEY_CHECK_ON_START, True, type=bool))
        self.db_path_input.setText(s.value("database_path", "", type=str))
        self.sync_url_input.setText(s.value(KEY_SYNC_URL, "", type=str))
        self.sync_token_input.setText(s.value(KEY_SYNC_TOKEN, "", type=str))
        self.sync_auto_checkbox.blockSignals(True)
        self.sync_auto_checkbox.setChecked(s.value(KEY_SYNC_AUTO, True, type=bool))
        self.sync_auto_checkbox.blockSignals(False)
        self._update_sync_buttons()
        self.site_checkbox.blockSignals(True)
        self.site_checkbox.setChecked(s.value(KEY_SITE_ENABLED, False, type=bool))
        self.device_name_input.setText(device_name())
        self.site_checkbox.blockSignals(False)
        self.wp_checkbox.blockSignals(True)
        self.wp_checkbox.setChecked(s.value(KEY_WP_ENABLED, False, type=bool) and s.value(KEY_UPLOAD_ENABLED, False, type=bool))
        self.wp_checkbox.blockSignals(False)
        self.wp_url_input.setText(s.value(KEY_WP_URL, "", type=str))
        chosen = upload_days()
        for box in self.upload_day_boxes:
            box.blockSignals(True)
            box.setChecked(box.property("day") in chosen)
            box.blockSignals(False)
        self.wp_user_input.setText(s.value(KEY_WP_USER, "", type=str))
        self.wp_password_input.setText(s.value(KEY_WP_PASSWORD, "", type=str))
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
        self.pause_settings.save()
        s.setValue(songlog.KEY_ENABLED, self.songlog_checkbox.isChecked())
        try:
            windows = songlog.parse_windows(self.no_report_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Nicht melden (Zeiten)", f"{exc}\n\nDie bisherigen Zeiten bleiben gespeichert.")
        else:
            s.setValue(songlog.KEY_NO_REPORT, songlog.format_windows(windows))
        if autostart.supported() and self.autostart_checkbox.isChecked() != autostart.is_enabled():
            problem = autostart.set_enabled(self.autostart_checkbox.isChecked())
            if problem:
                QMessageBox.warning(self, "Autostart", f"Der Autostart konnte nicht geändert werden:\n{problem}")

        s.setValue("atem_enabled", self.atem_enabled_checkbox.isChecked())
        s.setValue("atem_ip", self.atem_ip_input.text().strip())
        s.setValue(xair.KEY_ENABLED, self.xair_enabled_checkbox.isChecked())
        s.setValue(xair.KEY_IP, self.xair_ip_input.text().strip())
        s.setValue("atem_pres_channel", self.atem_pres_spin.value())
        s.setValue("atem_cam_channel", self.atem_cam_spin.value())
        s.setValue("atem_default_channel", self.atem_default_spin.value())
        s.setValue("atem_start_channel", self.atem_start_spin.value())

        s.setValue(devices.KEY_OUTPUT, self.audio_device_combo.currentData() or "")
        s.setValue(devices.KEY_INPUT, self.mic_device_combo.currentData() or "")
        s.setValue("recording_path", self.rec_path_input.text().strip())
        s.setValue("database_path", self.db_path_input.text().strip())
        s.setValue(KEY_SYNC_URL, self.sync_url_input.text().strip())
        s.setValue(KEY_SYNC_TOKEN, self.sync_token_input.text().strip())
        s.setValue(KEY_SYNC_AUTO, self.sync_auto_checkbox.isChecked())
        s.setValue(KEY_SITE_ENABLED, self.site_checkbox.isChecked())
        s.setValue(KEY_DEVICE_NAME, self.device_name_input.text().strip())
        s.setValue(KEY_SITE_URL, self.site_url_input.text().strip())
        s.setValue(KEY_SITE_TOKEN, self.site_token_input.text().strip())
        s.setValue(KEY_CHECK_ON_START, self.update_checkbox.isChecked())

        s.setValue("camera_1_name", self.cam1_combo.currentText())
        s.setValue("camera_2_name", self.cam2_combo.currentText())
        s.sync()
        xair.configure()                       # Mischpult-Verbindung mit den neuen Einstellungen starten/stoppen
        self.accept()
