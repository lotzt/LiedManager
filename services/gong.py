"""Gong: ein kurzer Klang auf Knopfdruck (zum Beispiel zum Beginn von Gebet oder Pause).

Die Klangdatei ist ``ui/assets/gong.wav``. Der Gong läuft über dasselbe
Ausgabegerät wie die Lieder (Einstellungen → Audio) und lässt ein laufendes Lied weiterspielen.
"""
from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

from paths import ASSETS_DIR
from services import devices
from services.settings import app_settings

GONG_FILE = ASSETS_DIR / "gong.wav"


class Gong(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._output.setVolume(1.0)
        self._player.setAudioOutput(self._output)
        self._player.setSource(QUrl.fromLocalFile(str(GONG_FILE)))
        self.apply_output_device()

    @property
    def available(self) -> bool:
        return GONG_FILE.exists()

    def apply_output_device(self) -> None:
        device = devices.find_output(str(app_settings().value(devices.KEY_OUTPUT, "")))
        if device is not None:
            self._output.setDevice(device)

    def play(self) -> bool:
        """Spielt den Gong von vorn (ein noch klingender Gong wird neu angeschlagen)."""
        if not self.available:
            return False
        self._player.stop()
        self._player.setPosition(0)
        self._player.play()
        return True

    @property
    def playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def toggle(self) -> bool:
        """Gong-Knopf: ein Klick schlägt an, ein Klick während des Klangs beendet ihn."""
        if self.playing:
            self._player.stop()
            return True
        return self.play()
