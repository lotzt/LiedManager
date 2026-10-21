"""Gemeinsamer Zugriff auf die Programmeinstellungen (eine einzige QSettings-Instanz)."""
import os

from PyQt6.QtCore import QSettings

ORGANIZATION = "LiedManager"
APPLICATION = "ChurchService"
TEST_DIR_ENV = "LIEDMANAGER_SETTINGS_DIR"   # nur für Tests: Einstellungen in dieser Ordner-Datei statt in den echten

_settings = None


def app_settings() -> QSettings:
    """Liefert immer dieselbe Instanz, damit Änderungen (z. B. aus dem Einstellungsdialog) sofort überall sichtbar sind."""
    global _settings
    if _settings is None:
        folder = os.environ.get(TEST_DIR_ENV)
        if folder:       # macOS (Preferences) und Windows (Registry) lassen sich per QSettings.setPath nicht umlenken
            _settings = QSettings(os.path.join(folder, "liedmanager-test.ini"), QSettings.Format.IniFormat)
        else:
            _settings = QSettings(ORGANIZATION, APPLICATION)
    return _settings
