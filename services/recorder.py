"""Mikrofon-Aufnahme als WAV-Datei (Start / Pause / Fortsetzen / Speichern)."""
import datetime
import logging
import os
import wave
from array import array

from PyQt6.QtCore import QObject, QStandardPaths, QTimer, pyqtSignal
from PyQt6.QtMultimedia import QAudio, QAudioFormat, QAudioSource, QMediaDevices

from services import devices
from services.settings import app_settings

log = logging.getLogger(__name__)

IDLE, REC, PAUSED = "idle", "rec", "paused"

TICK_MS = 50          # Aktualisierungsrate von Zeit und Pegel (20 Bilder/s)
LEVEL_DECAY = 0.74    # Pegel-Abfall pro Tick, wenn nicht aufgenommen wird
MIN_WAV_BYTES = 44    # nur der WAV-Header = leere Aufnahme


def recordings_dir() -> str:
    default = os.path.join(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation),
        "LiedManager Aufnahmen",
    )
    path = str(app_settings().value("recording_path", default))
    if not path.strip():
        path = default
    os.makedirs(path, exist_ok=True)
    return path


def recording_filename(preacher: str, when: datetime.datetime = None) -> str:
    """„JJJJ.MM.TT - Prediger.wav“ (ohne Namen nur „JJJJ.MM.TT.wav“). Zeichen, die in Dateinamen nicht erlaubt sind, entfallen."""
    stamp = (when or datetime.datetime.now()).strftime("%Y.%m.%d")
    name = "".join(ch for ch in preacher if ch not in '<>:"/\\|?*' and ord(ch) >= 32)
    name = " ".join(name.split()).strip(" .")[:80].strip()
    return f"{stamp} - {name}.wav" if name else f"{stamp}.wav"


def _unique_path(path: str) -> str:
    base, ext = os.path.splitext(path)
    candidate, counter = path, 1
    while os.path.exists(candidate):
        candidate = f"{base} ({counter}){ext}"
        counter += 1
    return candidate


class AudioRecorder(QObject):
    """Nimmt vom gewählten Mikrofon auf.

    Signale:
        state_changed(str)        "idle" | "rec" | "paused"
        tick(float, float)        Aufnahmedauer in Sekunden, Pegel 0..1 (alle 50 ms)
        saved(str)                Pfad der fertigen Datei
        error(str)                Fehlermeldung für die Anzeige
    """
    state_changed = pyqtSignal(str)
    tick = pyqtSignal(float, float)
    saved = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = IDLE
        self._source = None
        self._io = None
        self._wav = None
        self._tmp_path = None
        self._bytes = 0
        self._bytes_per_sec = 1
        self._tail = b""
        self._peak = 0.0
        self._shown_level = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)

    @property
    def state(self) -> str:
        return self._state

    # ------------------------------------------------------------------
    # Steuerung
    # ------------------------------------------------------------------
    def toggle(self) -> None:
        """Idle -> Aufnahme starten, Aufnahme -> pausieren, Pause -> fortsetzen."""
        if self._state == IDLE:
            self._start()
        elif self._state == REC:
            self._source.suspend()
            self._set_state(PAUSED)
        else:
            self._source.resume()
            self._set_state(REC)

    def stop_and_save(self, preacher: str = ""):
        """Beendet die Aufnahme und speichert sie als „JJJJ.MM.TT - Prediger.wav“. Gibt den Dateipfad zurück (oder ``None``)."""
        if self._state == IDLE:
            return None

        self._timer.stop()
        self._release_capture()
        temp_path, self._tmp_path = self._tmp_path, None
        self._peak = self._shown_level = 0.0
        self._set_state(IDLE)
        self.tick.emit(0.0, 0.0)

        if not (temp_path and os.path.exists(temp_path)):
            return None
        if os.path.getsize(temp_path) <= MIN_WAV_BYTES:
            self._remove(temp_path)
            log.info("Aufnahme verworfen (zu kurz oder leer).")
            return None

        final_path = _unique_path(
            os.path.join(recordings_dir(), recording_filename(preacher))
        )
        try:
            os.rename(temp_path, final_path)
        except OSError as exc:
            log.error("Aufnahme konnte nicht gespeichert werden: %s", exc)
            self.error.emit(f"Die Aufnahme konnte nicht gespeichert werden:\n{exc}\n\nDatei: {temp_path}")
            return None

        log.info("Aufnahme gespeichert: %s", final_path)
        self.saved.emit(final_path)
        return final_path

    # ------------------------------------------------------------------
    # Intern
    # ------------------------------------------------------------------
    def _set_state(self, state: str) -> None:
        self._state = state
        self.state_changed.emit(state)

    def _start(self) -> None:
        try:
            self._open_capture()
        except Exception as exc:
            log.error("Aufnahme-Fehler: %s", exc)
            self._release_capture()
            if self._tmp_path:
                self._remove(self._tmp_path)
                self._tmp_path = None
            self.error.emit(str(exc))
            return
        self._bytes = 0
        self._tail = b""
        self._peak = self._shown_level = 0.0
        self._timer.start()
        self._set_state(REC)

    def _open_capture(self) -> None:
        device = devices.find_input(str(app_settings().value(devices.KEY_INPUT, "")))
        if device is None:
            device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            raise RuntimeError("Es wurde kein Mikrofon gefunden.")

        fmt = QAudioFormat()
        fmt.setSampleRate(44100)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()
            fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        self._bytes_per_sec = fmt.sampleRate() * fmt.channelCount() * 2
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._tmp_path = os.path.join(recordings_dir(), f"{timestamp}_temp_recording.wav")

        self._wav = wave.open(self._tmp_path, "wb")
        self._wav.setnchannels(fmt.channelCount())
        self._wav.setsampwidth(2)
        self._wav.setframerate(fmt.sampleRate())

        self._source = QAudioSource(device, fmt, self)
        self._io = self._source.start()
        if self._io is None or self._source.error() != QAudio.Error.NoError:
            raise RuntimeError(
                "Das Mikrofon konnte nicht gestartet werden.\n"
                "Bitte Mikrofon-Zugriff in den Systemeinstellungen erlauben."
            )
        self._io.readyRead.connect(self._on_ready_read)

    def _release_capture(self) -> None:
        if self._source is not None:
            self._source.stop()
            self._source.deleteLater()
            self._source = None
        self._io = None
        if self._wav is not None:
            try:
                self._wav.close()
            except Exception:
                pass
            self._wav = None

    @staticmethod
    def _remove(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    def _on_ready_read(self) -> None:
        if self._io is None or self._wav is None:
            return
        data = bytes(self._io.readAll())
        if not data:
            return
        self._bytes += len(data)
        self._wav.writeframes(data)

        combined = self._tail + data
        use_len = len(combined) & ~1  # nur ganze 16-Bit-Samples auswerten
        self._tail = combined[use_len:]
        if use_len:
            samples = array("h", combined[:use_len])
            peak = max(max(samples), -min(samples)) / 32768.0  # beide Aufrufe laufen in C
            self._peak = self._peak * 0.3 + peak * 0.7

    def _on_tick(self) -> None:
        if self._state == REC:
            self._shown_level = min(1.0, self._peak * 1.5)
        elif self._shown_level > 0:
            faded = self._shown_level * LEVEL_DECAY
            self._shown_level = 0.0 if faded < 0.01 else faded
        self.tick.emit(self._bytes / self._bytes_per_sec, self._shown_level)
