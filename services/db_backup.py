"""Sicherungskopien der Liederdatenbank.

Die Datenbank ist das Wertvollste im Programm. Deshalb entsteht vor dem Abgleich mit dem Server höchstens einmal am Tag
eine Kopie – und immer vor „Alles neu hochladen“. Es werden die letzten ``KEEP`` Kopien aufbewahrt, ältere gelöscht.
Kopiert wird mit der SQLite-Sicherungsfunktion (auch bei geöffneter Datenbank ein konsistenter Stand). Reicht der freie
Speicherplatz nicht, wird keine Kopie angelegt (und das protokolliert). Dieses Modul kennt Qt nicht.
"""
import datetime
import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path

from paths import user_data_dir

log = logging.getLogger(__name__)

KEEP = 5
MIN_INTERVAL = 20 * 3600          # Routine-Sicherung höchstens einmal am Tag (mit etwas Spielraum)
PREFIX = "Sicherung "


def backup_dir() -> Path:
    path = user_data_dir() / "Datenbank-Sicherungen"
    path.mkdir(parents=True, exist_ok=True)
    return path


def existing(folder: Path = None) -> list:
    """Vorhandene Sicherungen, neueste zuerst."""
    folder = folder or backup_dir()
    files = [p for p in folder.glob(PREFIX + "*.db") if p.is_file()]
    return sorted(files, key=lambda p: p.name, reverse=True)


def due(folder: Path = None, now: float = None) -> bool:
    files = existing(folder)
    if not files:
        return True
    return (now or time.time()) - files[0].stat().st_mtime >= MIN_INTERVAL


def backup(db_path, folder: Path = None, keep: int = KEEP, reason: str = "") -> Path:
    """Legt eine Sicherung an und gibt ihren Pfad zurück (``None``, wenn nicht möglich)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    folder = folder or backup_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        need = db_path.stat().st_size * 1.2 + 50_000_000
        if shutil.disk_usage(folder).free < need:
            log.warning("Keine Sicherung: zu wenig freier Speicherplatz in %s", folder)
            return None
    except OSError as exc:
        log.warning("Sicherung nicht möglich: %s", exc)
        return None
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    target = folder / f"{PREFIX}{stamp}.db"
    temp = folder / (target.name + ".teil")
    try:
        source = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=30)
        try:
            copy = sqlite3.connect(str(temp))
            try:
                source.backup(copy)
            finally:
                copy.close()
        finally:
            source.close()
        os.replace(temp, target)
    except (sqlite3.Error, OSError) as exc:
        log.warning("Sicherung fehlgeschlagen: %s", exc)
        try:
            temp.unlink()
        except OSError:
            pass
        return None
    for old in existing(folder)[keep:]:
        try:
            old.unlink()
        except OSError:
            pass
    log.info("Datenbank gesichert (%s): %s", reason or "Routine", target)
    return target


_last_attempt = 0.0


def backup_if_due(db_path, folder: Path = None) -> Path:
    """Routine-Sicherung: höchstens einmal am Tag, und ein misslungener Versuch wird erst nach einer Stunde wiederholt."""
    global _last_attempt
    if time.time() - _last_attempt < 3600 or not due(folder):
        return None
    _last_attempt = time.time()
    return backup(db_path, folder, reason="täglich")
