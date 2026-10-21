"""Oberfläche des Auto-Updaters: Suche im Hintergrund, Angebot, Download mit Fortschritt, Installer starten."""
import logging

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from paths import updates_dir
from services import updater
from services.settings import app_settings
from version import GITHUB_REPO, __version__

log = logging.getLogger(__name__)

KEY_CHECK_ON_START = "update_check_on_start"
KEY_SKIPPED = "update_skipped_version"


class _CheckWorker(QThread):
    done = pyqtSignal(object)      # UpdateInfo oder None
    failed = pyqtSignal(str)

    def __init__(self, repo, fetch, parent=None):
        super().__init__(parent)
        self._repo, self._fetch = repo, fetch

    def run(self):
        try:
            self.done.emit(updater.check(self._repo, __version__, fetch=self._fetch))
        except updater.UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:   # nie den Thread mit Absturz beenden
            log.exception("Update-Suche fehlgeschlagen")
            self.failed.emit(f"Unerwarteter Fehler: {exc}")


class _DownloadWorker(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self._info = info
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            path = updater.download(self._info, updates_dir(),
                                    progress=lambda read, total: self.progress.emit(read, total),
                                    cancelled=lambda: self._cancel)
            self.done.emit(str(path))
        except updater.UpdateCancelled:
            self.failed.emit("")
        except updater.UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            log.exception("Update-Download fehlgeschlagen")
            self.failed.emit(f"Unerwarteter Fehler: {exc}")


def check_on_start_enabled() -> bool:
    return app_settings().value(KEY_CHECK_ON_START, True, type=bool)


class UpdateController(QObject):
    """Verbindet ``services.updater`` mit dem Hauptfenster.

    ``fetch`` lässt sich für Tests ersetzen. Während Aufnahme, Pausentimer oder Beamer laufen, wird nichts installiert.
    """
    status_changed = pyqtSignal(str)    # Text für die Einstellungen („Aktuell“, „Version … verfügbar“ …)

    def __init__(self, window, repo: str = None, fetch=None):
        super().__init__(window)
        self.window = window
        self.repo = GITHUB_REPO if repo is None else repo
        self._fetch = fetch or updater.fetch_latest
        self._check_worker = None
        self._download_worker = None
        self._progress = None

    @property
    def available(self) -> bool:
        return bool(self.repo)

    # ------------------------------------------------------------------
    def check_on_start(self) -> None:
        updater.cleanup(updates_dir())      # Reste früherer Downloads
        if self.available and check_on_start_enabled():
            self.check(manual=False)

    def check(self, manual: bool = True) -> None:
        if self._check_worker is not None or self._download_worker is not None:
            return
        if not self.available:
            if manual:
                QMessageBox.information(self.window, "Updates", "Die Update-Suche ist in dieser Version nicht eingerichtet "
                                        "(das Programm läuft aus dem Quellcode).")
            return
        self.status_changed.emit("Suche nach Updates …")
        worker = _CheckWorker(self.repo, self._fetch, self)
        worker.done.connect(lambda info: self._on_checked(info, manual))
        worker.failed.connect(lambda message: self._on_check_failed(message, manual))
        worker.finished.connect(self._check_finished)
        self._check_worker = worker
        worker.start()

    def _check_finished(self) -> None:
        worker, self._check_worker = self._check_worker, None
        if worker is not None:
            worker.deleteLater()

    # ------------------------------------------------------------------
    def _on_check_failed(self, message: str, manual: bool) -> None:
        log.info("Update-Suche: %s", message)
        self.status_changed.emit("Update-Suche nicht möglich")
        if manual:
            QMessageBox.warning(self.window, "Updates", message)

    def _on_checked(self, info, manual: bool) -> None:
        if info is None:
            self.status_changed.emit(f"Version {__version__} ist aktuell")
            if manual:
                QMessageBox.information(self.window, "Updates", f"LiedManager {__version__} ist aktuell.")
            return
        self.status_changed.emit(f"Version {info.version} ist verfügbar")
        if not manual and app_settings().value(KEY_SKIPPED, "", type=str) == info.version:
            return
        self._offer(info)

    def blocking_reason(self) -> str:
        """Warum jetzt nicht installiert werden soll (leer = alles frei)."""
        w = self.window
        if w.recorder.state != "idle":
            return "Eine Aufnahme läuft noch. Bitte erst beenden."
        if w.pausentimer.running:
            return "Der Pausentimer läuft noch. Bitte erst beenden."
        shown = (w.presentation_window, w.gallery_window)
        if any(win is not None and win.isVisible() for win in shown):
            return "Das Beamer-Bild ist noch offen. Bitte erst schließen."
        return ""

    def _offer(self, info) -> None:
        notes = info.notes if len(info.notes) <= 700 else info.notes[:700].rstrip() + " …"
        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Neue Version verfügbar")
        box.setText(f"LiedManager {info.version} ist verfügbar (installiert: {__version__}).")
        if notes:
            box.setInformativeText(notes)
        install = box.addButton("Herunterladen und installieren", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Später", QMessageBox.ButtonRole.RejectRole)
        skip = box.addButton("Diese Version überspringen", QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is skip:
            app_settings().setValue(KEY_SKIPPED, info.version)
        elif clicked is install:
            self.start_install(info)

    # ------------------------------------------------------------------
    def start_install(self, info) -> None:
        reason = self.blocking_reason()
        if reason:
            QMessageBox.warning(self.window, "Update jetzt nicht möglich", reason)
            return
        progress = QProgressDialog(f"LiedManager {info.version} wird heruntergeladen …", "Abbrechen", 0, 100, self.window)
        progress.setWindowTitle("Update")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        worker = _DownloadWorker(info, self)
        worker.progress.connect(self._on_progress)
        worker.done.connect(lambda path: self._on_downloaded(path, info))
        worker.failed.connect(self._on_download_failed)
        worker.finished.connect(self._download_finished)
        progress.canceled.connect(worker.cancel)
        self._progress, self._download_worker = progress, worker
        worker.start()

    def _on_progress(self, read: int, total: int) -> None:
        if self._progress is not None and total > 0:
            self._progress.setValue(min(100, int(read * 100 / total)))

    def _download_finished(self) -> None:
        worker, self._download_worker = self._download_worker, None
        if worker is not None:
            worker.deleteLater()

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress.deleteLater()
            self._progress = None

    def _on_download_failed(self, message: str) -> None:
        self._close_progress()
        if message:    # leer = vom Nutzer abgebrochen
            QMessageBox.warning(self.window, "Update", message)

    def _on_downloaded(self, path: str, info) -> None:
        self._close_progress()
        reason = self.blocking_reason()     # während des Downloads kann etwas gestartet worden sein
        if reason:
            QMessageBox.warning(self.window, "Update jetzt nicht möglich",
                                f"{reason}\n\nDie Datei bleibt heruntergeladen; die Update-Suche kann später erneut gestartet werden.")
            return
        if updater.can_update_silently():
            QMessageBox.information(
                self.window, "Update installieren",
                f"LiedManager {info.version} wird jetzt installiert.\n\n"
                "LiedManager beendet sich dafür kurz und startet danach von selbst neu.",
            )
        else:
            QMessageBox.information(
                self.window, "Update installieren",
                f"Gleich öffnet sich das Fenster mit LiedManager {info.version}.\n\n"
                "LiedManager beendet sich jetzt. Ziehe danach die App im geöffneten Fenster auf „Programme“ "
                "und ersetze die alte Version.",
            )
        try:
            updater.launch_installer(path)
        except Exception as exc:
            QMessageBox.warning(self.window, "Update", f"Der Installer konnte nicht gestartet werden:\n{exc}\n\nDatei: {path}")
            return
        QApplication.closeAllWindows()     # schließt auch einen offenen Einstellungsdialog; closeEvent beendet Dienste sauber
