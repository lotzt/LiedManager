"""Teilt Änderungen an der Lieder-Datenbank zwischen mehreren Geräten über einen eigenen Server (``server/sync.php``).

Jedes Gerät behält seine eigene, lokale Datenbank. Der Server (z. B. bei All-Inkl) speichert pro Lied eine Zeile;
die Geräte schicken ihre Änderungen per HTTPS dorthin und holen die der anderen ab. Das Programm muss dafür nicht
dauerhaft online sein: Es gleicht ab, sobald eine Verbindung besteht (Start, jede Minute, auf Knopfdruck).

So läuft es ab:

* Jedes Lied wird über seine Nummer erkannt (doppelte Nummern: ``p001``, ``p001#2`` …) und bekommt einen
  Fingerabdruck seines Inhalts (Titel, Text, Audio, Bilder).
* **Senden:** Ändert sich die Datenbank (z. B. mit einem Datenbank-Editor), vergleicht das Programm die Fingerabdrücke
  mit dem zuletzt abgeglichenen Stand und schickt nur die geänderten, neuen und gelöschten Lieder – jedes Lied in einer
  eigenen Anfrage, damit auch große Audios sicher ankommen.
* **Empfangen:** Das Programm fragt den Server, welche Lieder sich seit dem letzten Abgleich geändert haben, und holt
  nur die, die es noch nicht kennt. Bei Streit um dasselbe Lied gewinnt die jüngere Änderung (bei gleicher Zeit
  entscheidet die Geräte-Kennung) – dadurch landen alle Geräte beim gleichen Stand.
* Die lokale Datenbank wird dafür nur kurz geschrieben (eine Transaktion pro Lied). Das Programm bleibt die ganze
  Zeit benutzbar und lädt seine Liedliste von selbst neu (``PRAGMA data_version``).
* Beim ersten Mal gilt der aktuelle Stand als gemeinsamer Ausgangspunkt: Es wird nichts gesendet, damit nicht die
  komplette Datenbank auf dem Server landet. Die Datenbank sollte auf allen Geräten zu Beginn gleich sein.
* Die Zeitstempel sind „Lamport-Uhren“: Ein Gerät, dessen Uhr nachgeht, überstimmt trotzdem nie versehentlich eine
  Änderung, die es schon übernommen hat.
"""
import base64
import hashlib
import json
import logging
import os
import sqlite3
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

FORMAT = 1                 # Protokollversion, muss zu server/sync.php passen
KEY_COLUMN = "nummer"
CONTENT_COLUMNS = ("alias", "titel", "lyrics", "audio1", "audio2", "bild1", "bild2", "bild3", "bild4")
LOCK_TIMEOUT = 20          # Sekunden, die auf eine gesperrte Datenbank gewartet wird
REQUEST_TIMEOUT = 90       # Sekunden pro Anfrage (große Audios brauchen auf langsamen Leitungen etwas)
PART_BYTES = 6_000_000         # größere Lieder gehen in Teilen dieser Größe hoch (Serverlimits wie post_max_size)
MAX_SONG_BYTES = 400_000_000   # noch größere Lieder werden gar nicht erst hochgeladen
PUSH_WORKERS = 4           # gleichzeitige Uploads (spart die Wartezeit je Anfrage)
MAX_FAILURES = 3           # so viele abgelehnte Lieder pro Lauf, dann Abbruch (Server meldet Fehler)
RETRY_FAILED_AFTER = 3600  # abgelehntes (unverändertes) Lied frühestens nach dieser Zeit erneut versuchen


class SyncError(Exception):
    """Fehler beim Abgleich mit dem Server. ``status``: HTTP-Statuscode (0 = keine Verbindung)."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


@dataclass
class SyncResult:
    sent: int = 0            # Lieder, die zum Server geschickt wurden
    received: int = 0        # Lieder, die vom Server übernommen wurden
    skipped: int = 0         # Änderungen, die schon durch eine jüngere überholt waren
    failed: int = 0          # Lieder, die der Server nicht annehmen konnte (z. B. zu groß)
    failed_songs: list = field(default_factory=list)   # Liednummer (und Größe), damit man sie im Programm findet
    baseline: bool = False   # erster Lauf: Ausgangspunkt gespeichert
    forced: bool = False     # „Alles neu hochladen“: dieser Stand gilt jetzt für alle Geräte
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def changed_database(self) -> bool:
        return self.received > 0

    def text(self) -> str:
        """Kurzer deutscher Statustext."""
        if self.error:
            return self.error
        parts = ["Eingerichtet"] if self.baseline else []
        if self.forced:
            parts.append("Stand für alle Geräte gesetzt")
        if self.sent:
            parts.append(f"{self.sent} gesendet")
        if self.received:
            parts.append(f"{self.received} übernommen")
        if self.failed:
            names = ", ".join(self.failed_songs[:6]) + (" …" if len(self.failed_songs) > 6 else "")
            parts.append(f"{self.failed} Lied(er) vom Server abgelehnt (zu groß?)" + (f": {names}" if names else ""))
        return ", ".join(parts) if parts else "Alles aktuell"


# ----------------------------------------------------------------------
# Fingerabdrücke und Schlüssel
# ----------------------------------------------------------------------
def _encode(value) -> bytes:
    if value is None:
        return b"\x00"
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return b"b" + len(data).to_bytes(8, "big") + data
    data = str(value).encode("utf-8")
    return b"s" + len(data).to_bytes(8, "big") + data


def clean_ccli(value) -> str:
    """CCLI-Nummern bestehen nur aus Ziffern (Leerzeichen und Zusätze entfallen)."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def row_hash(values) -> str:
    digest = hashlib.sha1()
    for value in values:
        digest.update(_encode(value))
    return digest.hexdigest()


def make_key(nummer, seen: dict):
    """Eindeutiger Schlüssel eines Liedes: Nummer, bei doppelten Nummern mit Zähler (``p001#2``)."""
    if nummer is None:
        return None
    base = str(nummer).strip()
    if not base or base == "None":
        return None
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}#{seen[base]}"


def _pack(value):
    """Wert -> JSON-tauglich (Bytes als Base64, Zahlen bleiben Zahlen)."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"b": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, bool):
        return {"i": int(value)}
    if isinstance(value, int):
        return {"i": value}
    if isinstance(value, float):
        return {"f": value}
    return str(value)


def _unpack(value):
    if isinstance(value, dict):
        if "b" in value:
            return base64.b64decode(value["b"])
        if "i" in value:
            return int(value["i"])
        if "f" in value:
            return float(value["f"])
    return value


def _text_factory(raw: bytes):
    """Text als str lesen; Bytes, die kein gültiges UTF-8 sind (Bild/Audio im Text-Typ gespeichert), bleiben unverändert."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return bytes(raw)


def normalize_url(url: str) -> str:
    return (url or "").strip()


def url_problem(url: str) -> str:
    """Leer, wenn die Adresse brauchbar ist; sonst eine kurze Erklärung. Ohne HTTPS würde das Token offen übertragen."""
    url = normalize_url(url)
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https" and parts.netloc:
        return ""
    if parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1"):
        return ""       # nur zum Testen auf demselben Rechner
    return "Bitte die Server-Adresse mit https:// eintragen."


# ----------------------------------------------------------------------
# Verbindung zum Server
# ----------------------------------------------------------------------
def _ssl_context():
    """Zertifikate aus ``certifi`` (die gebaute Mac-App findet sonst keine); sonst die des Systems."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


class ServerApi:
    """Dünne Hülle um die JSON-Schnittstelle von ``sync.php``."""

    def __init__(self, url: str, token: str, timeout: float = REQUEST_TIMEOUT):
        self.url = normalize_url(url)
        self.token = (token or "").strip()
        self.timeout = timeout
        self._context = _ssl_context()

    def call(self, action: str, **params) -> dict:
        body = json.dumps({"token": self.token, "action": action, **params}, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "LiedManager-Sync"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self._context) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            raise SyncError(self._http_message(exc), exc.code) from exc
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise SyncError(f"Server nicht erreichbar ({reason})") from exc
        try:
            data = json.loads(payload)
        except ValueError as exc:
            raise SyncError("Unerwartete Antwort vom Server – stimmt die Adresse?") from exc
        if not isinstance(data, dict):
            raise SyncError("Unerwartete Antwort vom Server – stimmt die Adresse?")
        if "error" in data:
            raise SyncError(str(data["error"]))
        return data

    @staticmethod
    def _http_message(exc: urllib.error.HTTPError) -> str:
        if exc.code == 401:
            return "Token falsch – bitte in den Einstellungen prüfen."
        if exc.code in (404, 405):
            return "Server-Adresse falsch (sync.php nicht gefunden)."
        detail = ""
        try:
            detail = json.loads(exc.read()).get("error", "")
        except Exception:
            pass
        return f"Server meldet Fehler {exc.code}" + (f": {detail}" if detail else "")


# ----------------------------------------------------------------------
# Abgleich
# ----------------------------------------------------------------------
class ServerSync:
    def __init__(self, db_path, url, token, state_path, now_ms=None, api: Optional[ServerApi] = None,
                 force_upload: bool = False, on_progress=None, retry_failed: bool = False):
        """``force_upload``: Alles neu hochladen – die lokale Datenbank wird zum verbindlichen Stand für alle Geräte.
        ``on_progress(erledigt, gesamt)`` wird beim Senden nach jedem Lied aufgerufen (aus dem Abgleich-Thread)."""
        self.force_upload = force_upload
        self.cancelled = threading.Event()        # beim Beenden des Programms gesetzt: Abgleich bricht zwischen zwei Liedern ab
        self.retry_failed = retry_failed          # abgelehnte Lieder sofort erneut versuchen (statt erst nach einer Wartezeit)
        self._on_progress = on_progress
        self.db_path = str(db_path)
        self.url = normalize_url(url)
        self.token = (token or "").strip()
        self.state_path = str(state_path)
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._api = api

    # ------------------------------------------------------------------
    # Hauptablauf
    # ------------------------------------------------------------------
    def run_once(self) -> SyncResult:
        result = SyncResult()
        if not os.path.exists(self.db_path):
            result.error = "Die Datenbank wurde nicht gefunden."
            return result
        problem = url_problem(self.url)
        if problem:
            result.error = problem
            return result
        if not self.token:
            result.error = "Bitte ein Token eintragen."
            return result
        state = None
        try:
            api = self._api or ServerApi(self.url, self.token)
            state = self._open_state()
            self._send(state, result, api)
            self._receive(state, result, api)
        except SyncError as exc:
            log.warning("Abgleich fehlgeschlagen: %s", exc)
            result.error = str(exc)
        except (sqlite3.Error, OSError) as exc:
            log.warning("Abgleich fehlgeschlagen: %s", exc)
            result.error = f"Abgleich nicht möglich ({exc})"
        finally:
            if state is not None:
                state.close()
        return result

    # ------------------------------------------------------------------
    # Zustand (welcher Stand wurde zuletzt abgeglichen)
    # ------------------------------------------------------------------
    def _open_state(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self.state_path)), exist_ok=True)
        state = sqlite3.connect(self.state_path, timeout=LOCK_TIMEOUT)
        state.executescript(
            "CREATE TABLE IF NOT EXISTS known (key TEXT PRIMARY KEY, hash TEXT, ts INTEGER, dev TEXT, deleted INTEGER);"
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);"
        )
        if self._meta(state, "server") != self.url:          # anderer Server: Abholstand von vorn
            self._set_meta(state, "cursor", 0)
            self._set_meta(state, "server", self.url)
            state.commit()
        return state

    @staticmethod
    def _meta(state, key, default=None):
        row = state.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    @staticmethod
    def _set_meta(state, key, value) -> None:
        state.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))

    def _device_id(self, state) -> str:
        device = self._meta(state, "device")
        if not device:
            device = uuid.uuid4().hex[:8]
            self._set_meta(state, "device", device)
            state.commit()
        return device

    def _next_ts(self, state) -> int:
        """Zeitstempel in Millisekunden, pro Gerät streng steigend und immer jünger als alles bisher Gesehene."""
        ts = max(self._now_ms(), int(self._meta(state, "last_ts", 0)) + 1)
        self._set_meta(state, "last_ts", ts)
        return ts

    def _seen_ts(self, state, ts: int) -> None:
        """Merkt sich fremde Zeitstempel, damit eigene Änderungen danach immer jünger sind (auch bei falscher Uhr)."""
        if ts > int(self._meta(state, "last_ts", 0)):
            self._set_meta(state, "last_ts", ts)

    def _signature(self) -> str:
        parts = []
        for suffix in ("", "-wal"):
            try:
                stat = os.stat(self.db_path + suffix)
                parts.append(f"{stat.st_size}:{stat.st_mtime_ns}")
            except OSError:
                parts.append("-")
        return "|".join(parts)

    # ------------------------------------------------------------------
    # Lokale Datenbank lesen
    # ------------------------------------------------------------------
    def _connect_local(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=LOCK_TIMEOUT)
        conn.text_factory = _text_factory      # sonst bricht SQLite bei Medien im Text-Typ mit „Could not decode“ ab
        return conn

    @staticmethod
    def _local_columns(conn) -> list:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(Data)")]
        if KEY_COLUMN not in columns:
            raise sqlite3.Error("Tabelle „Data“ mit Spalte „nummer“ fehlt")
        return [c for c in CONTENT_COLUMNS if c in columns]

    @staticmethod
    def _ccli_col(conn) -> str:
        """Name der Spalte für die CCLI-Nummer (jede Spalte, deren Name „ccli“ enthält), sonst leer."""
        for row in conn.execute("PRAGMA table_info(Data)"):
            if "ccli" in str(row[1]).lower():
                return str(row[1])
        return ""

    @staticmethod
    def _fingerprints(conn, columns) -> dict:
        """Schlüssel -> (Fingerabdruck, rowid). Liest Zeile für Zeile, auch bei sehr großen Audios.
        Die CCLI-Nummer fließt nur ein, wenn eine eingetragen ist – Lieder ohne Nummer behalten ihren bisherigen Wert."""
        found = {}
        seen = {}
        ccli_col = ServerSync._ccli_col(conn)
        select = ", ".join(("rowid", KEY_COLUMN) + tuple(columns) + ((f'"{ccli_col}"',) if ccli_col else ()))
        for row in conn.execute(f"SELECT {select} FROM Data ORDER BY rowid"):
            key = make_key(row[1], seen)
            if key is not None:
                values = tuple(row[2:2 + len(columns)])
                ccli = clean_ccli(row[-1]) if ccli_col else ""
                found[key] = (row_hash(values + ((ccli,) if ccli else ())), row[0])
        return found

    @staticmethod
    def _key_map(conn) -> dict:
        seen = {}
        mapping = {}
        for rowid, nummer in conn.execute(f"SELECT rowid, {KEY_COLUMN} FROM Data ORDER BY rowid"):
            key = make_key(nummer, seen)
            if key is not None:
                mapping[key] = rowid
        return mapping

    @staticmethod
    def _song_payload(conn, columns, rowid) -> str:
        """Ein Lied als JSON-Text (so wie es auf dem Server liegt)."""
        ccli_col = ServerSync._ccli_col(conn)
        select = ", ".join((KEY_COLUMN,) + tuple(columns) + ((f'"{ccli_col}"',) if ccli_col else ()))
        values = conn.execute(f"SELECT {select} FROM Data WHERE rowid = ?", (rowid,)).fetchone()
        by_name = dict(zip(columns, values[1:1 + len(columns)]))
        payload = {"nummer": _pack(values[0]), "cols": {c: _pack(by_name.get(c)) for c in CONTENT_COLUMNS}}
        if ccli_col:                                        # leer mitsenden: so wird auch ein Löschen weitergegeben
            payload["cols"]["ccli"] = clean_ccli(values[-1])
        return json.dumps(payload, separators=(",", ":"))

    # ------------------------------------------------------------------
    # Senden
    # ------------------------------------------------------------------
    def _send(self, state, result: SyncResult, api: ServerApi) -> None:
        device = self._device_id(state)
        baseline_done = self._meta(state, "baseline") == "1"
        signature = self._signature()
        force = self.force_upload
        if self.retry_failed and not force and int(self._meta(state, "failed_count", 0)):
            for name in [row[0] for row in state.execute("SELECT key FROM meta WHERE key LIKE 'fail:%'")]:
                state.execute("DELETE FROM meta WHERE key = ?", (name,))
            self._set_meta(state, "signature", "")    # kein vorzeitiges „nichts geändert“
            state.commit()
        retry_at = float(self._meta(state, "retry_at", 0))       # > 0: abgelehnte Lieder warten auf einen neuen Versuch
        if (not force and baseline_done and self._meta(state, "signature") == signature
                and (not retry_at or time.time() < retry_at)):
            result.failed = int(self._meta(state, "failed_count", 0))
            result.failed_songs = [n for n in str(self._meta(state, "failed_names", "")).split("|") if n]
            return                                    # Datenbank unverändert seit dem letzten Abgleich

        conn = self._connect_local()
        try:
            columns = self._local_columns(conn)
            current = self._fingerprints(conn, columns)

            if not baseline_done and not force:       # erster Lauf: aktuellen Stand als Ausgangspunkt merken
                state.executemany("INSERT OR REPLACE INTO known (key, hash, ts, dev, deleted) VALUES (?, ?, 0, '', 0)",
                                  [(key, value[0]) for key, value in current.items()])
                self._set_meta(state, "baseline", "1")
                self._set_meta(state, "signature", signature)
                state.commit()
                result.baseline = True
                return

            known = {row[0]: row[1:] for row in state.execute("SELECT key, hash, ts, dev, deleted FROM known")}
            if force:
                if not current:
                    raise SyncError("Die lokale Datenbank enthält keine Lieder – es wird nichts hochgeladen.")
                # Alles neu hochladen: jedes lokale Lied gewinnt, was nur noch auf dem Server liegt, wird gelöscht
                on_server = self._live_keys_on_server(state, api)
                changed = list(current)
                removed = [key for key in (on_server | {k for k, row in known.items() if not row[3]})
                           if key not in current]
                for name in [row[0] for row in state.execute("SELECT key FROM meta WHERE key LIKE 'fail:%'")]:
                    state.execute("DELETE FROM meta WHERE key = ?", (name,))
                result.forced = True
                self._set_meta(state, "baseline", "1")
            else:
                changed = [key for key, (digest, _) in current.items()
                           if key not in known or known[key][3] or known[key][0] != digest]
                removed = [key for key, row in known.items() if not row[3] and key not in current]

            if changed or removed:
                ts = self._next_ts(state)
                state.commit()
                failures = 0
                total, done = len(changed) + len(removed), 0
                self._report(0, total)
                pool = ThreadPoolExecutor(max_workers=PUSH_WORKERS)
                try:
                    for start in range(0, len(changed), PUSH_WORKERS):
                        batch, jobs = changed[start:start + PUSH_WORKERS], []
                        for key in batch:             # Daten im Hauptthread lesen, Senden läuft parallel
                            digest, rowid = current[key]
                            if self._recently_failed(state, key, digest):
                                jobs.append((key, digest, "", None, "skip"))
                                continue
                            try:
                                data = self._song_payload(conn, columns, rowid)
                            except sqlite3.Error as exc:
                                jobs.append((key, digest, "", None, SyncError(str(exc), 500)))
                                continue
                            note = f" ({len(data) / 1_000_000:.0f} MB)"
                            if len(data) > MAX_SONG_BYTES:
                                jobs.append((key, digest, note, None, SyncError("Lied zu groß für den Server.", 413)))
                                continue
                            future = pool.submit(self._push_one, api, key, ts, device, digest, data)
                            jobs.append((key, digest, note, future, None))
                        for key, digest, note, future, problem in jobs:
                            if self.cancelled.is_set():
                                raise SyncError("Abgebrochen.")
                            done += 1
                            self._report(done - 1, total)
                            answer = None
                            if problem == "skip":
                                result.failed += 1
                                result.failed_songs.append(key)
                                continue
                            if problem is None:
                                try:
                                    answer = future.result()
                                except SyncError as exc:
                                    problem = exc
                            if problem is not None:
                                if problem.status not in (400, 413, 500):
                                    raise problem     # keine Verbindung / Token falsch: ganz abbrechen
                                log.warning("Lied %s vom Server abgelehnt: %s", key, problem)
                                self._set_meta(state, f"fail:{key}", f"{digest}:{int(time.time())}")
                                state.commit()
                                result.failed += 1
                                result.failed_songs.append(key + note)
                                if problem.status != 413:     # „zu groß“ ist ein Einzelfall und bricht den Abgleich nicht ab
                                    failures += 1
                                if failures >= MAX_FAILURES:
                                    raise SyncError(f"Der Server lehnt Lieder ab ({problem}).") from problem
                                continue
                            self._finish_push(state, result, answer, key, digest, ts, device, 0)
                finally:
                    pool.shutdown(wait=True, cancel_futures=True)
                for key in removed:
                    done += 1
                    self._report(done - 1, total)
                    old_hash = known[key][0] if key in known else ""
                    answer = api.call("push", key=key, ts=ts, dev=device, hash=old_hash, deleted=1, data=None)
                    self._finish_push(state, result, answer, key, old_hash, ts, device, 1)
                self._report(total, total)
            self._set_meta(state, "signature", signature)
            self._set_meta(state, "failed_count", result.failed)
            self._set_meta(state, "failed_names", "|".join(result.failed_songs[:50]))
            self._set_meta(state, "retry_at", time.time() + RETRY_FAILED_AFTER if result.failed else 0)
            state.commit()
        finally:
            conn.close()

    @staticmethod
    def _push_one(api, key, ts, device, digest, data):
        if len(data) <= PART_BYTES:
            return api.call("push", key=key, ts=ts, dev=device, hash=digest, deleted=0, data=data)
        uid = uuid.uuid4().hex                      # großes Lied: erst die Teile, dann der Eintrag
        parts = [data[i:i + PART_BYTES] for i in range(0, len(data), PART_BYTES)]
        for index, part in enumerate(parts):
            api.call("push_part", uid=uid, idx=index, data=part)
        return api.call("push", key=key, ts=ts, dev=device, hash=digest, deleted=0, data=None, parts=len(parts), uid=uid)

    def _report(self, done: int, total: int) -> None:
        if self._on_progress is not None:
            try:
                self._on_progress(done, total)
            except Exception:
                log.debug("Fortschrittsanzeige fehlgeschlagen", exc_info=True)

    def _live_keys_on_server(self, state, api: ServerApi) -> set:
        """Alle Lieder, die auf dem Server nicht gelöscht sind. Merkt sich dabei den jüngsten Zeitstempel,
        damit der neue Stand sicher jünger ist als alles, was dort liegt."""
        live = set()
        since = 0
        while True:
            page = api.call("list", since=since)
            for item in page.get("items", []):
                key = item.get("key", item.get("k"))
                self._seen_ts(state, int(item["ts"]))
                if item.get("deleted"):
                    live.discard(key)
                else:
                    live.add(key)
                since = int(item["seq"])
            if not page.get("more"):
                return live

    def _finish_push(self, state, result, answer, key, digest, ts, device, deleted) -> None:
        if answer.get("accepted"):
            state.execute("INSERT OR REPLACE INTO known (key, hash, ts, dev, deleted) VALUES (?, ?, ?, ?, ?)",
                          (key, digest, ts, device, deleted))
            state.execute("DELETE FROM meta WHERE key = ?", (f"fail:{key}",))
            result.sent += 1
        else:
            result.skipped += 1                       # auf dem Server liegt schon Jüngeres: kommt beim Empfangen
        state.commit()

    def _recently_failed(self, state, key, digest) -> bool:
        value = self._meta(state, f"fail:{key}")
        if not value:
            return False
        old_digest, _, when = value.rpartition(":")
        return old_digest == digest and time.time() - int(when or 0) < RETRY_FAILED_AFTER

    # ------------------------------------------------------------------
    # Empfangen
    # ------------------------------------------------------------------
    def _receive(self, state, result: SyncResult, api: ServerApi) -> None:
        device = self._device_id(state)
        cursor = int(self._meta(state, "cursor", 0))
        reset_checked = False
        while True:
            page = api.call("list", since=cursor)
            if int(page.get("format", FORMAT)) > FORMAT:
                raise SyncError("Der Server ist neuer als dieses Programm – bitte LiedManager aktualisieren.")
            if cursor > int(page.get("max", 0)) and not reset_checked:
                cursor = 0                            # Server wurde geleert/neu angelegt: von vorn abholen
                self._set_meta(state, "cursor", 0)
                state.commit()
                reset_checked = True
                continue
            reset_checked = True
            for item in page.get("items", []):
                if self.cancelled.is_set():
                    raise SyncError("Abgebrochen.")
                self._receive_item(state, result, api, item, device)
                cursor = int(item["seq"])
                self._set_meta(state, "cursor", cursor)
                state.commit()
            if not page.get("more"):
                break
        if result.received:
            self._set_meta(state, "signature", "")    # nächster Lauf prüft die Datenbank neu
            state.commit()

    def _receive_item(self, state, result: SyncResult, api: ServerApi, item: dict, device: str) -> None:
        key = item.get("key", item.get("k"))        # sync.php liefert die Spalte als „k“
        stamp = (int(item["ts"]), str(item["dev"]))
        self._seen_ts(state, stamp[0])
        known = state.execute("SELECT hash, ts, dev, deleted FROM known WHERE key = ?", (key,)).fetchone()
        if known is not None and (known[1], known[2]) >= stamp:
            if stamp[1] != device:
                result.skipped += 1                   # eigene Änderungen kommen als Echo zurück: nicht mitzählen
            return

        if item.get("deleted"):
            row = {"ts": stamp[0], "dev": stamp[1], "deleted": 1, "hash": known[0] if known else "", "data": None}
        else:
            answer = api.call("get", key=key)
            row = answer.get("row")
            if not row:
                return
            if row.get("parts"):                      # großes Lied: Teile einzeln abholen und zusammensetzen
                row["data"] = "".join(api.call("get_part", uid=row["uid"], idx=i)["data"] for i in range(int(row["parts"])))
            stamp = (int(row["ts"]), str(row["dev"]))
            self._seen_ts(state, stamp[0])
            if known is not None and (known[1], known[2]) >= stamp:
                return
        try:
            nummer, cols = self._decode_row(row)
        except (ValueError, KeyError, TypeError) as exc:
            log.warning("Lied %s vom Server nicht lesbar: %s", key, exc)
            result.failed += 1
            return
        self._apply_one(state, key, nummer, cols, row, stamp)
        result.received += 1

    @staticmethod
    def _decode_row(row: dict):
        if row.get("deleted"):
            return None, {}
        payload = json.loads(row["data"])
        return _unpack(payload["nummer"]), {c: _unpack(v) for c, v in payload["cols"].items()}

    def _apply_one(self, state, key, nummer, cols, row, stamp) -> None:
        """Übernimmt ein Lied (oder dessen Löschung) in einer einzigen Transaktion der lokalen Datenbank."""
        conn = self._connect_local()
        try:
            columns = self._local_columns(conn)
            mapping = self._key_map(conn)
            conn.execute("BEGIN IMMEDIATE")
            if row.get("deleted"):
                if key in mapping:
                    conn.execute("DELETE FROM Data WHERE rowid = ?", (mapping[key],))
            else:
                payload = [cols.get(c) for c in columns]
                if key in mapping:
                    conn.execute(f"UPDATE Data SET {', '.join(c + ' = ?' for c in columns)} WHERE rowid = ?",
                                 (*payload, mapping[key]))
                else:
                    insert_columns = [KEY_COLUMN] + columns
                    conn.execute(f"INSERT INTO Data ({', '.join(insert_columns)}) "
                                 f"VALUES ({', '.join('?' * len(insert_columns))})", (nummer, *payload))
                if "ccli" in cols:                          # Sender hat eine CCLI-Spalte (Wert evtl. leer)
                    ccli = clean_ccli(cols.get("ccli"))
                    ccli_col = self._ccli_col(conn)
                    if ccli and not ccli_col:
                        conn.execute("ALTER TABLE Data ADD COLUMN CCLI TEXT")      # Spalte bei Bedarf anlegen
                        ccli_col = "CCLI"
                    if ccli_col:
                        target = mapping[key] if key in mapping else conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                        conn.execute(f'UPDATE Data SET "{ccli_col}" = ? WHERE rowid = ?', (ccli or None, target))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
        state.execute("INSERT OR REPLACE INTO known (key, hash, ts, dev, deleted) VALUES (?, ?, ?, ?, ?)",
                      (key, row.get("hash", ""), stamp[0], stamp[1], 1 if row.get("deleted") else 0))
