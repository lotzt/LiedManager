"""Aufnahmen auf die eigene Website laden (``server/remote.php``, Ordner ``aufnahmen``).

Eine Aufnahme kann mehrere hundert MB groß sein. Deshalb wird sie in Stücken von ``CHUNK`` Bytes gesendet; bricht die
Verbindung ab, setzt der nächste Versuch dort fort, wo die Website aufgehört hat. Noch nicht hochgeladene Dateien stehen
in einer kleinen Liste im Datenordner und werden beim nächsten Start (oder nach der nächsten Aufnahme) nachgeholt.
Dieses Modul kennt Qt nicht.
"""
import base64
import json
import logging
import os
import threading

from paths import user_data_dir
from services.remote_relay import RemoteApi
from services.server_sync import SyncError, normalize_url, url_problem

log = logging.getLogger(__name__)

CHUNK = 1536 * 1024              # Bytes je Anfrage (Base64 wird ein Drittel größer; die Website erlaubt 4 MB)
TIMEOUT = 90
EXTENSIONS = (".wav", ".mp3", ".m4a", ".flac", ".ogg")
_LOCK = threading.Lock()


def queue_path() -> str:
    return str(user_data_dir() / "aufnahmen_hochladen.json")


def pending() -> list:
    with _LOCK:
        try:
            with open(queue_path(), encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return []
    return [str(p) for p in data if isinstance(p, str)] if isinstance(data, list) else []


def _write(items: list) -> None:
    try:
        os.makedirs(os.path.dirname(queue_path()), exist_ok=True)
        with open(queue_path(), "w", encoding="utf-8") as handle:
            json.dump(items, handle, ensure_ascii=False)
    except OSError:
        log.exception("Aufnahme-Upload: Liste konnte nicht gespeichert werden")


def add_pending(path: str) -> None:
    items = pending()
    if path not in items:
        items.append(path)
        with _LOCK:
            _write(items)


def remove_pending(path: str) -> None:
    items = [p for p in pending() if p != path]
    with _LOCK:
        _write(items)


def upload_file(url: str, token: str, path: str, on_progress=None, should_stop=None) -> str:
    """Lädt eine Datei hoch und gibt den Namen auf dem Server zurück. Fehler: ``SyncError``."""
    url = normalize_url(url)
    problem = url_problem(url)
    if problem:
        raise SyncError(problem)
    if not path.lower().endswith(EXTENSIONS):
        raise SyncError("Dateityp wird nicht hochgeladen.")
    api = RemoteApi(url, token, TIMEOUT)
    name = os.path.basename(path)
    total = os.path.getsize(path)
    offset = 0
    try:
        offset = int(api.call("rec_size", name=name).get("size", 0))
    except (SyncError, ValueError, TypeError):
        offset = 0
    if offset > total:
        offset = 0
    stored = name
    with open(path, "rb") as handle:
        handle.seek(offset)
        while True:
            if should_stop is not None and should_stop():
                raise SyncError("Abgebrochen.")
            data = handle.read(CHUNK)
            last = handle.tell() >= total
            reply = api.call("rec_put", name=name, offset=offset,
                             data=base64.b64encode(data).decode("ascii"), last=last)
            offset += len(data)
            stored = str(reply.get("name") or stored)
            if on_progress is not None:
                on_progress(offset, total)
            if last:
                return stored
