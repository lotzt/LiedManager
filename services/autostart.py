"""Autostart: LiedManager beim Anmelden am Computer automatisch starten.

* Windows: Eintrag „LiedManager“ unter HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run (nur dieser Benutzer).
* macOS:   LaunchAgent ``~/Library/LaunchAgents/de.liedmanager.autostart.plist`` (öffnet die App beim Anmelden).
* Linux:   ``~/.config/autostart/liedmanager.desktop``.

Der Zustand wird nicht in den Programmeinstellungen gemerkt, sondern immer direkt beim System nachgesehen – so stimmt
die Anzeige auch, wenn der Eintrag von Hand entfernt wurde. Keine Administratorrechte nötig.
"""
import logging
import os
import plistlib
import sys
from pathlib import Path

from paths import FROZEN, RESOURCE_DIR

log = logging.getLogger(__name__)

NAME = "LiedManager"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_MAC_LABEL = "de.liedmanager.autostart"


def supported() -> bool:
    return sys.platform.startswith("win") or sys.platform == "darwin" or sys.platform.startswith("linux")


def _mac_app_bundle():
    """…/LiedManager.app der gebauten App (sys.executable liegt in Contents/MacOS)."""
    for parent in Path(sys.executable).resolve().parents:
        if parent.suffix == ".app":
            return parent
    return None


def command() -> list:
    """Programm + Argumente, mit denen LiedManager gestartet wird."""
    if FROZEN:
        if sys.platform == "darwin":
            bundle = _mac_app_bundle()
            if bundle is not None:
                return ["/usr/bin/open", "-a", str(bundle)]
        return [sys.executable]
    python = Path(sys.executable)
    if sys.platform.startswith("win"):                      # pythonw: ohne Konsolenfenster
        windowless = python.with_name("pythonw.exe")
        if windowless.exists():
            python = windowless
    return [str(python), str(RESOURCE_DIR / "main.py")]


def _quote_windows(args) -> str:
    return " ".join(f'"{a}"' for a in args)


def _mac_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_MAC_LABEL}.plist"


def _linux_desktop() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "liedmanager.desktop"


def is_enabled() -> bool:
    try:
        if sys.platform.startswith("win"):
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.QueryValueEx(key, NAME)
            return True
        if sys.platform == "darwin":
            return _mac_plist().exists()
        return _linux_desktop().exists()
    except OSError:
        return False


def set_enabled(enabled: bool) -> str:
    """Schaltet den Autostart ein/aus. Gibt eine Fehlermeldung zurück (leer = hat geklappt)."""
    try:
        if sys.platform.startswith("win"):
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                if enabled:
                    winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, _quote_windows(command()))
                else:
                    try:
                        winreg.DeleteValue(key, NAME)
                    except FileNotFoundError:
                        pass
        elif sys.platform == "darwin":
            plist = _mac_plist()
            if enabled:
                plist.parent.mkdir(parents=True, exist_ok=True)
                with open(plist, "wb") as handle:
                    plistlib.dump({"Label": _MAC_LABEL, "ProgramArguments": command(), "RunAtLoad": True,
                                   "ProcessType": "Interactive"}, handle)
            else:
                plist.unlink(missing_ok=True)
        else:
            desktop = _linux_desktop()
            if enabled:
                desktop.parent.mkdir(parents=True, exist_ok=True)
                exec_line = " ".join(f'"{a}"' for a in command())
                desktop.write_text(f"[Desktop Entry]\nType=Application\nName={NAME}\nExec={exec_line}\n"
                                   "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
            else:
                desktop.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("Autostart konnte nicht geändert werden: %s", exc)
        return str(exc)
    return ""
