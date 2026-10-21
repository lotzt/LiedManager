"""Kamera- und Mikrofon-Zugriff beim Programmstart anfragen (macOS fragt, Windows/Linux erlauben still).

Ablauf in ``ensure_at_start``:
1. Ist ein Zugriff noch nicht entschieden, erklärt ein Hinweis-Dialog, wofür er gebraucht wird – erst danach
   erscheint die Abfrage des Betriebssystems (sonst kommt sie für den Nutzer „aus dem Nichts“).
2. Wurde ein Zugriff verweigert, zeigt ein zweiter Dialog, wie man ihn in den Systemeinstellungen nachholt.
   Dieser Hinweis lässt sich pro Zugriff abschalten.

Die Funktionen ``status``, ``request`` und die beiden Dialoge sind getrennt, damit der Smoke-Test sie ersetzen kann.
"""
import logging
import sys
from collections import namedtuple

from PyQt6 import QtCore
from PyQt6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QCheckBox, QMessageBox

from services.settings import app_settings

log = logging.getLogger(__name__)

Permission = namedtuple("Permission", "key label purpose qt_class mac_pane win_page")

CAMERA = Permission("camera", "Kamera", "für die Live-Kamerabilder", "QCameraPermission",
                    "Privacy_Camera", "ms-settings:privacy-webcam")
MICROPHONE = Permission("microphone", "Mikrofon", "für die Predigt-Aufnahme", "QMicrophonePermission",
                        "Privacy_Microphone", "ms-settings:privacy-microphone")
ALL = (CAMERA, MICROPHONE)

REQUEST_TIMEOUT_MS = 5 * 60 * 1000   # Sicherheitsnetz, falls das System nie antwortet


def _hint_key(permission: Permission) -> str:
    return f"permission_hint_off_{permission.key}"


def status(permission: Permission):
    """``Qt.PermissionStatus`` (Granted / Denied / Undetermined) oder ``None``, wenn Qt das nicht kennt (PyQt6 < 6.5)."""
    qt_class = getattr(QtCore, permission.qt_class, None)
    app = QCoreApplication.instance()
    if qt_class is None or app is None:
        return None
    try:
        return app.checkPermission(qt_class())
    except Exception as exc:
        log.warning("%s-Berechtigung konnte nicht geprüft werden: %s", permission.label, exc)
        return None


def request(permission: Permission):
    """Fragt den Zugriff an und wartet, bis der Nutzer geantwortet hat. Gibt den neuen Status zurück."""
    qt_class = getattr(QtCore, permission.qt_class, None)
    app = QCoreApplication.instance()
    if qt_class is None or app is None:
        return None
    loop = QEventLoop()
    try:
        app.requestPermission(qt_class(), lambda _permission: loop.quit())
    except Exception as exc:
        log.warning("%s-Berechtigung konnte nicht angefragt werden: %s", permission.label, exc)
        return None
    QTimer.singleShot(REQUEST_TIMEOUT_MS, loop.quit)
    loop.exec()
    return status(permission)


def open_system_settings(permission: Permission) -> bool:
    """Öffnet die passende Seite der Systemeinstellungen (macOS: Datenschutz, Windows: Datenschutz)."""
    if sys.platform == "darwin":
        url = f"x-apple.systempreferences:com.apple.preference.security?{permission.mac_pane}"
    elif sys.platform.startswith("win"):
        url = permission.win_page
    else:
        return False
    return QDesktopServices.openUrl(QUrl(url))


# ----------------------------------------------------------------------
# Dialoge
# ----------------------------------------------------------------------
def _show_intro(pending, parent=None) -> None:
    lines = "\n".join(f"•  {p.label} – {p.purpose}" for p in pending)
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("LiedManager braucht Zugriff")
    box.setText("LiedManager möchte auf folgende Geräte zugreifen:")
    box.setInformativeText(
        f"{lines}\n\n"
        "Gleich fragt dein Computer nach – bitte jeweils „Erlauben“ bzw. „OK“ wählen.\n\n"
        "Ohne Zugriff bleibt die jeweilige Funktion aus; Lieder, Beamer und Pausentimer laufen trotzdem."
    )
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def _show_denied(denied, parent=None) -> None:
    """Hinweis auf verweigerte Zugriffe; ein Häkchen schaltet ihn für diese Zugriffe dauerhaft ab."""
    names = " und ".join(p.label for p in denied)
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(f"{names}-Zugriff ist ausgeschaltet")
    box.setText(f"LiedManager darf nicht auf {'das' if len(denied) == 1 else 'die'} {names} zugreifen.")
    where = ("Systemeinstellungen → Datenschutz & Sicherheit" if sys.platform == "darwin"
             else "Einstellungen → Datenschutz & Sicherheit")
    box.setInformativeText(
        f"Zum Einschalten: {where}, dort „{names}“ wählen und LiedManager erlauben. "
        "Danach das Programm neu starten."
    )
    open_button = box.addButton("Einstellungen öffnen", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Später", QMessageBox.ButtonRole.RejectRole)
    never = QCheckBox("Diesen Hinweis nicht mehr zeigen")
    box.setCheckBox(never)
    box.exec()
    if never.isChecked():
        for permission in denied:
            app_settings().setValue(_hint_key(permission), True)
    if box.clickedButton() is open_button:
        open_system_settings(denied[0])


# ----------------------------------------------------------------------
# Ablauf beim Start
# ----------------------------------------------------------------------
def ensure_at_start(parent=None) -> dict:
    """Fragt fehlende Zugriffe an und weist auf verweigerte hin. Gibt ``{schlüssel: Status}`` zurück."""
    settings = app_settings()
    pending = [p for p in ALL if status(p) == Qt.PermissionStatus.Undetermined]
    if pending:
        _show_intro(pending, parent)
        for permission in pending:
            request(permission)

    result = {p.key: status(p) for p in ALL}
    denied = []
    for permission in ALL:
        if result[permission.key] == Qt.PermissionStatus.Denied:
            if not settings.value(_hint_key(permission), False, type=bool):
                denied.append(permission)
        elif result[permission.key] == Qt.PermissionStatus.Granted:
            settings.remove(_hint_key(permission))   # wieder erlaubt -> künftige Verweigerung darf wieder warnen
    if denied:
        _show_denied(denied, parent)
    return result
