"""Aufnahmen direkt in die WordPress-Mediathek hochladen (REST-Schnittstelle ``/wp-json/wp/v2/media``).

Anmeldung mit Benutzername und „Anwendungspasswort“ (WordPress → Benutzer → Profil → Anwendungspasswörter); das normale
Passwort wird nicht gebraucht. WordPress nimmt die Datei in einer einzigen Anfrage entgegen, die Größe begrenzen
``upload_max_filesize`` und ``post_max_size`` des Servers. Ist ``ffmpeg`` installiert, wird die WAV-Aufnahme vorher in eine
kleine MP3 umgewandelt (Mono, 64 kbit/s – für Predigten ausreichend; die Originaldatei bleibt unverändert).
Dieses Modul kennt Qt nicht.
"""
import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request

from services.server_sync import SyncError, _ssl_context, url_problem

log = logging.getLogger(__name__)

TIMEOUT = 600
CONTENT_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".flac": "audio/flac", ".ogg": "audio/ogg"}


def site_base(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    for tail in ("/wp-json", "/wp-admin", "/wp-login.php"):
        if url.endswith(tail):
            url = url[: -len(tail)]
    return url


def endpoints(url: str) -> list:
    base = site_base(url)
    return [f"{base}/wp-json/wp/v2/media", f"{base}/?rest_route=/wp/v2/media"]   # zweite Form: Permalinks „Einfach“


def ascii_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return "".join(c if c.isalnum() or c in " ._-" else "_" for c in text).strip() or "aufnahme.wav"


_FFMPEG_DIRS = {
    "darwin": ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"],          # Homebrew (Apple/Intel), MacPorts
    "win32": [r"C:\ffmpeg\bin", os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin"),
              os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links"),     # winget install ffmpeg
              os.path.expanduser(r"~\scoop\shims")],
}


def find_ffmpeg():
    """ffmpeg im Suchpfad – und an den üblichen Orten, die eine aus dem Finder/Startmenü gestartete App nicht im PATH hat."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    for folder in _FFMPEG_DIRS.get(sys.platform, []):
        found = shutil.which("ffmpeg", path=folder)
        if found:
            return found
    return None


def to_mp3(path: str):
    """Pfad der MP3-Fassung (Temp-Datei) oder ``None``, wenn ffmpeg fehlt oder die Umwandlung scheitert."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg or not path.lower().endswith(".wav"):
        return None
    target = os.path.join(tempfile.gettempdir(), os.path.splitext(os.path.basename(path))[0] + ".mp3")
    try:
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-b:a", "64k", target],
                       check=True, timeout=3600, stdin=subprocess.DEVNULL,
                       creationflags=0x08000000 if sys.platform.startswith("win") else 0)   # Windows: kein Konsolenfenster
    except (OSError, subprocess.SubprocessError):
        log.warning("Umwandlung in MP3 fehlgeschlagen – es wird die WAV-Datei hochgeladen.", exc_info=True)
        return None
    return target


class _Body:
    """Datei als Anfragekörper: wird in Stücken gelesen (kein Laden der ganzen Datei in den Speicher) und meldet den Fortschritt."""

    def __init__(self, path, on_progress, should_stop):
        self._file = open(path, "rb")
        self.total = os.path.getsize(path)
        self.done = 0
        self._on_progress, self._should_stop = on_progress, should_stop

    def read(self, size=-1):
        if self._should_stop is not None and self._should_stop():
            raise SyncError("Abgebrochen.")
        data = self._file.read(256 * 1024 if size is None or size < 0 else min(size, 256 * 1024))
        self.done += len(data)
        if self._on_progress is not None:
            self._on_progress(self.done, self.total)
        return data

    def close(self):
        self._file.close()


def _parse_json(raw: bytes):
    """JSON-Objekt aus der Antwort; manche Server schreiben Warnungen davor – dann ab der ersten „{“ lesen. Sonst ``None``."""
    text = raw.decode("utf-8", "replace")
    start = text.find("{")
    if start < 0:
        return None
    try:
        data = json.loads(text[start:])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _message(code: int, detail: str) -> str:
    if code == 401:
        return ("WordPress lehnt die Anmeldung ab (401). Prüfen: Benutzername (Login-Name) und das Anwendungspasswort (nicht das normale "
                "Passwort), die Adresse genau wie im Browser (mit/ohne www, https) – und ob der Server den Anmelde-Header entfernt "
                "(dann in die .htaccess von WordPress: RewriteRule .* - [E=HTTP_AUTHORIZATION:%{HTTP:Authorization}]).")
    if code == 403:
        return "Keine Berechtigung – der Benutzer braucht mindestens die Rolle „Autor“ (und darf Dateien hochladen)."
    if code == 413:
        return "Datei zu groß für den Server (WordPress/PHP-Grenze upload_max_filesize bzw. post_max_size)."
    return f"WordPress meldet Fehler {code}{': ' + detail if detail else ''}"


def upload_file(site_url: str, user: str, app_password: str, path: str, on_progress=None, should_stop=None,
                convert: bool = True) -> str:
    """Lädt die Datei in die Mediathek und gibt die Adresse der Datei zurück. Fehler: ``SyncError``."""
    problem = url_problem(site_base(site_url))
    if problem:
        raise SyncError(problem)
    if not user.strip() or not app_password.strip():
        raise SyncError("Benutzername oder Anwendungspasswort fehlt.")
    ext = os.path.splitext(path)[1].lower()
    if ext not in CONTENT_TYPES:
        raise SyncError("Dateityp wird nicht hochgeladen.")
    temp = to_mp3(path) if convert else None
    source = temp or path
    ext = os.path.splitext(source)[1].lower()
    filename = ascii_name(os.path.basename(source))
    token = base64.b64encode(f"{user.strip()}:{app_password.strip()}".encode("utf-8")).decode("ascii")
    try:
        last_error = None
        for index, endpoint in enumerate(endpoints(site_url)):
            body = _Body(source, on_progress, should_stop)
            request = urllib.request.Request(endpoint, data=body, method="POST", headers={
                "Authorization": f"Basic {token}",
                "Content-Type": CONTENT_TYPES[ext],
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(body.total),
                "User-Agent": "LiedManager-Upload"})
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT, context=_ssl_context()) as response:
                    raw = response.read() or b""
                    status = getattr(response, "status", 200)
                payload = _parse_json(raw)
                if payload is None:
                    if status == 201:                                # „Created“: hochgeladen, nur die Antwort ist ungewöhnlich
                        return filename
                    snippet = " ".join(raw.decode("utf-8", "replace").split())[:100]
                    raise SyncError("WordPress hat keine gültige Antwort geliefert"
                                    + (f" („{snippet}“)" if snippet else " (leer)")
                                    + ". Stimmt die Adresse (https://, ohne /wp-admin)? Blockiert ein Sicherheits-Plugin die REST-Schnittstelle?")
                return str(payload.get("source_url") or payload.get("link") or filename)
            except urllib.error.HTTPError as exc:
                if exc.code == 404 and index == 0:               # REST-Adresse unter dieser Form nicht gefunden: andere probieren
                    last_error = SyncError(_message(404, "REST-Schnittstelle nicht gefunden"))
                    continue
                try:
                    detail = str(json.loads(exc.read() or b"{}").get("message", ""))
                except (ValueError, OSError):
                    detail = ""
                raise SyncError(_message(exc.code, detail), exc.code) from exc
            except (urllib.error.URLError, OSError) as exc:
                raise SyncError(f"Server nicht erreichbar ({getattr(exc, 'reason', exc)})") from exc
            finally:
                body.close()
        raise last_error or SyncError("Upload fehlgeschlagen.")
    finally:
        if temp:
            try:
                os.remove(temp)
            except OSError:
                pass
