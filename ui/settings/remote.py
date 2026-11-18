"""Reiter „Remote“: LiedManager per Handy über die eigene Website bedienen."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QLineEdit

from ui import theme as t
from ui.sync_ui import STATUS_OFF
from ui.web_remote_ui import KEY_DEVICE_NAME, KEY_SITE_ENABLED, KEY_SITE_TOKEN, KEY_SITE_URL


class RemoteTab:
    """Teil von ``SettingsDialog`` (Mixin): baut die Karten dieses Reiters und reagiert auf seine Felder."""

    def create_remote_tab(self):
        """Reiter „Remote“: LiedManager per Handy über die eigene Website bedienen."""
        self.site_checkbox = self._checkbox("Remote-Steuerung einschalten")
        self.site_checkbox.setToolTip("Bedienung per Handy über die Website")
        self.site_url_input = self._line_edit("https://deine-domain.de/steuerung/remote.php")
        self.site_url_input.setToolTip("Adresse von remote.php")
        self.site_token_input = self._line_edit("Token (steht in remote.php)")
        self.site_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.site_token_input.setToolTip("Token aus remote.php")
        self.device_name_input = self._line_edit("z. B. Kirche, Büro, Laptop")
        self.device_name_input.setToolTip("Name dieses Computers in der Fernsteuerung")
        self.device_name_input.editingFinished.connect(self._save_device_name)
        self.site_checkbox.toggled.connect(self._site_toggled)
        self.site_url_input.editingFinished.connect(self._save_site_fields)
        self.site_token_input.editingFinished.connect(self._save_site_fields)
        self.site_status_label = QLabel(STATUS_OFF)
        self.site_status_label.setWordWrap(True)
        self.site_status_label.setStyleSheet(t.hint_style())
        self.site_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return {
            "remote": self._card(self.site_checkbox,
                                 self._two_fields(self._field("Adresse der Website", self.site_url_input),
                                                  self._field("Token", self.site_token_input),
                                                  self._field("Name dieses Computers", self.device_name_input)),
                                 self.site_status_label,
                                 title="Remote-Steuerung",
                                 info="Bedienung per Handy. LiedManager muss laufen; die PIN steht in remote.php."),
        }

    def set_site_status(self, text: str) -> None:
        self.site_status_label.setText(text)

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
