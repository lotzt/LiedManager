"""Aufnahmen nach dem Speichern automatisch auf die eigene Website laden (Adresse und Token wie bei der Remote-Funktion)."""
import datetime
import logging
import os
import re
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
KEY_UPLOAD_DAYS = "recording_upload_days"         # Wochentage (1 = Montag … 7 = Sonntag), z. B. "7"; leer/fehlt = alle
STATUS_OFF = "Aus"
DAY_NAMES = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def upload_days() -> set:
    """Die Wochentage, deren Aufnahmen hochgeladen werden (1 = Montag … 7 = Sonntag). Nichts eingestellt = alle."""
    text = str(app_settings().value(KEY_UPLOAD_DAYS, "", type=str))
    days = {int(d) for d in re.findall(r"[1-7]", text)}
    return days or set(range(1, 8))


def recording_day(path: str):
    """Datum der Aufnahme: aus dem Dateinamen („JJJJ.MM.TT Prediger“), sonst aus dem Änderungsdatum der Datei."""
    match = re.match(r"(\d{4})[.\-_](\d{2})[.\-_](\d{2})", os.path.basename(path))
    if match:
        try:
            return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    try:
        return datetime.date.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return None


def day_allowed(path: str) -> bool:
    day = recording_day(path)
    return day is None or day.isoweekday() in upload_days()


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
        if not self.enabled():
            return
        if not day_allowed(path):
            day = recording_day(path)
            self._set_status(f"„{os.path.basename(path)}“ wird nicht hochgeladen ({DAY_NAMES[day.isoweekday() - 1]} "
                             "ist nicht ausgewählt).")
            return
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
            if not day_allowed(path):                        # Wochentag inzwischen abgewählt: nicht mehr hochladen
                upload.remove_pending(path)
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
