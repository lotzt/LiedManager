"""Einstellungsdialog: setzt die Reiter (je eine Datei in ``ui/settings/``) zusammen, lädt und speichert die Werte."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QStackedWidget, QVBoxLayout,
)

from services import autostart, devices, screens, songlog, xair
from services.remote_relay import device_name
from services.settings import app_settings
from services.settings_keys import (
    KEY_AUDIO_1_NAME, KEY_AUDIO_2_NAME,
    KEY_ATEM_CAM_CHANNEL, KEY_ATEM_DEFAULT_CHANNEL, KEY_ATEM_ENABLED, KEY_ATEM_IP, KEY_ATEM_PRES_CHANNEL,
    KEY_ATEM_START_CHANNEL, KEY_CAMERA_1_NAME, KEY_CAMERA_2_NAME, KEY_DATABASE_PATH, KEY_FULLSCREEN_MODE,
    KEY_PRESENTATION_SEASON, KEY_RECORDING_PATH,
)
from ui import theme as t
from ui.camera_panel import KEY_PERMANENT_CAMERA, KEY_PERMANENT_SCREEN
from ui.recording_upload_ui import (
    KEY_UPLOAD_ENABLED, KEY_WP_ENABLED, KEY_WP_PASSWORD, KEY_WP_URL, KEY_WP_USER, upload_days,
)
from ui.settings.audio import AudioTab
from ui.settings.camera import CameraTab
from ui.settings.form import FIELD_H, FormBuilder
from ui.settings.general import GeneralTab
from ui.settings.mixer import MixerTab
from ui.settings.remote import RemoteTab
from ui.settings.songs import SongsTab
from ui.sync_ui import KEY_SYNC_AUTO, KEY_SYNC_TOKEN, KEY_SYNC_URL
from ui.updater_ui import KEY_CHECK_ON_START
from ui.web_remote_ui import KEY_DEVICE_NAME, KEY_SITE_ENABLED, KEY_SITE_TOKEN, KEY_SITE_URL
from version import __version__


class SettingsDialog(QDialog, FormBuilder, GeneralTab, SongsTab, AudioTab, CameraTab, MixerTab, RemoteTab):
    """Einstellungsdialog: Allgemein, Pausentimer, Lieder, Audio, Kamera, Mischpult, Remote."""

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
        display = self.create_display_tab()
        pause = self.create_pause_tab()              # nach der Anzeige: nutzt die Jahreszeit-Liste von dort
        audio = self.create_audio_tab()
        upload_items = self.create_upload_items()
        cameras = self.create_camera_tab()
        mixer = self.create_atem_tab()
        data = self.create_data_tab()
        songlog = self.create_songlog_cards()
        remote = self.create_remote_tab()
        update_items = self.create_update_tab()
        program = self._card(self.autostart_checkbox, *update_items, title="Programm")
        recordings = self._card(audio["path"], *upload_items, title="Aufnahmen",
                                info="Speicherort der WAV-Dateien. Hochladen: WordPress-Benutzer ab Rolle „Autor“; "
                                     "mit ffmpeg wird vorher eine kleine MP3 erstellt.")
        entries = (
            ("Allgemein", self._page(program, display["beamer"])),
            ("Pausentimer", self._page(self._subtabs(*pause))),
            ("Lieder", self._page(self._subtabs(("Datenbank", data["db"], data["sync"]),
                                                ("Gespielte Lieder", songlog["songlog"], songlog["ccli"])))),
            ("Audio", self._page(audio["devices"], recordings)),
            ("Kamera", self._page(*cameras)),
            ("Mischpult", self._page(mixer["atem"], mixer["xair"])),   # Video- und Tonmischer an einer Stelle
            ("Remote", self._page(remote["remote"])),
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
            if combo.property("no_fit"):               # Gerätelisten: gleich breite Felder, lange Namen gekürzt
                continue
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
        """Macht den Dialog so hoch, dass die höchste Seite ganz zu sehen ist und nicht gescrollt werden muss.
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

    ccli_ask = pyqtSignal(str, str)           # Titel, Text → Rückfrage im Hauptthread
    ccli_progress = pyqtSignal(str)

    def done(self, result):
        self._ccli_stop = True                      # laufende CCLI-Meldung beenden, wenn der Dialog geschlossen wird
        event = getattr(self, "_ccli_event", None)
        if event is not None:
            self._ccli_answer = "stop"
            event.set()
        super().done(result)

    def load_settings(self):
        s = self.settings
        self._select_data(self.screen_combo, screens.beamer_screen().name())
        self.fullscreen_checkbox.setChecked(s.value(KEY_FULLSCREEN_MODE, True, type=bool))
        self._select_data(self.season_combo, s.value(KEY_PRESENTATION_SEASON, "frühling", type=str))
        self.pause_settings.load()
        self.songlog_checkbox.setChecked(s.value(songlog.KEY_ENABLED, True, type=bool))
        self.autostart_checkbox.setChecked(autostart.is_enabled())      # Zustand direkt beim System nachsehen
        self.no_report_input.setText(songlog.format_windows(songlog.no_report_windows()))

        self.atem_enabled_checkbox.setChecked(s.value(KEY_ATEM_ENABLED, False, type=bool))
        self.atem_ip_input.setText(s.value(KEY_ATEM_IP, "", type=str))
        self.xair_enabled_checkbox.setChecked(s.value(xair.KEY_ENABLED, False, type=bool))
        self.xair_ip_input.setText(s.value(xair.KEY_IP, "", type=str))
        self.atem_pres_spin.setValue(s.value(KEY_ATEM_PRES_CHANNEL, 3, type=int))
        self.atem_cam_spin.setValue(s.value(KEY_ATEM_CAM_CHANNEL, 4, type=int))
        self.atem_default_spin.setValue(s.value(KEY_ATEM_DEFAULT_CHANNEL, 1, type=int))
        self.atem_start_spin.setValue(s.value(KEY_ATEM_START_CHANNEL, 0, type=int))

        self._select_data(self.audio_device_combo, s.value(devices.KEY_OUTPUT, "", type=str))
        self._select_data(self.mic_device_combo, s.value(devices.KEY_INPUT, "", type=str))
        self.audio1_name_input.setText(s.value(KEY_AUDIO_1_NAME, "", type=str))
        self.audio2_name_input.setText(s.value(KEY_AUDIO_2_NAME, "", type=str))
        self.rec_path_input.setText(s.value(KEY_RECORDING_PATH, "", type=str))
        self.update_checkbox.setChecked(s.value(KEY_CHECK_ON_START, True, type=bool))
        self.db_path_input.setText(s.value(KEY_DATABASE_PATH, "", type=str))
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

        self._select_data(self.permanent_camera_combo, s.value(KEY_PERMANENT_CAMERA, 0, type=int))
        saved_screen = s.value(KEY_PERMANENT_SCREEN, "", type=str)
        if saved_screen and self.permanent_screen_combo.findData(saved_screen) < 0:
            # gespeicherter Bildschirm gerade nicht angeschlossen: trotzdem zeigen, damit die Wahl erhalten bleibt
            self.permanent_screen_combo.addItem(f"{saved_screen} (nicht angeschlossen)", saved_screen)
        self._select_data(self.permanent_screen_combo, saved_screen)
        self.permanent_screen_combo.setEnabled(bool(self.permanent_camera_combo.currentData()))

    def save_and_close(self):
        if not self._confirm_permanent_screen():     # zuerst fragen, damit bei „Nein“ nichts halb gespeichert ist
            return
        s = self.settings
        screens.save_beamer_screen(self.screen_combo.currentData() or "")
        s.setValue(KEY_FULLSCREEN_MODE, self.fullscreen_checkbox.isChecked())
        s.setValue(KEY_PRESENTATION_SEASON, self.season_combo.currentData())
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

        s.setValue(KEY_ATEM_ENABLED, self.atem_enabled_checkbox.isChecked())
        s.setValue(KEY_ATEM_IP, self.atem_ip_input.text().strip())
        s.setValue(xair.KEY_ENABLED, self.xair_enabled_checkbox.isChecked())
        s.setValue(xair.KEY_IP, self.xair_ip_input.text().strip())
        s.setValue(KEY_ATEM_PRES_CHANNEL, self.atem_pres_spin.value())
        s.setValue(KEY_ATEM_CAM_CHANNEL, self.atem_cam_spin.value())
        s.setValue(KEY_ATEM_DEFAULT_CHANNEL, self.atem_default_spin.value())
        s.setValue(KEY_ATEM_START_CHANNEL, self.atem_start_spin.value())

        s.setValue(devices.KEY_OUTPUT, self.audio_device_combo.currentData() or "")
        s.setValue(devices.KEY_INPUT, self.mic_device_combo.currentData() or "")
        s.setValue(KEY_AUDIO_1_NAME, self.audio1_name_input.text().strip())
        s.setValue(KEY_AUDIO_2_NAME, self.audio2_name_input.text().strip())
        s.setValue(KEY_RECORDING_PATH, self.rec_path_input.text().strip())
        s.setValue(KEY_DATABASE_PATH, self.db_path_input.text().strip())
        s.setValue(KEY_SYNC_URL, self.sync_url_input.text().strip())
        s.setValue(KEY_SYNC_TOKEN, self.sync_token_input.text().strip())
        s.setValue(KEY_SYNC_AUTO, self.sync_auto_checkbox.isChecked())
        s.setValue(KEY_SITE_ENABLED, self.site_checkbox.isChecked())
        s.setValue(KEY_DEVICE_NAME, self.device_name_input.text().strip())
        s.setValue(KEY_SITE_URL, self.site_url_input.text().strip())
        s.setValue(KEY_SITE_TOKEN, self.site_token_input.text().strip())
        s.setValue(KEY_CHECK_ON_START, self.update_checkbox.isChecked())

        s.setValue(KEY_CAMERA_1_NAME, self.cam1_combo.currentText())
        s.setValue(KEY_CAMERA_2_NAME, self.cam2_combo.currentText())
        s.setValue(KEY_PERMANENT_CAMERA, self.permanent_camera_combo.currentData() or 0)
        s.setValue(KEY_PERMANENT_SCREEN, self.permanent_screen_combo.currentData() or "")
        s.sync()
        xair.configure()                       # Mischpult-Verbindung mit den neuen Einstellungen starten/stoppen
        self.accept()
