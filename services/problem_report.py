"""Automatische Problemmeldung: unerwartete Fehler gehen (ohne Zutun) an die eigene Website (remote.php) und stehen dort
unter „Mehr“ → „Gemeldete Probleme“.

Gesendet wird nur: Programmversion, Betriebssystem, Fehlertext und Ablaufprotokoll (Traceback) – keine Liedtexte, keine
Zugangsdaten, keine Dateien. Pfade im Benutzerordner werden gekürzt. Gleiche Fehler werden nur einmal pro Programmstart
gesendet (der Server zählt sie hoch), höchstens ``MAX_PER_HOUR`` pro Stunde; ohne Internet bleibt die Meldung in einer
kleinen Warteschlange (Datei) und wird beim nächsten Mal gesendet. Abschalten: Einstellungen → Allgemein.
"""
import hashlib
import json
import logging
import platform
import re
import sys
import threading
import time
import traceback

from paths import user_data_dir
from services.settings import app_settings

log = logging.getLogger(__name__)

KEY_ENABLED = "problem_report_enabled"
KEY_SITE_ENABLED = "web_site_enabled"
KEY_SITE_URL = "web_site_url"
KEY_SITE_TOKEN = "web_site_token"
MAX_PER_HOUR = 10
QUEUE_MAX = 20
DETAIL_MAX = 5000
SEND_EVERY = 30.0            # Sekunden zwischen Versuchen, die Warteschlange zu leeren

_lock = threading.Lock()
_seen = set()                # Fingerabdrücke, die in diesem Programmlauf schon gemeldet wurden
_sent_times = []
_installed = False
_sender_running = False


def is_enabled() -> bool:
    try:
        return bool(app_settings().value(KEY_ENABLED, True, type=bool))
    except Exception:
        return False


def _target():
    """(Adresse, Token), wenn die Web-Steuerung eingerichtet ist, sonst ``None``."""
    try:
        s = app_settings()
        if not s.value(KEY_SITE_ENABLED, False, type=bool):
            return None
        url = str(s.value(KEY_SITE_URL, "", type=str)).strip()
        token = str(s.value(KEY_SITE_TOKEN, "", type=str)).strip()
    except Exception:
        return None
    return (url, token) if url and token else None


def scrub(text: str) -> str:
    """Entfernt Benutzernamen aus Pfaden und alles, was wie ein Zugangsdatum aussieht."""
    text = re.sub(r"(?i)([A-Z]:\\Users\\)[^\\\s]+", r"\1…", text)
    text = re.sub(r"(/Users/|/home/)[^/\s]+", r"\1…", text)
    text = re.sub(r"(?i)(token|passwort|password|pin|secret|authorization)(['\"]?\s*[:=]\s*)\S+", r"\1\2…", text)
    return text


def fingerprint(title: str, detail: str) -> str:
    """Gleiche Ursache = gleicher Wert: Fehlerart plus letzte Programmzeile des Tracebacks, ohne Zeilennummern/Zahlen."""
    frames = [line for line in detail.splitlines() if line.strip().startswith("File ")]
    key = re.sub(r"\d+", "#", title) + "|" + re.sub(r"line \d+", "", frames[-1] if frames else "")
    return hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:16]


def _queue_file():
    return user_data_dir() / "problemmeldungen.json"


def _load_queue() -> list:
    try:
        data = json.loads(_queue_file().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save_queue(queue: list) -> None:
    try:
        if queue:
            _queue_file().write_text(json.dumps(queue[-QUEUE_MAX:], ensure_ascii=False), encoding="utf-8")
        else:
            _queue_file().unlink(missing_ok=True)
    except OSError:
        pass


def report(title: str, detail: str = "") -> bool:
    """Meldung vormerken (und im Hintergrund senden). ``False``: aus, doppelt oder zu viele."""
    if not is_enabled() or _target() is None:
        return False
    title = scrub(" ".join(str(title).split()))[:300]
    detail = scrub(detail)[-DETAIL_MAX:]
    fp = fingerprint(title, detail)
    now = time.time()
    with _lock:
        if fp in _seen:
            return False
        _sent_times[:] = [t for t in _sent_times if now - t < 3600]
        if len(_sent_times) >= MAX_PER_HOUR:
            return False
        _seen.add(fp)
        _sent_times.append(now)
        queue = _load_queue()
        queue.append({"fp": fp, "title": title, "detail": detail, "version": _version(), "system": _system(), "at": int(now)})
        _save_queue(queue)
    _start_sender()
    return True


def _version() -> str:
    try:
        from version import __version__
        return __version__
    except Exception:
        return "?"


def _system() -> str:
    return f"{platform.system()} {platform.release()} · Python {platform.python_version()}"[:80]


def _start_sender() -> None:
    global _sender_running
    with _lock:
        if _sender_running:
            return
        _sender_running = True
    threading.Thread(target=_send_loop, name="problem-report", daemon=True).start()


def _send_loop() -> None:
    global _sender_running
    try:
        for _attempt in range(4):
            if not flush():
                time.sleep(SEND_EVERY)
            else:
                break
    finally:
        with _lock:
            _sender_running = False


def flush(api=None) -> bool:
    """Wartende Meldungen senden. ``True``, wenn die Warteschlange danach leer ist (oder es nichts zu tun gibt)."""
    target = _target()
    if target is None:
        return True
    with _lock:
        queue = _load_queue()
    if not queue:
        return True
    if api is None:
        from services.remote_relay import RemoteApi
        api = RemoteApi(target[0], target[1], 15)
    remaining = []
    for item in queue:
        try:
            api.call("report", fp=item.get("fp", ""), title=item.get("title", ""), detail=item.get("detail", ""),
                     version=item.get("version", ""), system=item.get("system", ""))
        except Exception as exc:                      # offline, Token falsch, alte remote.php … später nochmal
            remaining.append(item)
            log.debug("Problemmeldung nicht gesendet: %s", exc)
            remaining.extend(queue[queue.index(item) + 1:])
            break
    with _lock:
        _save_queue(remaining)
    return not remaining


class _LogHandler(logging.Handler):
    """Fehler aus dem Protokoll (``log.error``/``log.exception``) werden ebenfalls gemeldet."""
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR or record.name.startswith("services.problem_report"):
            return
        try:
            detail = "".join(traceback.format_exception(*record.exc_info)) if record.exc_info else ""
            report(f"{record.name}: {record.getMessage()}", detail)
        except Exception:
            pass


def install() -> None:
    """Einmal beim Start: unbehandelte Fehler (Hauptthread, Threads) und ``log.error`` automatisch melden."""
    global _installed
    if _installed:
        return
    _installed = True
    previous_hook = sys.excepthook

    def hook(exc_type, exc, tb):
        try:
            report(f"{exc_type.__name__}: {exc}", "".join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:
            pass
        previous_hook(exc_type, exc, tb)

    sys.excepthook = hook
    previous_thread_hook = threading.excepthook

    def thread_hook(args):
        try:
            if args.exc_type is not SystemExit:
                report(f"{args.exc_type.__name__}: {args.exc_value}",
                       "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
        except Exception:
            pass
        previous_thread_hook(args)

    threading.excepthook = thread_hook
    logging.getLogger().addHandler(_LogHandler(level=logging.ERROR))
    _start_sender()                                    # Meldungen vom letzten Mal (z. B. Absturz ohne Internet) nachsenden
