"""Oberfläche des Datenbank-Abgleichs mit dem Server: läuft im Hintergrund, das Programm bleibt dabei ganz normal benutzbar."""
import logging
import time

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from paths import sync_state_path
from services import db_backup
from services.server_sync import ServerSync, SyncResult
from services.settings import app_settings

log = logging.getLogger(__name__)

KEY_SYNC_URL = "sync_url"
KEY_SYNC_TOKEN = "sync_token"
KEY_SYNC_AUTO = "sync_auto"          # automatisch (Start + jede Minute); aus = nur auf Knopfdruck
STATUS_OFF = "Aus"
STATUS_NO_URL = "Aus – keine Server-Adresse eingetragen"
STATUS_MANUAL = "Verbunden – Abgleich nur auf Knopfdruck (automatisch aus)"


class _SyncWorker(QThread):
    done = pyqtSignal(object)      # SyncResult
    progress = pyqtSignal(int, int)    # erledigt, gesamt (nur beim Senden)

    def __init__(self, db_path: str, url: str, token: str, force: bool = False, retry: bool = False, parent=None):
        super().__init__(parent)
        self._db_path, self._url, self._token, self._force, self._retry = db_path, url, token, force, retry
        self._sync = None

    def cancel(self) -> None:
        if self._sync is not None:
            self._sync.cancelled.set()

    def run(self):
        last = [-1]

        def report(done: int, total: int) -> None:
            percent = 100 if total <= 0 else int(100 * done / total)
            if percent != last[0]:                  # nur bei neuem Prozentwert melden (schont die Oberfläche)
                last[0] = percent
                self.progress.emit(done, total)

        try:
            try:                                              # Sicherung vor einem Abgleich (täglich) bzw. vor „Alles neu hochladen“
                if self._force:
                    db_backup.backup(self._db_path, reason="vor „Alles neu hochladen“")
                else:
                    db_backup.backup_if_due(self._db_path)
            except Exception:
                log.exception("Datenbank-Sicherung fehlgeschlagen")
            self._sync = ServerSync(self._db_path, self._url, self._token, sync_state_path(self._db_path),
                                    force_upload=self._force, on_progress=report, retry_failed=self._retry)
            result = self._sync.run_once()
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
        """An, sobald eine Server-Adresse eingetragen ist (ob automatisch abgeglichen wird, regelt „Automatisch abgleichen“)."""
        return bool(cls.url())

    @staticmethod
    def auto() -> bool:
        """Automatischer Abgleich (beim Start und jede Minute). Aus: die Verbindung bleibt, gesendet wird nur auf Knopfdruck."""
        return bool(app_settings().value(KEY_SYNC_AUTO, True, type=bool))

    @property
    def running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def configure(self) -> None:
        """Übernimmt Schalter und Adresse: ausgeschaltet (oder ohne Adresse) ist der Abgleich aus, Adresse und Token bleiben."""
        if self.enabled() and self.auto():
            self._timer.start()
        elif self.enabled():
            self._timer.stop()
            if not self.running:
                self._set_status(STATUS_MANUAL)
        else:
            self._timer.stop()
            self._set_status(STATUS_OFF)

    def run_now(self, url: str = None, token: str = None, force: bool = False, manual: bool = False) -> bool:
        """Startet einen Abgleich im Hintergrund. ``url``/``token``: Werte aus dem Einstellungsdialog.
        ``force``: Alles neu hochladen – die lokale Datenbank wird zum Stand für alle Geräte."""
        if url is None and not self.enabled():
            return False
        if url is None and not manual and not self.auto():
            return False                              # automatisch aus: nur auf Knopfdruck
        retry_known = url is not None                  # Knopf im Einstellungsdialog: abgelehnte Lieder neu versuchen
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
        self._worker = _SyncWorker(self._window.db.db_name, url, token, force, manual or force or retry_known, self)
        self._worker.done.connect(self._on_done)
        self._worker.progress.connect(lambda done, total, force=force: self._on_progress(done, total, force))
        self._worker.start()
        return True

    def _on_progress(self, done: int, total: int, force: bool) -> None:
        if self._worker is None or total <= 0:
            return
        percent = int(100 * done / total)
        what = "Lädt alles neu hoch" if force else "Sendet Änderungen"
        self._set_status(f"{what} … {percent} % ({done} von {total} Liedern)")

    def _on_done(self, result: SyncResult) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        stamp = time.strftime("%H:%M")
        text = f"{stamp} Uhr: {result.text()}" if result.ok else f"{stamp} Uhr: {result.error}"
        if result.ok and not self.auto():
            text += " (automatisch aus)"
        self._set_status(text)
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
            worker.cancel()             # bricht zwischen zwei Liedern ab (kein Warten auf den ganzen Abgleich)
            if not worker.wait(6_000):
                worker.terminate()      # ein einzelnes riesiges Lied hängt: SQLite rollt eine halbe Transaktion von selbst zurück
                worker.wait(3_000)
