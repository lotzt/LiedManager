"""Bildschirme für Beamer und dauerhafte Kamera-Ausgabe.

Gespeichert wird der **Name** des Bildschirms (``QScreen.name()``), nicht seine Nummer: Die Nummern ändern sich, wenn
Bildschirme anders angesteckt werden oder der Computer neu startet – dann landete das Lied sonst auf dem falschen Bild.
Die Nummer wird zusätzlich weiter geschrieben, damit ältere Versionen dieselbe Einstellung lesen können.
"""
from PyQt6.QtWidgets import QApplication

from services.settings import app_settings

KEY_BEAMER_SCREEN = "beamer_screen"              # Nummer (alt, nur noch Ersatz und für ältere Versionen)
KEY_BEAMER_SCREEN_NAME = "beamer_screen_name"    # Name des Bildschirms (maßgeblich)


def find_screen(name: str):
    """Bildschirm mit diesem Namen oder ``None``."""
    if not name:
        return None
    for screen in QApplication.screens():
        if screen.name() == name:
            return screen
    return None


def screen_label(index: int, screen) -> str:
    """Anzeige in den Auswahllisten, z. B. „Bildschirm 2 (1920×1080) – HDMI-1“."""
    geo = screen.geometry()
    return f"Bildschirm {index + 1} ({geo.width()}×{geo.height()}) – {screen.name()}"


def beamer_screen():
    """Der eingestellte Beamer-Bildschirm. Ist er (unter diesem Namen) nicht angeschlossen, gilt wie früher die
    gespeicherte Nummer und notfalls der Hauptbildschirm – das Beamer-Bild muss irgendwo erscheinen."""
    settings = app_settings()
    screen = find_screen(settings.value(KEY_BEAMER_SCREEN_NAME, "", type=str))
    if screen is not None:
        return screen
    screens = QApplication.screens()
    index = settings.value(KEY_BEAMER_SCREEN, 0, type=int)
    return screens[index] if 0 <= index < len(screens) else QApplication.primaryScreen()


def beamer_screen_index() -> int:
    """Nummer des Beamer-Bildschirms in ``QApplication.screens()`` (für die Fenster, die mit Nummern arbeiten)."""
    target = beamer_screen()
    for index, screen in enumerate(QApplication.screens()):
        if screen is target or screen == target:
            return index
    return 0


def save_beamer_screen(name: str) -> None:
    """Speichert den Beamer-Bildschirm (Name maßgeblich, Nummer für ältere Versionen)."""
    settings = app_settings()
    settings.setValue(KEY_BEAMER_SCREEN_NAME, name)
    screens = QApplication.screens()
    for index, screen in enumerate(screens):
        if screen.name() == name:
            settings.setValue(KEY_BEAMER_SCREEN, index)
            break
