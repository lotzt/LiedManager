"""Behringer X AIR 18 (und X AIR 16/12) über das Netzwerk steuern: Fader und Mute der Kanäle 1–8.

Das Pult spricht OSC über UDP (Port 10024). Dieses Modul kennt Qt nicht und braucht keine Zusatzpakete.
* Fader:  ``/ch/01/mix/fader``  Gleitkommazahl 0.0 … 1.0 (0.75 ≈ 0 dB)
* Mute:   ``/ch/01/mix/on``     Ganzzahl, 1 = Kanal an, 0 = stummgeschaltet
* Name:   ``/ch/01/config/name``
Damit das Pult Änderungen zurückmeldet, wird ``/xremote`` alle paar Sekunden erneuert. Alle Netzwerkzugriffe laufen in
einem Hintergrund-Thread, die Oberfläche friert also nie ein.
"""
import logging
import socket
import struct
import threading
import time

log = logging.getLogger(__name__)

PORT = 10024
CHANNELS = 8
RENEW_EVERY = 7.0          # das Pult vergisst „xremote“ nach etwa 10 s
LIVE_FOR = 15.0            # so lange gilt das Pult als verbunden, wenn es Antworten schickt
KEY_ENABLED = "xair_enabled"
KEY_IP = "xair_ip"


# ----------------------------------------------------------------------
# OSC (nur das, was das X AIR braucht: Texte, Ganzzahlen, Kommazahlen)
# ----------------------------------------------------------------------
def _pad(raw: bytes) -> bytes:
    return raw + b"\x00" * (4 - len(raw) % 4)


def osc_encode(address: str, *args) -> bytes:
    tags, payload = ",", b""
    for arg in args:
        if isinstance(arg, bool):
            arg = int(arg)
        if isinstance(arg, int):
            tags += "i"
            payload += struct.pack(">i", arg)
        elif isinstance(arg, float):
            tags += "f"
            payload += struct.pack(">f", arg)
        else:
            tags += "s"
            payload += _pad(str(arg).encode("utf-8"))
    return _pad(address.encode("utf-8")) + _pad(tags.encode("ascii")) + payload


def _read_string(data: bytes, pos: int):
    end = data.index(b"\x00", pos)
    return data[pos:end].decode("utf-8", "replace"), (end + 4) // 4 * 4


def osc_decode(data: bytes):
    """(Adresse, [Werte]) oder ``None``, wenn das Paket nicht lesbar ist (Bündel werden ignoriert)."""
    try:
        if not data.startswith(b"/"):
            return None
        address, pos = _read_string(data, 0)
        if pos >= len(data):
            return address, []
        tags, pos = _read_string(data, pos)
        values = []
        for tag in tags[1:]:
            if tag == "i":
                values.append(struct.unpack(">i", data[pos:pos + 4])[0])
                pos += 4
            elif tag == "f":
                values.append(struct.unpack(">f", data[pos:pos + 4])[0])
                pos += 4
            elif tag == "s":
                text, pos = _read_string(data, pos)
                values.append(text)
            else:
                break
        return address, values
    except (ValueError, struct.error):
        return None


def fader_db(level: float) -> float:
    """Fader (0..1) in dB – so rechnet das X AIR. 0 ergibt ``-inf``."""
    if level <= 0:
        return float("-inf")
    if level >= 0.5:
        return level * 40 - 30
    if level >= 0.25:
        return level * 80 - 50
    if level >= 0.0625:
        return level * 160 - 70
    return level * 480 - 90


# ----------------------------------------------------------------------
class XAirMixer:
    """Verbindung zum Pult. ``start()`` öffnet den Hintergrund-Thread, ``stop()`` beendet ihn."""

    def __init__(self, ip: str = "", port: int = PORT):
        self.ip, self.port = ip.strip(), port
        self._lock = threading.Lock()
        self._levels = {n: None for n in range(1, CHANNELS + 1)}
        self._mutes = {n: None for n in range(1, CHANNELS + 1)}
        self._names = {n: "" for n in range(1, CHANNELS + 1)}
        self._last_seen = 0.0
        self._sock = None
        self._thread = None
        self._stop = threading.Event()

    # --- Zustand -------------------------------------------------------
    @property
    def connected(self) -> bool:
        return time.monotonic() - self._last_seen < LIVE_FOR if self._last_seen else False

    def state(self) -> dict:
        with self._lock:
            channels = [{"n": n, "name": self._names[n], "level": self._levels[n], "mute": self._mutes[n]}
                        for n in range(1, CHANNELS + 1)]
        return {"connected": self.connected, "channels": channels}

    # --- Befehle -------------------------------------------------------
    def set_level(self, channel: int, level: float) -> None:
        channel = self._check(channel)
        level = max(0.0, min(1.0, float(level)))
        with self._lock:
            self._levels[channel] = level           # sofort anzeigen; das Pult bestätigt es gleich
        self._send(osc_encode(f"/ch/{channel:02d}/mix/fader", level))

    def set_mute(self, channel: int, muted: bool) -> None:
        channel = self._check(channel)
        with self._lock:
            self._mutes[channel] = bool(muted)
        self._send(osc_encode(f"/ch/{channel:02d}/mix/on", 0 if muted else 1))

    def mute_all(self) -> None:
        """Alle Kanäle stumm (ein Knopf für den Notfall)."""
        for n in range(1, CHANNELS + 1):
            self.set_mute(n, True)

    def refresh(self) -> None:
        """Fragt alle Werte neu ab (ein Befehl ohne Wert wird vom Pult mit dem aktuellen Wert beantwortet)."""
        for n in range(1, CHANNELS + 1):
            for leaf in ("mix/fader", "mix/on", "config/name"):
                self._send(osc_encode(f"/ch/{n:02d}/{leaf}"))

    @staticmethod
    def _check(channel) -> int:
        channel = int(channel)
        if not 1 <= channel <= CHANNELS:
            raise ValueError("Unbekannter Kanal.")
        return channel

    def _send(self, packet: bytes) -> None:
        sock = self._sock
        if sock is None or not self.ip:
            return
        try:
            sock.sendto(packet, (self.ip, self.port))
        except OSError as exc:
            log.debug("X AIR: Senden fehlgeschlagen: %s", exc)

    # --- Hintergrund-Thread -------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        if not self.ip:
            return
        self._stop.clear()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        self._sock = sock
        self._thread = threading.Thread(target=self._run, name="xair", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=1.5)
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self._last_seen = 0.0

    def _run(self) -> None:
        next_renew = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_renew:
                self._send(osc_encode("/xremote"))
                if not self._last_seen or not self.connected:
                    self.refresh()                       # noch nichts gehört: alles erfragen
                next_renew = now + RENEW_EVERY
            sock = self._sock
            if sock is None:
                return
            try:
                data, _addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                time.sleep(0.5)
                continue
            self._handle(data)

    def _handle(self, data: bytes) -> None:
        decoded = osc_decode(data)
        if decoded is None:
            return
        address, values = decoded
        parts = address.split("/")                       # ['', 'ch', '01', 'mix', 'fader']
        self._last_seen = time.monotonic()
        if len(parts) != 5 or parts[1] != "ch" or not values or not parts[2].isdigit():
            return
        n = int(parts[2])
        if not 1 <= n <= CHANNELS:
            return
        with self._lock:
            if parts[3:] == ["mix", "fader"] and isinstance(values[0], float):
                self._levels[n] = max(0.0, min(1.0, values[0]))
            elif parts[3:] == ["mix", "on"] and isinstance(values[0], int):
                self._mutes[n] = values[0] == 0
            elif parts[3:] == ["config", "name"] and isinstance(values[0], str):
                self._names[n] = values[0]


# ----------------------------------------------------------------------
# Das eine Pult des Programms (Einstellungen: Adresse + Schalter)
# ----------------------------------------------------------------------
_mixer = None


def enabled() -> bool:
    from services.settings import app_settings
    return bool(app_settings().value(KEY_ENABLED, False, type=bool))


def configure() -> None:
    """Nach dem Programmstart und nach dem Speichern der Einstellungen aufrufen: startet/stoppt/aktualisiert die Verbindung."""
    global _mixer
    from services.settings import app_settings
    ip = str(app_settings().value(KEY_IP, "", type=str)).strip()
    if not enabled() or not ip:
        shutdown()
        return
    if _mixer is not None and _mixer.ip == ip:
        _mixer.start()
        return
    shutdown()
    _mixer = XAirMixer(ip)
    _mixer.start()


def shutdown() -> None:
    global _mixer
    mixer, _mixer = _mixer, None
    if mixer is not None:
        mixer.stop()


def mixer():
    return _mixer


def state() -> dict:
    current = _mixer
    if current is None:
        return {"enabled": enabled(), "connected": False, "channels": []}
    result = current.state()
    result["enabled"] = True
    return result
