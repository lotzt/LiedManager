"""Ansteuerung des Blackmagic-ATEM-Mischers (macOS und Windows).

Unterstützte Module (das erste vorhandene wird genommen):
  * ``ATEM``        – das bisher verwendete Modul (API: ATEM.ATEM(ip).connect/changeProgramInput/disconnect)
  * ``PyATEMMax``   – wird beim Programmstart automatisch installiert

Die Netzwerkzugriffe laufen in einem Hintergrund-Thread. Ist der Mischer nicht erreichbar, friert die
Oberfläche dadurch nicht ein. Schaltbefehle werden in der Reihenfolge abgearbeitet, in der sie gegeben wurden.
"""
import importlib
import logging
import queue
import threading
import time

from services.settings import app_settings

log = logging.getLogger(__name__)

DEFAULT_IP = "192.168.10.240"
CONNECT_TIMEOUT = 5.0

# Kanal-Art -> (Einstellungs-Schlüssel, Standardkanal)
CHANNELS = {
    "presentation": ("atem_pres_channel", 3),
    "camera": ("atem_cam_channel", 4),
    "default": ("atem_default_channel", 1),
    "start": ("atem_start_channel", 0),        # beim Programmstart; 0 = Schwarz (Black) des ATEM
}
BLACK = 0

_jobs: "queue.Queue[tuple[str, int]]" = queue.Queue()
_worker = None
_worker_lock = threading.Lock()


def _backend():
    """Liefert ("legacy" | "pyatemmax", Modul) oder (None, None)."""
    for kind, name in (("legacy", "ATEM"), ("pyatemmax", "PyATEMMax")):
        try:
            return kind, importlib.import_module(name)
        except ImportError:
            continue
    return None, None


def available() -> bool:
    return _backend()[0] is not None


def _wait_connected(switcher) -> None:
    try:
        ok = switcher.waitForConnection(infinite=False, timeout=CONNECT_TIMEOUT)
    except TypeError:  # ältere Version ohne Parameter -> selbst abfragen
        deadline = time.monotonic() + CONNECT_TIMEOUT
        ok = False
        while time.monotonic() < deadline:
            if getattr(switcher, "connected", False):
                ok = True
                break
            time.sleep(0.1)
    if ok is False:
        raise ConnectionError("Der ATEM antwortet nicht (IP-Adresse prüfen).")


def _switch_blocking(ip: str, channel: int) -> None:
    kind, module = _backend()
    if kind == "legacy":
        switcher = module.ATEM(ip)
        switcher.connect()
        try:
            switcher.changeProgramInput(channel)
        finally:
            switcher.disconnect()
    elif kind == "pyatemmax":
        switcher = module.ATEMMax()
        switcher.connect(ip)
        try:
            _wait_connected(switcher)
            switcher.setProgramInputVideoSource(0, channel)  # Mix-Effekt 1, Eingang = Kanalnummer
            time.sleep(0.3)  # Paket noch rausgehen lassen, bevor getrennt wird
        finally:
            switcher.disconnect()
    else:
        raise RuntimeError("Kein ATEM-Modul installiert.")


def _worker_loop() -> None:
    while True:
        ip, channel = _jobs.get()
        try:
            _switch_blocking(ip, channel)
        except Exception as exc:
            log.warning("ATEM-Umschaltung auf Kanal %s fehlgeschlagen: %s", channel, exc)
        finally:
            _jobs.task_done()


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_worker_loop, name="atem-worker", daemon=True)
            _worker.start()


def switch(kind: str) -> None:
    """Schaltet den Mischer auf den Kanal ``kind`` ("presentation", "camera", "default" oder "start"; 0 = Schwarz).

    Tut nichts, wenn die Ansteuerung deaktiviert ist, kein ATEM-Modul vorhanden ist oder keine IP gesetzt wurde.
    """
    settings = app_settings()
    if not settings.value("atem_enabled", False, type=bool) or not available():
        return
    ip = settings.value("atem_ip", DEFAULT_IP, type=str).strip()
    if not ip:
        return
    key, default = CHANNELS[kind]
    _jobs.put((ip, settings.value(key, default, type=int)))
    _ensure_worker()


def wait_idle(timeout: float = 2.0) -> None:
    """Wartet beim Beenden kurz, bis ausstehende Schaltbefehle (z. B. „Standardkanal“) gesendet sind."""
    deadline = time.monotonic() + timeout
    while _jobs.unfinished_tasks and time.monotonic() < deadline:
        time.sleep(0.05)


def test_connection(ip: str) -> tuple[bool, str]:
    """Baut testweise eine Verbindung auf (blockierend – nur aus einem Hintergrund-Thread aufrufen)."""
    kind, module = _backend()
    if kind is None:
        return False, "Kein ATEM-Modul installiert (PyATEMMax)."
    try:
        if kind == "legacy":
            switcher = module.ATEM(ip)
            switcher.connect()
            switcher.disconnect()
        else:
            switcher = module.ATEMMax()
            switcher.connect(ip)
            try:
                _wait_connected(switcher)
            finally:
                switcher.disconnect()
        return True, "Verbunden"
    except Exception as exc:
        return False, str(exc) or "Keine Verbindung"
