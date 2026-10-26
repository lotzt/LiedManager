"""Aufnahmen nach dem Speichern automatisch auf die eigene Website laden (Adresse und Token wie bei der Remote-Funktion)."""
import logging
import os
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from services import recording_upload as upload
from services import wordpress_upload
from services.server_sync import SyncError
from services.settings import app_settings
from ui.web_remote_ui import KEY_SITE_TOKEN, KEY_SITE_URL

log = logging.getLogger(__name__)

KEY_UPLOAD_ENABLED = "recording_upload_enabled"
KEY_WP_ENABLED = "recording_upload_wordpress"       # Ziel: WordPress-Mediathek statt Ordner „aufnahmen“
KEY_WP_URL = "recording_wp_url"
KEY_WP_USER = "recording_wp_user"
KEY_WP_PASSWORD = "recording_wp_password"
STATUS_OFF = "Aus"


class RecordingUploader(QObject):
    status_changed = pyqtSignal(str)

    def __init__(self, window):
        super().__init__(window)
        self.status = STATUS_OFF if not self.enabled() else "Bereit"
        self._thread = None
        self._stop = threading.Event()
        window.recorder.saved.connect(self._on_saved)
        QTimer.singleShot(8000, self.start)               # beim Programmstart: Liegengebliebenes nachholen

    @staticmethod
    def enabled() -> bool:
        return bool(app_settings().value(KEY_UPLOAD_ENABLED, False, type=bool))

    def configure(self) -> None:
        if self.enabled():
            self._set_status("Bereit")
            self.start()
        else:
            self._set_status(STATUS_OFF)

    def _set_status(self, text: str) -> None:
        if text != self.status:
            self.status = text
            self.status_changed.emit(text)

    def _on_saved(self, path: str) -> None:
        if self.enabled():
            upload.add_pending(path)
            self.start()

    def start(self) -> None:
        if not self.enabled() or (self._thread is not None and self._thread.is_alive()):
            return
        if not upload.pending():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._work, name="recording-upload", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------
    def _work(self) -> None:
        settings = app_settings()
        url = str(settings.value(KEY_SITE_URL, "", type=str)).strip()
        token = str(settings.value(KEY_SITE_TOKEN, "", type=str)).strip()
        wordpress = True                                      # Aufnahmen gehen immer in die WordPress-Mediathek
        target = "in der WordPress-Mediathek"
        for path in upload.pending():
            if self._stop.is_set():
                return
            name = os.path.basename(path)
            if not os.path.isfile(path):
                upload.remove_pending(path)                  # Datei gibt es nicht mehr
                continue

            def progress(done, total, name=name):
                self._set_status(f"Lade „{name}“ hoch … {int(100 * done / max(1, total))} %")

            try:
                if wordpress:
                    wordpress_upload.upload_file(
                        str(settings.value(KEY_WP_URL, "", type=str)), str(settings.value(KEY_WP_USER, "", type=str)),
                        str(settings.value(KEY_WP_PASSWORD, "", type=str)), path,
                        on_progress=progress, should_stop=self._stop.is_set)
                else:
                    upload.upload_file(url, token, path, on_progress=progress, should_stop=self._stop.is_set)
            except SyncError as exc:
                self._set_status(f"Upload von „{name}“ unterbrochen: {exc}. Nächster Versuch beim nächsten Start "
                                 "oder nach der nächsten Aufnahme.")
                return
            except Exception:
                log.exception("Aufnahme-Upload fehlgeschlagen")
                self._set_status(f"Upload von „{name}“ fehlgeschlagen (Details in der Protokolldatei).")
                return
            upload.remove_pending(path)
            self._set_status(f"„{name}“ ist {target}.")
