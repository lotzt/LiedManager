"""Ein Token für die eigene Website: remote.php (Fernsteuerung, Aufnahmen, Problemmeldungen) und sync.php (Abgleich)
lesen auf dem Server dieselbe Zugangsdatei (liedmanager-zugang.php) – also gibt es im Programm auch nur ein Token.

Früher hatte der Abgleich ein eigenes Token („sync_token“). Ist das gemeinsame noch leer, wird das alte übernommen.
"""
from urllib.parse import urlsplit, urlunsplit

from services.settings import app_settings

KEY_TOKEN = "web_site_token"
KEY_OLD_SYNC_TOKEN = "sync_token"


def token() -> str:
    settings = app_settings()
    value = str(settings.value(KEY_TOKEN, "", type=str) or "").strip()
    if not value:
        old = str(settings.value(KEY_OLD_SYNC_TOKEN, "", type=str) or "").strip()
        if old:
            settings.setValue(KEY_TOKEN, old)
            settings.sync()
            value = old
    return value


def sibling_url(url: str, folder: str, filename: str) -> str:
    """Vorschlag für die andere Datei: …/steuerung/remote.php → …/sync/sync.php (und umgekehrt). Leer, wenn unklar."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url if "://" in url else "https://" + url)
    except ValueError:
        return ""
    if not parts.netloc:
        return ""
    path = parts.path.rstrip("/")
    if path.lower().endswith(".php"):
        path = path.rsplit("/", 1)[0]            # Ordner der Datei
    parent = path.rsplit("/", 1)[0] if path.count("/") >= 1 and path else ""
    return urlunsplit((parts.scheme, parts.netloc, f"{parent}/{folder}/{filename}", "", ""))
