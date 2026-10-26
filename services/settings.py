"""Gemeinsamer Zugriff auf die Programmeinstellungen (eine einzige QSettings-Instanz).

Geheimnisse (Token, Passwörter) liegen nicht im Klartext in den Einstellungen, sondern im Schlüsselbund des Systems
(macOS: Schlüsselbund, Windows: Anmeldeinformationsverwaltung) – sofern das Paket ``keyring`` vorhanden ist. Ohne
Schlüsselbund (oder im Testmodus) bleibt es bei den Einstellungen. Alte Klartext-Werte wandern beim ersten Lesen automatisch
in den Schlüsselbund und werden aus den Einstellungen gelöscht. Der übrige Code merkt davon nichts: ``value()`` und
``setValue()`` funktionieren wie gewohnt.
"""
import logging
import os

from PyQt6.QtCore import QSettings

log = logging.getLogger(__name__)

ORGANIZATION = "LiedManager"
APPLICATION = "ChurchService"
TEST_DIR_ENV = "LIEDMANAGER_SETTINGS_DIR"   # nur für Tests: Einstellungen in dieser Ordner-Datei statt in den echten
KEYCHAIN_SERVICE = "LiedManager"
SECRET_KEYS = frozenset({"sync_token", "web_site_token", "recording_wp_password"})

_settings = None
_keyring = None          # None = noch nicht geprüft, False = nicht verfügbar


def _keychain():
    """Das ``keyring``-Modul, wenn es einen echten Schlüsselbund gibt, sonst ``None``."""
    global _keyring
    if _keyring is None:
        _keyring = False
        if not os.environ.get(TEST_DIR_ENV):
            try:
                import keyring
                from keyring.backends import fail
                if not isinstance(keyring.get_keyring(), fail.Keyring):
                    _keyring = keyring
            except Exception:
                log.info("Kein Schlüsselbund verfügbar – Token und Passwörter bleiben in den Einstellungen.")
    return _keyring or None


class _Settings(QSettings):
    def value(self, key, defaultValue=None, type=None):
        kind = type
        if key in SECRET_KEYS:
            keychain = _keychain()
            if keychain is not None:
                try:
                    secret = keychain.get_password(KEYCHAIN_SERVICE, key)
                    if secret is None:                               # noch nicht umgezogen: alten Klartext übernehmen
                        old = super().value(key, "", str)
                        if old:
                            keychain.set_password(KEYCHAIN_SERVICE, key, str(old))
                            super().remove(key)
                            secret = str(old)
                    if secret is not None:
                        return secret
                except Exception:
                    log.warning("Schlüsselbund nicht lesbar – es wird der Wert aus den Einstellungen genommen.", exc_info=True)
        if kind is None:
            return super().value(key, defaultValue)
        return super().value(key, defaultValue, kind)

    def setValue(self, key, value):
        if key in SECRET_KEYS:
            keychain = _keychain()
            if keychain is not None:
                try:
                    if value in (None, ""):
                        try:
                            keychain.delete_password(KEYCHAIN_SERVICE, key)
                        except Exception:
                            pass                                       # war nicht gespeichert
                    else:
                        keychain.set_password(KEYCHAIN_SERVICE, key, str(value))
                    super().remove(key)                                # kein Klartext zurücklassen
                    return
                except Exception:
                    log.warning("Schlüsselbund nicht beschreibbar – Wert bleibt in den Einstellungen.", exc_info=True)
        super().setValue(key, value)


def app_settings() -> QSettings:
    """Liefert immer dieselbe Instanz, damit Änderungen (z. B. aus dem Einstellungsdialog) sofort überall sichtbar sind."""
    global _settings
    if _settings is None:
        folder = os.environ.get(TEST_DIR_ENV)
        if folder:       # macOS (Preferences) und Windows (Registry) lassen sich per QSettings.setPath nicht umlenken
            _settings = _Settings(os.path.join(folder, "liedmanager-test.ini"), QSettings.Format.IniFormat)
        else:
            _settings = _Settings(ORGANIZATION, APPLICATION)
    return _settings
