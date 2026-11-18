"""Reiter „Kamera“: die zwei Kamerabilder und die dauerhafte Ausgabe auf einem festen Bildschirm."""

from PyQt6.QtMultimedia import QMediaDevices
from PyQt6.QtWidgets import QApplication, QMessageBox

from services.screens import screen_label


class CameraTab:
    """Teil von ``SettingsDialog`` (Mixin): baut die Karten dieses Reiters und reagiert auf seine Felder."""

    def create_camera_tab(self):
        self.cam1_combo = self._device_combo()
        self.cam2_combo = self._device_combo()
        self.populate_video_devices()
        self.cam1_combo.setToolTip("Oberes Kamerabild")
        self.cam2_combo.setToolTip("Unteres Kamerabild")
        cameras = self._card(self._two_fields(self._field("Kamera 1 (oben)", self.cam1_combo),
                                              self._field("Kamera 2 (unten)", self.cam2_combo), equal=True), title="Kameras")

        # Dauerhafte Ausgabe: eine Kamera ständig im Vollbild auf einem festen Bildschirm
        self.permanent_camera_combo = self._combo()
        self.permanent_camera_combo.addItem("Aus", 0)
        self.permanent_camera_combo.addItem("Kamera 1 (oben)", 1)
        self.permanent_camera_combo.addItem("Kamera 2 (unten)", 2)
        self.permanent_camera_combo.setToolTip("Diese Kamera läuft ständig im Vollbild")
        self.permanent_screen_combo = self._device_combo()
        for index, screen in enumerate(QApplication.screens()):
            self.permanent_screen_combo.addItem(screen_label(index, screen), screen.name())
        self.permanent_screen_combo.setToolTip("Bildschirm für die dauerhafte Ausgabe")
        self.permanent_camera_combo.currentIndexChanged.connect(
            lambda _i: self.permanent_screen_combo.setEnabled(bool(self.permanent_camera_combo.currentData())))
        permanent = self._card(
            self._two_fields(self._field("Kamera", self.permanent_camera_combo),
                             self._field("Bildschirm", self.permanent_screen_combo), equal=True),
            title="Dauerhafte Ausgabe",
            info="Die gewählte Kamera läuft ständig im Vollbild auf diesem Bildschirm, unabhängig vom Beamer: "
                 "Esc schließt sie nicht. Ist es der Beamer-Bildschirm, erscheinen Lieder, Bilder und die "
                 "Pausenfolie davor. Ist der Bildschirm nicht angeschlossen, wird nichts ausgegeben.")
        return cameras, permanent

    def populate_video_devices(self):
        self.cam1_combo.addItem("Keine Kamera", userData=None)
        self.cam2_combo.addItem("Keine Kamera", userData=None)
        for device in QMediaDevices.videoInputs():
            name = device.description()
            self.cam1_combo.addItem(name, userData=device)
            self.cam2_combo.addItem(name, userData=device)

    def _confirm_permanent_screen(self) -> bool:
        """Warnt, wenn die dauerhafte Ausgabe das Hauptfenster verdecken würde. ``False`` = nicht speichern."""
        if not self.permanent_camera_combo.currentData():
            return True
        name = self.permanent_screen_combo.currentData() or ""
        main = self.parent()
        main_screen = main.screen() if main is not None else None
        if main_screen is None or main_screen.name() != name:
            return True
        answer = QMessageBox.question(
            self, "Dauerhafte Ausgabe",
            "Auf diesem Bildschirm liegt das Hauptfenster von LiedManager. Die Kamera würde es verdecken.\n\n"
            "Trotzdem speichern?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes
