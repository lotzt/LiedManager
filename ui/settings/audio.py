"""Reiter „Audio“: Ausgabe- und Eingabegerät, Aufnahmen (Speicherort, Hochladen nach WordPress)."""
import os

from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtMultimedia import QMediaDevices
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from services import devices
from ui import theme as t
from ui.recording_upload_ui import (
    KEY_UPLOAD_DAYS, KEY_UPLOAD_ENABLED, KEY_WP_ENABLED, KEY_WP_PASSWORD, KEY_WP_URL, KEY_WP_USER,
)


class AudioTab:
    """Teil von ``SettingsDialog`` (Mixin): baut die Karten dieses Reiters und reagiert auf seine Felder."""

    def create_audio_tab(self):
        self.audio_device_combo = self._device_combo()
        self.mic_device_combo = self._device_combo()
        self.populate_audio_devices()
        self.audio_device_combo.setToolTip("Für die Audiodateien der Lieder und den Gong")
        self.mic_device_combo.setToolTip("Für Aufnahmen")

        default_dir = os.path.join(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation),
            "LiedManager Aufnahmen",
        )
        self.rec_path_input = self._line_edit(default_dir)
        self.rec_path_browse_btn = self._outline_button("Durchsuchen …")
        self.rec_path_browse_btn.clicked.connect(self.browse_recording_path)
        self.rec_path_input.setToolTip("Ordner für die Aufnahmen")
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

        self.audio1_name_input = self._line_edit("Audio 1")
        self.audio2_name_input = self._line_edit("Audio 2")
        self.audio1_name_input.setToolTip("Name der ersten Audiospur eines Lieds, z. B. „Piano“")
        self.audio2_name_input.setToolTip("Name der zweiten Audiospur eines Lieds, z. B. „Gesang“")
        return {
            "devices": self._card(self._two_fields(self._field("Ausgabe (Lieder-Audio, Gong)", self.audio_device_combo),
                                                   self._field("Eingabe (Mikrofon)", self.mic_device_combo), equal=True),
                                  self._two_fields(self._field("Name Audio 1", self.audio1_name_input),
                                                   self._field("Name Audio 2", self.audio2_name_input), equal=True),
                                  title="Audio", info="„Systemstandard“ = normales Gerät des Computers. Die Namen stehen "
                                                      "auf den Audio-Knöpfen im Programm und in der Remote-Steuerung."),
            "path": path_box,               # kommt in die Karte „Aufnahmen“ (zusammen mit dem Hochladen)
        }

    def populate_audio_devices(self):
        self.audio_device_combo.addItem("Systemstandard", "")
        for device in QMediaDevices.audioOutputs():
            self.audio_device_combo.addItem(device.description(), devices.device_key(device))
        self.mic_device_combo.addItem("Systemstandard", "")
        for device in QMediaDevices.audioInputs():
            self.mic_device_combo.addItem(device.description(), devices.device_key(device))

    def browse_recording_path(self):
        path = QFileDialog.getExistingDirectory(
            self, "Speicherort für Aufnahmen auswählen", self.rec_path_input.text()
        )
        if path:
            self.rec_path_input.setText(path)

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

    def create_upload_items(self) -> list:
        """Hochladen der Aufnahmen in die WordPress-Mediathek (steht in der Karte „Aufnahmen“)."""
        self.wp_checkbox = self._checkbox("Automatisch in die WordPress-Mediathek hochladen")
        self.wp_checkbox.toggled.connect(self._wp_toggled)
        self.wp_url_input = self._line_edit("https://deine-domain.de")
        self.wp_url_input.setToolTip("Ohne /wp-admin")
        self.wp_user_input = self._line_edit("WordPress-Benutzername")
        self.wp_password_input = self._line_edit("Anwendungspasswort")
        self.wp_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.wp_password_input.setToolTip("WordPress → Profil → Anwendungspasswörter")
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
        days_caption = QLabel("Nur von diesen Tagen")
        days_caption.setStyleSheet(t.caption_style())
        days_layout.addWidget(days_caption)
        days_layout.addLayout(days_row)
        self.upload_status_label = QLabel("Aus")
        self.upload_status_label.setWordWrap(True)
        self.upload_status_label.setStyleSheet(t.hint_style())
        self.upload_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return [self.wp_checkbox,
                       self._two_fields(self._field("WordPress-Adresse", self.wp_url_input),
                                        self._field("Benutzername", self.wp_user_input),
                                        self._field("Anwendungspasswort", self.wp_password_input)),
                       self.upload_days_box,
                       self.upload_status_label]
