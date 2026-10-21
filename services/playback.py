"""Audio-Wiedergabe der im Lied gespeicherten Audiodateien."""
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

from services import devices
from services.settings import app_settings


class AudioPlayback(QObject):
    """Spielt Audiodaten direkt aus dem Speicher ab.

    Signale:
        progress(float)         Fortschritt in Prozent (0..100)
        playing_changed(bool)   True = Wiedergabe läuft
    """
    progress = pyqtSignal(float)
    playing_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buffer = None
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(lambda _ms: self.progress.emit(0.0))
        self.apply_output_device()

    def apply_output_device(self) -> None:
        """Wendet das in den Einstellungen gewählte Ausgabegerät an (leer = Systemstandard)."""
        device = devices.find_output(str(app_settings().value(devices.KEY_OUTPUT, "")))
        if device is not None:
            self._output.setDevice(device)

    def play_bytes(self, data: bytes) -> None:
        self.stop()
        buffer = QBuffer(self)
        buffer.setData(QByteArray(bytes(data)))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._buffer = buffer
        self._player.setSourceDevice(buffer, QUrl())
        self._player.play()

    def toggle(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def stop(self) -> None:
        """Stoppt und gibt die Audiodaten frei (wichtig: Audios können viele MB groß sein)."""
        self._player.stop()
        self._player.setSource(QUrl())
        if self._buffer is not None:
            self._buffer.close()
            self._buffer.deleteLater()
            self._buffer = None
        self.progress.emit(0.0)

    def seek_percent(self, percent: float) -> None:
        duration = self._player.duration()
        if duration > 0:
            self._player.setPosition(int(duration * percent / 100.0))

    def _on_state_changed(self, state) -> None:
        self.playing_changed.emit(state == QMediaPlayer.PlaybackState.PlayingState)

    def _on_position_changed(self, position_ms: int) -> None:
        duration = self._player.duration()
        if duration > 0:
            self.progress.emit(position_ms / duration * 100.0)
