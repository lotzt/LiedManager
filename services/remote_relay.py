"""Website-Steuerung: die Brücke zwischen LiedManager und der eigenen Website (``server/remote.php``).

Warum eine Brücke? Das Programm steht hinter dem Router und ist aus dem Internet nicht erreichbar. Deshalb ruft es
selbst bei der Website an – ausgehend, wie der Datenbank-Abgleich – und fragt dort nach Aufträgen:

* ``poll``    wartet bis zu ``HOLD_SECONDS`` auf Aufträge aus dem Browser (kommt einer, antwortet der Server sofort),
* ``state``   schickt den aktuellen Zustand des Programms; der Browser bekommt ihn von der Website, ohne dass das
              Programm bei jeder Abfrage gefragt werden muss,
* ``result``  liefert das Ergebnis eines Auftrags (Aktion, Vorschaubild, Bild-Upload) an den wartenden Browser.

Die Aktionen führt ``ui/web_remote_ui.py`` als „Backend“ im Programm aus. Angemeldet
wird der Browser von der Website selbst (PIN in ``remote.php``); nur angemeldete Anfragen erreichen das Programm.
Dieses Modul kennt Qt nicht. Nur Standardbibliothek. Ohne HTTPS verweigert es die Verbindung (das Token wäre sonst offen).
"""
import base64
import binascii
import json
import logging
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor

from services.remote_common import UPLOAD_EXTENSIONS, RemoteError
from services.server_sync import ServerApi, SyncError, normalize_url, url_problem

log = logging.getLogger(__name__)

FORMAT = 1                      # Protokollversion, muss zu server/remote.php passen
MIN_TOKEN_LENGTH = 16
HOLD_SECONDS = 15               # so lange wartet der Server auf einen Auftrag, bevor er „nichts“ antwortet
POLL_TIMEOUT = HOLD_SECONDS + 20
SEND_TIMEOUT = 15
MIN_CYCLE = 0.5                 # schneller als zweimal pro Sekunde wird nie nachgefragt (Schutz vor Dauerschleife)
STATE_EVERY = 1.0               # so oft wird der Zustand geprüft …
STATE_KEEPALIVE = 5.0           # … und mindestens so oft gesendet, auch wenn er gleich geblieben ist
RETRY_MAX = 30                  # Wartezeit bei Fehlern wächst bis zu diesem Wert (Sekunden)
WORKERS = 4


class RemoteApi(ServerApi):
    """Wie ``ServerApi``, nur mit Fehlermeldungen, die zu ``remote.php`` passen (statt ``sync.php``)."""

    @staticmethod
    def _http_message(exc: urllib.error.HTTPError) -> str:
        if exc.code == 401:
            return "Token falsch – bitte in den Einstellungen und in remote.php prüfen"
        if exc.code in (404, 405):
            return "Adresse falsch (remote.php nicht gefunden)"
        detail = ""
        try:
            detail = json.loads(exc.read()).get("error", "")
        except Exception:
            pass
        if exc.code == 503:
            # Die Website nennt selbst, welche Zugangsdaten fehlen (z. B. „PIN ist zu kurz“)
            return detail or "remote.php ist noch nicht eingerichtet (Token, PIN und Datenbank eintragen)"
        return f"Server meldet Fehler {exc.code}" + (f": {detail}" if detail else "")


def token_problem(token: str) -> str:
    """Leer, wenn das Token brauchbar ist."""
    if len((token or "").strip()) < MIN_TOKEN_LENGTH:
        return f"Das Token braucht mindestens {MIN_TOKEN_LENGTH} Zeichen (dasselbe wie in remote.php)."
    return ""


def page_url(url: str) -> str:
    """Adresse, die man im Browser öffnet (= die Adresse von remote.php)."""
    return normalize_url(url)


class RelayClient:
    """``backend`` braucht: ``state()``, ``action(name, args)``, ``thumbnail(index)``,
    ``upload(filename, data)``. ``on_status(text)`` wird bei jeder Änderung des Zustands der Verbindung aufgerufen
    (aus einem Hintergrund-Thread)."""

    def __init__(self, url: str, token: str, backend, on_status=None, poll_api=None, send_api=None):
        self.url = normalize_url(url)
        self.token = (token or "").strip()
        self.backend = backend
        self._on_status = on_status or (lambda text: None)
        self._poll_api = poll_api or RemoteApi(self.url, self.token, POLL_TIMEOUT)
        self._send_api = send_api or RemoteApi(self.url, self.token, SEND_TIMEOUT)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._threads = []
        self._pool = None
        self._status = ""
        self._connected = False
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return bool(self._threads)

    @property
    def connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    def start(self) -> str:
        """Startet die Verbindung. Gibt eine Fehlermeldung zurück, sonst leeren Text."""
        if self._threads:
            return ""
        problem = url_problem(self.url) or token_problem(self.token)
        if problem:
            return problem
        self._stop.clear()
        self._pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="relay-job")
        self._threads = [
            threading.Thread(target=self._poll_loop, name="relay-poll", daemon=True),
            threading.Thread(target=self._state_loop, name="relay-state", daemon=True),
        ]
        for thread in self._threads:
            thread.start()
        self._set_status("Verbinde mit der Website …")
        return ""

    def stop(self) -> None:
        if not self._threads:
            return
        self._stop.set()
        self._wake.set()
        threads, self._threads = self._threads, []
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
        if self._connected:
            self._connected = False
            bye = threading.Thread(target=self._say_goodbye, daemon=True)   # Browser sofort „getrennt“ anzeigen
            bye.start()
            bye.join(1.5)
        for thread in threads:
            thread.join(timeout=0.2)

    def _say_goodbye(self) -> None:
        try:
            RemoteApi(self.url, self.token, 3).call("bye")
        except SyncError:
            pass

    # ------------------------------------------------------------------
    def _set_status(self, text: str) -> None:
        with self._lock:
            if text == self._status:
                return
            self._status = text
        try:
            self._on_status(text)
        except Exception:
            log.exception("Website-Steuerung: Statusmeldung fehlgeschlagen")

    def _set_connected(self, connected: bool, error: str = "", wait: int = 0) -> None:
        self._connected = connected
        if connected:
            self._set_status(f"Verbunden – im Browser öffnen: {page_url(self.url)}")
        else:
            retry = f" Neuer Versuch in {wait} s." if wait else ""
            self._set_status(f"Keine Verbindung zur Website ({error}).{retry}")

    # ------------------------------------------------------------------
    # Aufträge abholen
    # ------------------------------------------------------------------
    def _poll_loop(self) -> None:
        failures = 0
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                reply = self._poll_api.call("poll", hold=HOLD_SECONDS)
                if reply.get("format") != FORMAT:
                    raise SyncError("Programm und remote.php passen nicht zusammen – bitte remote.php neu hochladen")
                failures = 0
                self._set_connected(True)
                for job in reply.get("jobs") or []:
                    pool = self._pool
                    if pool is not None and isinstance(job, dict):
                        pool.submit(self._handle, job)
                pause = MIN_CYCLE - (time.monotonic() - started)
                if pause > 0 and self._stop.wait(pause):
                    return
            except SyncError as exc:
                failures += 1
                wait = min(RETRY_MAX, 2 * failures)
                self._set_connected(False, str(exc), wait)
                if self._stop.wait(wait):
                    return
            except Exception:
                log.exception("Website-Steuerung: unerwarteter Fehler beim Abholen")
                if self._stop.wait(5):
                    return

    # ------------------------------------------------------------------
    # Zustand senden
    # ------------------------------------------------------------------
    def _state_loop(self) -> None:
        last_text, last_sent = None, 0.0
        while not self._stop.is_set():
            self._wake.wait(STATE_EVERY)
            self._wake.clear()
            if self._stop.is_set():
                return
            if not self._connected:
                last_text = None
                continue
            try:
                text = json.dumps(self.backend.state(), ensure_ascii=False, separators=(",", ":"))
            except RemoteError:
                continue                                  # Programm antwortet gerade nicht: beim nächsten Mal wieder
            except Exception:
                log.exception("Website-Steuerung: Zustand konnte nicht gelesen werden")
                continue
            now = time.monotonic()
            if text == last_text and now - last_sent < STATE_KEEPALIVE:
                continue
            try:
                self._send_api.call("state", data=text)
                last_text, last_sent = text, now
            except SyncError as exc:
                last_text = None
                log.debug("Website-Steuerung: Zustand nicht gesendet (%s)", exc)

    # ------------------------------------------------------------------
    # Aufträge ausführen
    # ------------------------------------------------------------------
    def _handle(self, job: dict) -> None:
        job_id = job.get("id")
        status, ctype, body = self._execute(job)
        try:
            self._send_api.call("result", id=job_id, http=status, ctype=ctype,
                                body=base64.b64encode(body).decode("ascii"))
        except SyncError as exc:
            log.warning("Website-Steuerung: Ergebnis nicht zugestellt (%s)", exc)
        self._wake.set()                                  # frischen Zustand gleich hinterherschicken

    def _execute(self, job: dict):
        """Gibt (HTTP-Status, Inhaltstyp, Bytes) zurück. Fehler werden zu einer Meldung für den Browser."""
        kind = job.get("kind")
        name = str(job.get("name", ""))
        try:
            if kind == "action":
                try:
                    args = json.loads(job.get("body") or "{}")
                except ValueError:
                    raise RemoteError("Ungültiges JSON.", 400)
                if not isinstance(args, dict):
                    args = {}
                return self._json(200, self.backend.action(name, args))
            if kind == "thumb":
                data = self.backend.thumbnail(int(name))
                if data is None:
                    raise RemoteError("Kein Bild.", 404)
                return 200, "image/jpeg", data
            if kind == "upload":
                if not name.lower().endswith(UPLOAD_EXTENSIONS):
                    raise RemoteError("Nur Bilder (PNG, JPG, GIF, BMP, WebP) sind erlaubt.", 415)
                try:
                    data = base64.b64decode(job.get("body") or "", validate=True)
                except (binascii.Error, ValueError):
                    raise RemoteError("Ungültige Anfrage.", 400)
                if not data:
                    raise RemoteError("Die Datei ist leer.", 400)
                return self._json(200, self.backend.upload(name, data))
            raise RemoteError("Unbekannter Auftrag.", 400)
        except RemoteError as exc:
            return self._json(exc.status, {"error": exc.message})
        except (ValueError, TypeError):
            return self._json(400, {"error": "Ungültige Anfrage."})
        except Exception:
            log.exception("Website-Steuerung: Auftrag %s/%s fehlgeschlagen", kind, name)
            return self._json(500, {"error": "Interner Fehler."})

    @staticmethod
    def _json(status: int, payload):
        return status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False).encode("utf-8")
