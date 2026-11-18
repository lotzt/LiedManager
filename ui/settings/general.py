"""Reiter „Allgemein“: Programm (Autostart, Updates) und Beamer-Bildschirm; dazu der Reiter „Pausentimer“."""

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel

from paths import custom_pausentimer_dir
from services import autostart, screens
from ui import theme as t
from version import __version__


class GeneralTab:
    """Teil von ``SettingsDialog`` (Mixin): baut die Karten dieses Reiters und reagiert auf seine Felder."""

    def create_display_tab(self):
        self.screen_combo = self._combo()
        self.populate_screens()
        self.fullscreen_checkbox = self._checkbox("Im Vollbild zeigen")
        self.fullscreen_checkbox.setChecked(True)
        self.screen_combo.setToolTip("Bildschirm für Beamer und Kamera-Vollbild")
        self.fullscreen_checkbox.setToolTip("Aus: normales Fenster")

        self.season_combo = self._combo()
        for label, key in (("Frühling", "frühling"), ("Sommer", "sommer"),
                           ("Herbst", "herbst"), ("Winter", "winter")):
            self.season_combo.addItem(label, key)
        self.season_combo.setToolTip("Welche Pausenfolie gilt")
        self.open_presentations_btn = self._outline_button("Vorlagen-Ordner")
        self.open_presentations_btn.clicked.connect(self.open_presentation_folder)
        self.open_presentations_btn.setToolTip("Ordner der Pausenfolien öffnen")

        self.autostart_checkbox = self._checkbox("Beim Anmelden automatisch starten")
        self.autostart_checkbox.setToolTip("Startet beim Anmelden am Computer")
        self.autostart_checkbox.setVisible(autostart.supported())

        return {
            "beamer": self._card(self._inline(self._field("Bildschirm", self.screen_combo), self.fullscreen_checkbox),
                                 title="Beamer"),
        }

    def create_pause_tab(self):
        """Eigener Reiter: Pausenfolie (Art, Jahreszeit, Vorlage, Vorschau, Bibelvers, Ablauf, Musik, Schrift)."""
        from ui.pause_settings import PauseSettings
        self.pause_settings = PauseSettings(self)
        return self.pause_settings.cards()

    def create_update_tab(self):
        self.update_checkbox = self._checkbox("Beim Start nach Updates suchen")
        self.update_checkbox.setToolTip("Fragt bei GitHub nach neuen Versionen")
        self.update_check_btn = self._outline_button("Jetzt nach Updates suchen")
        self.update_check_btn.setToolTip("Sofort prüfen")
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

        return [self.update_checkbox, update_row]       # steht in der Karte „Programm“ (Reiter Allgemein)

    def set_update_status(self, text: str) -> None:
        self.update_status_label.setText(text)

    def populate_screens(self):
        for index, screen in enumerate(QApplication.screens()):
            self.screen_combo.addItem(screens.screen_label(index, screen), screen.name())

    def open_presentation_folder(self):
        folder = custom_pausentimer_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
