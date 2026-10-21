"""Pfade der Anwendung – im Entwicklungsmodus und in der gebauten App (PyInstaller)."""
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

# Mitgelieferte Dateien (Assets, Schriften): neben dem Code bzw. im PyInstaller-Paket
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ASSETS_DIR = RESOURCE_DIR / "ui" / "assets"


def user_data_dir() -> Path:
    """Beschreibbarer Ordner für Datenbank, Log und eigene Pausenfolien."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = base / "LiedManager"
    path.mkdir(parents=True, exist_ok=True)
    return path


def custom_db_path() -> str:
    """In den Einstellungen gewählte Datenbank (leer = automatisch suchen)."""
    try:
        from services.settings import app_settings  # erst hier: paths.py selbst braucht kein Qt
        return str(app_settings().value("database_path", "", type=str)).strip()
    except Exception:
        return ""


def default_db_path(name: str = "LiedManager.db") -> str:
    """Automatische Suche: Arbeitsverzeichnis, neben dem Programm, dann im Datenordner des Benutzers."""
    beside_program = Path(sys.executable).resolve().parent if FROZEN else RESOURCE_DIR
    candidates = [Path.cwd() / name, beside_program / name, user_data_dir() / name]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[-1] if FROZEN else candidates[1])


def resolve_db_path(name: str = "LiedManager.db") -> str:
    """Die in den Einstellungen gewählte Datenbank hat Vorrang, sonst wird automatisch gesucht."""
    return custom_db_path() or default_db_path(name)


def sync_state_path(db_path: str) -> Path:
    """Merkzettel des Datenbank-Abgleichs (pro Datenbank-Datei eine eigene Datei, nur lokal)."""
    import hashlib
    key = hashlib.sha1(os.path.normcase(os.path.abspath(db_path)).encode("utf-8")).hexdigest()[:12]
    folder = user_data_dir() / "sync"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"abgleich_{key}.db"


def updates_dir() -> Path:
    """Hier landen heruntergeladene Installer (werden beim nächsten Start aufgeräumt)."""
    path = user_data_dir() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def custom_pausentimer_dir() -> Path:
    """Ordner für die Pausenfolien (eigene PowerPoint-Vorlagen; das Programm liefert keine mit)."""
    return user_data_dir() / "pausentimer"
