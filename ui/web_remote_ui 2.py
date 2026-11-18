"""Anbindung der Website-Steuerung ans Programm.

Das Programm hält eine Verbindung zu ``server/remote.php`` auf der eigenen Website (``services/remote_relay.py``);
die Bedienung klappt dann per Handy von überall.

Die Verbindung arbeitet in eigenen Threads. Alles, was das Programm berührt, läuft hier
über ``_on_gui``: Der Auftrag wird per Signal in den Oberflächen-Thread geschickt und dort ausgeführt (Qt-Objekte dürfen
nur dort angefasst werden). Die Aktionen rufen dieselben Funktionen auf wie die Knöpfe im Programm.
"""
import hashlib
import logging
import os
import threading
import time
import uuid

from PyQt6.QtCore import QBuffer, QIODevice, QObject, QSize, Qt, QTime, pyqtSignal
from PyQt6.QtGui import QImageReader

from paths import user_data_dir
from services import atem, xair
from services.recorder import IDLE
from services.remote_common import RemoteError
from services.remote_relay import KEY_DEVICE_NAME, RelayClient, device_name, forget_old_name  # noqa: F401  (auch für den Einstellungsdialog)
from services.settings import app_settings
from services.web_remote_page import REQUIRED_VALUES
from ui import theme
from ui.pausentimer_panel import PausentimerPanel
from ui.side_panel import TAB_IMAGES
from version import __version__

log = logging.getLogger(__name__)

LEGACY_KEYS = ("web_remote_enabled", "web_remote_pin", "web_remote_port")   # früherer lokaler Webserver (entfernt)
KEY_SITE_ENABLED = "web_site_enabled"
KEY_SITE_URL = "web_site_url"
KEY_SITE_TOKEN = "web_site_token"
STATUS_OFF = "Aus"
GUI_TIMEOUT = 8.0              # so lange wartet eine Anfrage aus dem Browser auf das Programm
MAX_RESULTS = 60
THUMB_SIZE = QSize(320, 200)
UPLOAD_KEEP_SECONDS = 7 * 24 * 3600


class _Job:
    def __init__(self, function):
        self.function = function
        self.done = threading.Event()
        self.result = None
        self.error = None


def design_values() -> dict:
    """Farben, Maße und Schriften aus ``ui/theme.py`` für die Webseite."""
    values = {name: getattr(theme, name) for name in REQUIRED_VALUES if hasattr(theme, name)}
    values["BODY"] = ", ".join(f'"{name}"' if " " in name else name for name in theme.BODY_FAMILIES)
    return values


def _clean_filename(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/")) or "bild"
    keep = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in base)
    return keep[-80:] or "bild"


class RemoteController(QObject):
    """Startet/stoppt die Website-Steuerung und ist ihr „Backend“ (Zustand, Aktionen, Vorschaubilder, Upload)."""

    site_status_changed = pyqtSignal(str)      # Zustand der Verbindung zur eigenen Website
    _invoke = pyqtSignal(object)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.site_status = STATUS_OFF
        self._relay = None
        self._site_signature = None
        self._found = {}              # rowid -> SongSummary der letzten Suche
        self._image_paths = []        # Stand der Bilder-Ablage (für Vorschaubilder, vom Oberflächen-Thread gesetzt)
        self._thumbs = {}
        self._progress = 0.0
        self._playing = False
        self._rec_seconds = 0.0
        self._invoke.connect(self._run_job, Qt.ConnectionType.QueuedConnection)
        window.playback.progress.connect(self._on_progress)
        window.playback.playing_changed.connect(self._on_playing)
        window.recorder.tick.connect(lambda seconds, _level: setattr(self, "_rec_seconds", seconds))

    # ------------------------------------------------------------------
    # Start / Stopp
    # ------------------------------------------------------------------
    @staticmethod
    def site_enabled() -> bool:
        return bool(app_settings().value(KEY_SITE_ENABLED, False, type=bool))

    @staticmethod
    def site_url() -> str:
        return str(app_settings().value(KEY_SITE_URL, "", type=str)).strip()

    @staticmethod
    def site_token() -> str:
        return str(app_settings().value(KEY_SITE_TOKEN, "", type=str)).strip()

    @staticmethod
    def forget_legacy_settings() -> None:
        """Entfernt die Einstellungen des früheren lokalen Webservers (darunter eine im Klartext gespeicherte PIN)."""
        settings = app_settings()
        if any(settings.contains(key) for key in LEGACY_KEYS):
            for key in LEGACY_KEYS:
                settings.remove(key)
            settings.sync()

    def configure(self) -> None:
        """Verbindet mit der eigenen Website, trennt oder startet neu – nur wenn sich Adresse oder Token geändert haben."""
        self.forget_legacy_settings()
        if not self.site_enabled():
            self._stop_site()
            self._set_site_status(STATUS_OFF)
            return
        signature = (self.site_url(), self.site_token(), device_name())
        if self._relay is not None and self._relay.running and signature == self._site_signature:
            return
        self._stop_site()
        client = RelayClient(signature[0], signature[1], self, on_status=self._set_site_status, device=signature[2])
        error = client.start()
        if error:
            self._set_site_status(f"Nicht gestartet – {error}")
            return
        self._relay = client
        self._site_signature = signature
        threading.Thread(target=forget_old_name, args=signature, name="device-rename", daemon=True).start()

    def _stop_site(self) -> None:
        client, self._relay = self._relay, None
        self._site_signature = None
        if client is not None:
            client.stop()

    def _set_site_status(self, text: str) -> None:
        self.site_status = text                       # darf aus dem Verbindungs-Thread kommen (Signal wird eingereiht)
        self.site_status_changed.emit(text)

    def shutdown(self) -> None:
        self._stop_site()

    # ------------------------------------------------------------------
    # Brücke in den Oberflächen-Thread
    # ------------------------------------------------------------------
    def _run_job(self, job: _Job) -> None:
        try:
            job.result = job.function()
        except Exception as exc:           # an den wartenden Verbindungs-Thread weitergeben
            job.error = exc
        finally:
            job.done.set()

    def _on_gui(self, function):
        job = _Job(function)
        self._invoke.emit(job)
        if not job.done.wait(GUI_TIMEOUT):
            raise RemoteError("Das Programm antwortet gerade nicht.", 504)
        if job.error is not None:
            if isinstance(job.error, RemoteError):
                raise job.error
            log.error("Website-Steuerung: Aktion fehlgeschlagen", exc_info=job.error)
            raise RemoteError("Die Aktion ist fehlgeschlagen.", 500)
        return job.result

    def _on_progress(self, percent: float) -> None:
        self._progress = percent

    def _on_playing(self, playing: bool) -> None:
        self._playing = playing

    # ------------------------------------------------------------------
    # Backend für die Website-Steuerung (Aufruf aus den Verbindungs-Threads)
    # ------------------------------------------------------------------
    def state(self) -> dict:
        return self._on_gui(self._build_state)

    def action(self, name: str, args: dict) -> dict:
        handler = getattr(self, f"_act_{name}", None)
        if handler is None or name.startswith("_"):
            raise RemoteError("Unbekannte Aktion.", 404)
        return self._on_gui(lambda: handler(args)) or {"ok": True}

    def thumbnail(self, index: int):
        paths = self._image_paths
        if not 0 <= index < len(paths):
            return None
        path = paths[index]
        try:
            stamp = os.stat(path).st_mtime_ns
        except OSError:
            return None
        cached = self._thumbs.get(path)
        if cached and cached[0] == stamp:
            return cached[1]
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            size.scale(THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(size)
        image = reader.read()
        if image.isNull():
            return None
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "JPEG", 82)
        data = bytes(buffer.data())
        if len(self._thumbs) > 300:
            self._thumbs.clear()
        self._thumbs[path] = (stamp, data)
        return data

    def upload(self, filename: str, data: bytes) -> dict:
        folder = user_data_dir() / "web_uploads"
        folder.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for old in folder.iterdir():                       # alte Uploads aufräumen
            try:
                if now - old.stat().st_mtime > UPLOAD_KEEP_SECONDS:
                    old.unlink()
            except OSError:
                pass
        target = folder / f"{uuid.uuid4().hex[:8]}_{_clean_filename(filename)}"
        target.write_bytes(data)

        def add():
            added, failed = self.window.images_panel.add_paths([str(target)])
            if added:
                self.window.side_panel.show_tab(TAB_IMAGES)
            return added, len(failed)

        added, failed = self._on_gui(add)
        if not added:
            try:
                target.unlink()
            except OSError:
                pass
        return {"added": added, "failed": failed}

    # ------------------------------------------------------------------
    # Zustand (läuft im Oberflächen-Thread)
    # ------------------------------------------------------------------
    def _build_state(self) -> dict:
        w = self.window
        settings = app_settings()
        paths = w.images_panel.paths()
        self._image_paths = paths

        gallery = w.gallery_window if (w.gallery_window is not None and w.gallery_window.isVisible()) else None
        presentation = w.presentation_window is not None and w.presentation_window.isVisible()
        camera_fullscreen = w.camera_panel.fullscreen_indices()
        if gallery is not None:
            beamer = "gallery"
        elif presentation:
            beamer = "song"
        elif camera_fullscreen:
            beamer = "camera"
        elif w.pausentimer.running:
            beamer = "pause"
        else:
            beamer = "none"

        song = None
        if w.current_song_summary is not None:
            summary = w.current_song_summary
            titel = summary.titel if summary.titel and summary.titel != "None" else ""
            song = {"nummer": summary.nummer, "titel": titel,
                    "audio": [{"available": w._audio_blob(i) is not None, "name": w.AUDIO_NAMES[i]} for i in (0, 1)]}

        active = w.audio_stack.currentIndex() == w.AUDIO_PLAYER
        track = w.player_panel.track_name_label.text() if active else ""
        slot = w.AUDIO_NAMES.index(track) if track in w.AUDIO_NAMES else -1

        panel = w.pausentimer_panel
        cameras = []
        for index, camera_slot in enumerate(w.camera_panel.slots):
            name = settings.value(f"camera_{index + 1}_name", "", type=str)
            shown = f"Kamera {index + 1}" + (f" – {name}" if name and name != "Keine Kamera" else "")
            cameras.append({"name": shown, "live": camera_slot.state in ("live", "fullscreen"),
                            "fullscreen": index in camera_fullscreen})

        return {
            "version": __version__,
            "beamer": beamer,
            "song": song,
            "audio": {"active": active, "playing": self._playing, "progress": self._progress / 100.0,
                      "track": track, "slot": slot},
            "recording": {"state": w.recorder.state, "seconds": int(self._rec_seconds)},
            "pause": {"running": w.pausentimer.running, "end": panel.end_time().toString("HH:mm"),
                      "lines": panel.lines(), "seconds_left": w.pausentimer.seconds_left(),
                      "max_lines": PausentimerPanel.MAX_LINES, "max_chars": PausentimerPanel.MAX_CHARS},
            "images": {"items": [{"name": os.path.basename(p), "key": hashlib.sha1(p.encode("utf-8")).hexdigest()[:10]}
                                 for p in paths]},
            "gallery": ({"index": gallery.current_index, "count": gallery.image_count} if gallery is not None else None),
            "cameras": cameras,
            "atem": {"enabled": bool(settings.value("atem_enabled", False, type=bool)),
                     "channels": {kind: settings.value(key, default, type=int)
                                  for kind, (key, default) in atem.CHANNELS.items()}},
            "mixer": xair.state(),
            "sync": {"enabled": w.sync.enabled(), "status": w.sync.status},
        }

    # ------------------------------------------------------------------
    # Aktionen (laufen im Oberflächen-Thread, rufen dieselben Funktionen wie die Knöpfe)
    # ------------------------------------------------------------------
    @staticmethod
    def _number(args: dict, key: str, low: float, high: float, integer: bool = True):
        value = args.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            raise RemoteError("Ungültiger Wert.", 400)
        return int(value) if integer else float(value)

    def _act_search(self, args: dict) -> dict:
        text = str(args.get("text", ""))[:100]
        songs = self.window.db.search_songs(text)
        self._found = {song.rowid: song for song in songs[:MAX_RESULTS]}
        return {"songs": [{"rowid": s.rowid, "nummer": s.nummer,
                           "titel": s.titel if s.titel and s.titel != "None" else ""} for s in songs[:MAX_RESULTS]],
                "more": len(songs) > MAX_RESULTS}

    def _act_select(self, args: dict) -> dict:
        song = self._found.get(self._number(args, "rowid", 0, 2 ** 62))
        if song is None:
            raise RemoteError("Bitte noch einmal suchen.", 404)
        self.window._hide_search_list()
        self.window._load_song(song)
        return {"ok": True}

    def _act_show_song(self, args: dict) -> dict:
        if not self.window.current_song_full:
            raise RemoteError("Es ist noch kein Lied gewählt.", 409)
        self.window.open_presentation()
        return {"ok": True}

    def _act_beamer_close(self, args: dict) -> dict:
        self.window.close_beamer_windows()
        return {"ok": True}

    def _act_escape(self, args: dict) -> dict:
        self.window.handle_escape()
        return {"ok": True}

    def _act_audio_play(self, args: dict) -> dict:
        slot = self._number(args, "slot", 0, 1)
        if self.window._audio_blob(slot) is None:
            raise RemoteError("Dazu gibt es kein Audio.", 409)
        self.window._play_audio_slot(slot)
        return {"ok": True}

    def _act_audio_toggle(self, args: dict) -> dict:
        self.window.playback.toggle()
        return {"ok": True}

    def _act_audio_stop(self, args: dict) -> dict:
        self.window._stop_playback()
        return {"ok": True}

    def _act_audio_seek(self, args: dict) -> dict:
        self.window.playback.seek_percent(self._number(args, "percent", 0, 100, integer=False))
        return {"ok": True}

    def _act_record_toggle(self, args: dict) -> dict:
        self.window.recorder.toggle()
        return {"ok": True}

    def _act_record_save(self, args: dict) -> dict:
        if self.window.recorder.state == IDLE:
            raise RemoteError("Es läuft keine Aufnahme.", 409)
        self.window.recorder.stop_and_save(str(args.get("preacher", ""))[:80].strip())
        return {"ok": True}

    def _act_images_open(self, args: dict) -> dict:
        count = self.window.images_panel.count()
        if not count:
            raise RemoteError("Es sind keine Bilder abgelegt.", 409)
        self.window.open_gallery(self._number(args, "index", 0, count - 1))
        return {"ok": True}

    def _act_gallery_step(self, args: dict) -> dict:
        gallery = self.window.gallery_window
        if gallery is None or not gallery.isVisible():
            raise RemoteError("Die Galerie ist nicht geöffnet.", 409)
        gallery.step(1 if self._number(args, "delta", -1, 1) > 0 else -1)
        return {"ok": True}

    def _act_gallery_close(self, args: dict) -> dict:
        self.window.close_gallery()
        return {"ok": True}

    def _act_images_remove(self, args: dict) -> dict:
        panel = self.window.images_panel
        index = self._number(args, "index", 0, max(0, panel.count() - 1))
        if not panel.count():
            raise RemoteError("Es sind keine Bilder abgelegt.", 409)
        panel.select_row(index)
        panel.remove_selected()
        return {"ok": True}

    def _act_images_clear(self, args: dict) -> dict:
        self.window.images_panel.clear()
        return {"ok": True}

    def _act_camera_fullscreen(self, args: dict) -> dict:
        panel = self.window.camera_panel
        index = self._number(args, "index", 0, len(panel.slots) - 1)
        if panel.slots[index].state not in ("live", "fullscreen"):
            raise RemoteError("Diese Kamera hat kein Bild.", 409)
        panel.toggle_fullscreen(index)
        return {"ok": True}

    def _act_camera_close(self, args: dict) -> dict:
        self.window.camera_panel.close_all_fullscreen()
        return {"ok": True}

    def _act_atem(self, args: dict) -> dict:
        kind = args.get("kind")
        if kind not in atem.CHANNELS:
            raise RemoteError("Unbekannter Kanal.", 400)
        atem.switch(kind)
        return {"ok": True}

    def _mixer(self):
        mixer = xair.mixer()
        if mixer is None:
            raise RemoteError("Das Mischpult ist in den Einstellungen nicht eingeschaltet.", 409)
        return mixer

    def _act_mixer_level(self, args: dict) -> dict:
        try:
            self._mixer().set_level(int(args.get("channel", 0)), float(args.get("level", 0)))
        except (TypeError, ValueError):
            raise RemoteError("Ungültiger Kanal oder Wert.", 400)
        return {"ok": True}

    def _act_mixer_mute(self, args: dict) -> dict:
        try:
            self._mixer().set_mute(int(args.get("channel", 0)), bool(args.get("mute", True)))
        except (TypeError, ValueError):
            raise RemoteError("Ungültiger Kanal.", 400)
        return {"ok": True}

    def _act_mixer_mute_all(self, args: dict) -> dict:
        self._mixer().mute_all()
        return {"ok": True}

    def _act_gong(self, args: dict) -> dict:
        if not self.window.gong.play():
            raise RemoteError("Die Gong-Datei fehlt.", 409)
        return {"ok": True}

    def _act_pause_set(self, args: dict) -> dict:
        panel = self.window.pausentimer_panel
        lines = args.get("lines", [])
        if not isinstance(lines, list):
            raise RemoteError("Ungültige Ansagen.", 400)
        lines = [str(line)[:PausentimerPanel.MAX_CHARS] for line in lines[:PausentimerPanel.MAX_LINES]]
        text = "\n".join(lines).rstrip("\n")
        if text != panel.text_edit.toPlainText():
            panel.text_edit.setPlainText(text)
        end = QTime.fromString(str(args.get("end", "")), "HH:mm")
        if end.isValid() and end != panel.end_time():
            panel.time_edit.setTime(end)
        return {"ok": True}

    def _act_pause_toggle(self, args: dict) -> dict:
        self.window._on_pausentimer_start_clicked()
        return {"ok": True}

    def _act_sync_now(self, args: dict) -> dict:
        if not self.window.sync.enabled():
            raise RemoteError("Der Abgleich ist nicht eingerichtet.", 409)
        self.window.sync.run_now(manual=True)
        return {"ok": True}
