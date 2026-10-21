"""Installiert fehlende Pakete beim Start automatisch (nur Standardbibliothek – läuft vor allen anderen Importen).

Pflicht:   PyQt6
Optional:  python-pptx (Ansagen in die Pausenfolie), PyATEMMax (ATEM-Mischer), certifi (Update-Suche)

Abschalten mit der Umgebungsvariable LIEDMANAGER_NO_AUTOINSTALL=1.
"""
import importlib
import importlib.util
import json
import os
import site
import subprocess
import sys
import time
from pathlib import Path

# (Modulnamen, von denen EINER genügt, pip-Paket, Pflicht?)
PACKAGES = [
    (("PyQt6",), "PyQt6", True),
    (("pptx",), "python-pptx", False),
    (("ATEM", "PyATEMMax"), "PyATEMMax", False),
    (("certifi",), "certifi", False),   # sichere Verbindung zu GitHub (Update-Suche)
]

RETRY_AFTER_SECONDS = 24 * 3600  # fehlgeschlagene optionale Pakete höchstens einmal pro Tag erneut versuchen
_STATE_FILE = Path.home() / ".liedmanager_deps.json"


def _present(modules) -> bool:
    importlib.invalidate_caches()
    return any(importlib.util.find_spec(name) is not None for name in modules)


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def _pip(*args) -> bool:
    cmd = [sys.executable, "-m", "pip", "--disable-pip-version-check", *args]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=600).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _install(package: str) -> bool:
    """Probiert nacheinander: normal, --user, --break-system-packages (z. B. Homebrew-Python)."""
    if not _pip("--version"):
        try:  # pip fehlt -> nachinstallieren
            subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"],
                           capture_output=True, timeout=300)
        except (OSError, subprocess.SubprocessError):
            pass
    for extra in ((), ("--user",), ("--break-system-packages",), ("--user", "--break-system-packages")):
        if _pip("install", *extra, package):
            try:  # frisch angelegtes User-Verzeichnis dem laufenden Programm bekannt machen
                site.addsitedir(site.getusersitepackages())
            except Exception:
                pass
            return True
    return False


def _alert(message: str) -> None:
    """Meldung auch ohne Qt anzeigen (Konsole + einfaches Systemfenster)."""
    print(message, file=sys.stderr)
    try:
        if sys.platform.startswith("win"):
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "LiedManager", 0x10)
        elif sys.platform == "darwin":
            text = message.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(["osascript", "-e", f'display dialog "{text}" with title "LiedManager" '
                            'buttons {"OK"} default button 1 with icon stop'], timeout=60)
    except Exception:
        pass


def ensure_dependencies() -> None:
    if getattr(sys, "frozen", False) or os.environ.get("LIEDMANAGER_NO_AUTOINSTALL") == "1":
        return  # gebaute App bringt alles mit
    state = _load_state()
    changed = False

    for modules, package, required in PACKAGES:
        if _present(modules):
            continue
        last_try = state.get(package, 0)
        if not required and time.time() - last_try < RETRY_AFTER_SECONDS:
            continue
        print(f"Installiere fehlendes Paket: {package} …", flush=True)
        if _install(package) and _present(modules):
            print(f"{package} wurde installiert.", flush=True)
            state.pop(package, None)
            changed = True
            continue
        if required:
            _alert(f"Das Pflicht-Paket „{package}“ konnte nicht automatisch installiert werden.\n\n"
                   f"Bitte im Terminal ausführen:\n{Path(sys.executable).name} -m pip install {package}")
            sys.exit(1)
        print(f"Optionales Paket {package} konnte nicht installiert werden "
              "(Funktion bleibt deaktiviert).", flush=True)
        state[package] = time.time()
        changed = True

    if changed:
        _save_state(state)
