"""Oberfläche des Datenbank-Abgleichs mit dem Server: läuft im Hintergrund, das Programm bleibt dabei ganz normal benutzbar."""
import logging
import time

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from paths import sync_state_path
from services.server_sync import ServerSync, SyncResult
from services.settings import app_settings

log = logging.getLogger(__name__)

KEY_SYNC_URL = "sync_url"
KEY_SYNC_TOKEN = "sync_token"
KEY_SYNC_ENABLED = "sync_enabled"
STATUS_OFF = "Aus"
STATUS_NO_URL = "Aus – keine Server-Adresse eingetragen"


class _SyncWorker(QThread):
    done = pyqtSignal(object)      # SyncResult

    def __init__(self, db_path: str, url: str, token: str, force: bool = False, parent=None):
        super().__init__(parent)
        self._db_path, self._url, self._token, self._force = db_path, url, token, force

    def run(self):
        try:
            result = ServerSync(self._db_path, self._url, self._token, sync_state_path(self._db_path),
                                force_upload=self._force).run_once()
        except Exception as exc:   # nie den Thread mit Absturz beenden
            log.exception("Datenbank-Abgleich fehlgeschlagen")
            result = SyncResult(error=f"Unerwarteter Fehler: {exc}")
        self.done.emit(result)


class SyncController(QObject):
    """Gleicht die Datenbank regelmäßig mit dem Server ab (Start, jede Minute, auf Knopfdruck). Ohne Internet: nächster Versuch."""

    INTERVAL_MS = 60_000

    status_changed = pyqtSignal(str)
    database_changed = pyqtSignal()       # es wurden Änderungen anderer Geräte übernommen

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._worker = None
        self.status = STATUS_OFF
        self._timer = QTimer(self)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self.run_now)

    @staticmethod
    def url() -> str:
        return str(app_settings().value(KEY_SYNC_URL, "", type=str)).strip()

    @staticmethod
    def token() -> str:
        return str(app_settings().value(KEY_SYNC_TOKEN, "", type=str)).strip()

    @classmethod
    def enabled(cls) -> bool:
        """An, wenn eingeschaltet und eine Adresse da ist. Wer vor dem Schalter schon eine Adresse hatte, bleibt an."""
        flag = app_settings().value(KEY_SYNC_ENABLED, None)
        on = bool(cls.url()) if flag is None else str(flag).lower() in ("true", "1")
        return on and bool(cls.url())

    @property
    def running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def configure(self) -> None:
        """Übernimmt Schalter und Adresse: ausgeschaltet (oder ohne Adresse) ist der Abgleich aus, Adresse und Token bleiben."""
        if self.enabled():
            self._timer.start()
        else:
            self._timer.stop()
            self._set_status(STATUS_NO_URL if str(app_settings().value(KEY_SYNC_ENABLED, "")).lower() in ("true", "1")
                             and not self.url() else STATUS_OFF)

    def run_now(self, url: str = None, token: str = None, force: bool = False) -> bool:
        """Startet einen Abgleich im Hintergrund. ``url``/``token``: Werte aus dem Einstellungsdialog.
        ``force``: Alles neu hochladen – die lokale Datenbank wird zum Stand für alle Geräte."""
        if url is None and not self.enabled():
            return False
        url = (url if url is not None else self.url()).strip()
        token = (token if token is not None else self.token()).strip()
        if not url:
            self._set_status(STATUS_NO_URL)
            return False
        if self.running:
            return False
        if not self._window.db.available:
            self._set_status("Datenbank nicht gefunden – Abgleich nicht möglich.")
            return False
        self._set_status("Lädt alles neu hoch …" if force else "Gleicht ab …")
        self._worker = _SyncWorker(self._window.db.db_name, url, token, force, self)
        self._worker.done.connect(self._on_done)
        self._worker.start()
        return True

    def _on_done(self, result: SyncResult) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        stamp = time.strftime("%H:%M")
        self._set_status(f"{stamp} Uhr: {result.text()}" if result.ok else f"{stamp} Uhr: {result.error}")
        if result.changed_database:
            log.info("Abgleich: %d Lieder übernommen", result.received)
            self.database_changed.emit()

    def _set_status(self, text: str) -> None:
        self.status = text
        self.status_changed.emit(text)

    def shutdown(self) -> None:
        """Beim Beenden: Zeitgeber stoppen und einen laufenden Abgleich zu Ende laufen lassen."""
        self._timer.stop()
        worker = self._worker
        if worker is not None and worker.isRunning():
            if not worker.wait(20_000):
                worker.terminate()      # sehr großer Abgleich: SQLite rollt eine halbe Transaktion von selbst zurück
                worker.wait(3_000)
