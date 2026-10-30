"""Pausenfolie auf dem Beamer – ohne PowerPoint.

* ``PauseRenderer``    zeichnet eine Ansicht des Designs (siehe ``services/pausenfolie.py``): Hintergrund, Bild-Ebenen und
                       Texte. Der unveränderliche Teil wird einmal pro Bildschirmgröße als Bild vorbereitet; Ansagen,
                       Bibelvers und Zahl werden darüber gezeichnet (scharf, in jeder Auflösung).
* ``PauseWindow``      Vollbild auf dem Beamer (immer oben), Countdown mit Puls-Effekt wie in der Vorlage.
* ``NativePausentimer`` dieselbe Schnittstelle wie ``services.powerpoint.PausentimerController``: Ablauf nach der Endzeit,
                       Musik, Mischer, Wachhalten des Rechners.
"""
import datetime
import logging
from pathlib import Path

from PyQt6.QtCore import (
    QAbstractAnimation,
    QObject,
    QPointF,
    QRectF,
    Qt,
    QTime,
    QTimer,
    QUrl,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QImage,
    QImageReader,
    QPainter,
    QPixmap,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import QApplication, QWidget

from services import atem, devices, pausenfolie, power
from services.settings import app_settings

log = logging.getLogger(__name__)

W, H = pausenfolie.WIDTH, pausenfolie.HEIGHT
FALLBACK_FAMILIES = ["Arial", "Helvetica Neue", "Helvetica", "sans-serif"]
_loaded_fonts = {}            # Pfad der Schriftdatei -> [Familiennamen]


def _pulse_values(progress: float):
    """(Größe, Deckkraft) für das (abschaltbare) Pulsieren: kurz 5 % größer und wieder zurück – ohne durchsichtig zu werden."""
    p = max(0.0, min(1.0, progress))
    return 1.0 + 0.05 * (p / 0.5 if p <= 0.5 else (1.0 - p) / 0.5), 1.0


class PauseRenderer:
    """Zeichnet die Ansichten eines Designs. Alle Maße in Pixeln einer 1920 × 1080-Fläche."""

    def __init__(self, design: dict):
        self.design = design or {}
        self.folder = Path(self.design.get("_dir", "."))
        self._images = {}
        self._backgrounds = {}             # (Ansicht, Breite, Höhe) -> QPixmap
        self._families = {}                # Name in der Vorlage -> geladene Familie
        for family, styles in (self.design.get("fonts") or {}).items():
            for file in styles.values():
                if not file:
                    continue
                path = str(self.folder / file)
                if path not in _loaded_fonts:
                    font_id = QFontDatabase.addApplicationFont(path)
                    _loaded_fonts[path] = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
                if _loaded_fonts[path]:
                    self._families[family] = _loaded_fonts[path][0]

    # --- Grundbausteine ------------------------------------------------
    def image(self, file: str):
        if file not in self._images:
            reader = QImageReader(str(self.folder / file))
            reader.setAutoTransform(True)
            image = reader.read()
            if image.isNull():
                log.warning("Pausenfolie: Bild %s nicht lesbar (%s)", file, reader.errorString())
            self._images[file] = image
        return self._images[file]

    def font(self, style: dict, scale: float = 1.0) -> QFont:
        family = self._families.get(style.get("font", ""), style.get("font", ""))
        font = QFont()
        font.setFamilies([family] + FALLBACK_FAMILIES if family else FALLBACK_FAMILIES)
        font.setPixelSize(max(1, round(float(style.get("size", 40)) * scale)))
        font.setBold(bool(style.get("bold")))
        font.setItalic(bool(style.get("italic")))
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        return font

    @staticmethod
    def color(style: dict) -> QColor:
        color = QColor(style.get("color", "#000000"))
        color.setAlphaF(max(0.0, min(1.0, float(style.get("alpha", 1.0)))))
        return color

    def scene(self, name: str) -> dict:
        return (self.design.get("scenes") or {}).get(name) or {"background": {"color": "#000000"}, "layers": []}

    # --- Unveränderlicher Teil -----------------------------------------
    def background(self, name: str, width: int, height: int, dpr: float = 1.0) -> QPixmap:
        """Hintergrund, Bilder und feste Texte einer Ansicht in Gerätepixeln (einmal je Größe berechnet)."""
        key = (name, width, height, dpr)
        if key not in self._backgrounds:
            canvas = QImage(max(1, round(width * dpr)), max(1, round(height * dpr)), QImage.Format.Format_RGB32)
            canvas.fill(Qt.GlobalColor.black)
            painter = QPainter(canvas)
            painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
                                   | QPainter.RenderHint.TextAntialiasing)
            painter.scale(canvas.width() / W, canvas.height() / H)
            painter.setClipRect(QRectF(0, 0, W, H))
            self.draw_static(painter, name)
            painter.end()
            pixmap = QPixmap.fromImage(canvas)
            pixmap.setDevicePixelRatio(dpr)
            if len(self._backgrounds) > 8:
                self._backgrounds.clear()
            self._backgrounds[key] = pixmap
        return self._backgrounds[key]

    def draw_static(self, painter: QPainter, name: str) -> None:
        scene = self.scene(name)
        bg = scene.get("background") or {}
        if bg.get("file"):
            l, t, r, b = (bg.get("fill") or [0, 0, 0, 0])[:4]
            self._draw_image(painter, bg["file"], QRectF(l * W, t * H, W - (l + r) * W, H - (t + b) * H))
        else:
            painter.fillRect(QRectF(0, 0, W, H), QColor(bg.get("color", "#000000")))
        for layer in scene.get("layers", []):
            if layer.get("kind") == "image":
                self._draw_image(painter, layer["file"], QRectF(*layer["rect"]), layer.get("rot", 0),
                                 layer.get("flip_h"), layer.get("flip_v"), layer.get("crop"))
            elif layer.get("kind") == "text" and layer.get("role") in ("static", "end"):
                self.draw_text(painter, layer, layer.get("text", ""))

    def _draw_image(self, painter, file, rect: QRectF, rot=0.0, flip_h=False, flip_v=False, crop=None):
        image = self.image(file)
        if image.isNull():
            return
        source = QRectF(0, 0, image.width(), image.height())
        if crop and any(crop):
            l, t, r, b = crop[:4]
            source = QRectF(l * image.width(), t * image.height(),
                            image.width() * (1 - l - r), image.height() * (1 - t - b))
        painter.save()
        painter.translate(rect.center())
        if rot:
            painter.rotate(rot)
        painter.scale(-1 if flip_h else 1, -1 if flip_v else 1)
        painter.drawImage(QRectF(-rect.width() / 2, -rect.height() / 2, rect.width(), rect.height()), image, source)
        painter.restore()

    # --- Texte ------------------------------------------------------------
    @staticmethod
    def wrap(text: str, metrics: QFontMetricsF, width: float) -> list:
        """Zeilenumbruch an Wortgrenzen (Absätze bleiben erhalten; zu lange Wörter stehen allein in der Zeile)."""
        lines = []
        for paragraph in str(text).split("\n"):
            words, current = paragraph.split(" "), ""
            if not paragraph.strip():
                lines.append("")
                continue
            for word in words:
                candidate = f"{current} {word}" if current else word
                if current and metrics.horizontalAdvance(candidate) > width:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            lines.append(current)
        return lines

    def draw_text(self, painter: QPainter, layer: dict, text: str, shrink_to: float = None,
                  scale: float = 1.0, opacity: float = 1.0) -> None:
        """Ein Textfeld wie in PowerPoint: Innenabstand, Ausrichtung, feste Zeilenhöhe. ``shrink_to``: Unterkante, bis zu
        der der Text höchstens reichen darf (sonst wird er kleiner). Zahl/Ende stehen mittig im Kreis (``center_in``)."""
        if not str(text).strip():
            return
        centered = "center_in" in layer
        if centered:
            area = QRectF(*layer["center_in"])
        else:
            l, t, r, b = layer.get("insets") or [0, 0, 0, 0]
            x, y, w, h = layer["rect"]
            area = QRectF(x + l, y + t, max(10, w - l - r), max(10, h - t - b))
        size_factor = 1.0
        reference = layer.get("reference") if layer.get("role") == "verse" else ""
        for _attempt in range(12):
            font = self.font(layer, size_factor)
            metrics = QFontMetricsF(font)
            line_h = (float(layer["line_height"]) * size_factor if layer.get("line_height")
                      else metrics.lineSpacing())
            lines = [str(text).strip()] if centered else self.wrap(text, metrics, area.width())
            total = line_h * len(lines) + (line_h * 2 if reference else 0)
            if shrink_to is None or area.top() + total <= shrink_to or size_factor < 0.5:
                break
            size_factor *= 0.92
        painter.save()
        painter.setFont(font)
        painter.setPen(self.color(layer))
        painter.setOpacity(opacity)
        if centered:
            center = area.center()
            if scale != 1.0:
                painter.translate(center)
                painter.scale(scale, scale)
                painter.translate(-center)
            width = metrics.horizontalAdvance(lines[0])
            baseline = center.y() + metrics.capHeight() / 2
            painter.drawText(QPointF(center.x() - width / 2, baseline), lines[0])
            painter.restore()
            return
        top = area.top()
        if layer.get("anchor") == "center":
            top = area.center().y() - total / 2
        elif layer.get("anchor") == "bottom":
            top = area.bottom() - total
        align = layer.get("align", "left")
        for index, line in enumerate(lines):
            if not line:
                continue
            width = metrics.horizontalAdvance(line)
            x = area.left() if align == "left" else (area.right() - width if align == "right"
                                                     else area.center().x() - width / 2)
            baseline = top + index * line_h + (line_h + metrics.ascent() - metrics.descent()) / 2
            painter.drawText(QPointF(x, baseline), line)
        if reference:
            style = dict(layer)
            style.update(layer.get("reference_style") or {})
            ref_font = self.font(style, size_factor)
            ref_metrics = QFontMetricsF(ref_font)
            painter.setFont(ref_font)
            painter.setPen(self.color(style))
            width = ref_metrics.horizontalAdvance(reference)
            x = area.right() - width if layer.get("reference_align", "right") == "right" else area.left()
            baseline = top + (len(lines) + 1) * line_h + (line_h + ref_metrics.ascent() - ref_metrics.descent()) / 2
            painter.drawText(QPointF(x, baseline), reference)
        painter.restore()

    def draw_dynamic(self, painter: QPainter, name: str, texts: dict, number=None,
                     pulse=(1.0, 1.0)) -> None:
        """Ansagen, Bibelvers bzw. Zahl über den vorbereiteten Hintergrund zeichnen (Painter auf 1920 × 1080 skaliert)."""
        drawn_announcements = False
        for layer in self.scene(name).get("layers", []):
            if layer.get("kind") != "text":
                continue
            role = layer.get("role")
            if role == "announcements":
                self.draw_text(painter, layer, texts.get("announcements", ""), shrink_to=H - 30)
                drawn_announcements = True
            elif role == "verse":
                verse = dict(layer)
                verse["reference"] = texts.get("verse_reference", layer.get("reference", ""))
                self.draw_text(painter, verse, texts.get("verse_text", layer.get("text", "")), shrink_to=H - 30)
            elif role == "number" and number is not None:
                self.draw_text(painter, layer, str(number), scale=pulse[0], opacity=pulse[1])
        if name == "announcements" and not drawn_announcements:     # Vorlage ohne erkanntes Ansagen-Feld: trotzdem zeigen
            self.draw_text(painter, {"kind": "text", "role": "announcements", "rect": [140, 330, 1200, 700],
                                     "font": "", "size": 46, "color": "#323232", "align": "left"},
                           texts.get("announcements", ""), shrink_to=H - 30)

    def render(self, name: str, texts: dict, number=None, width: int = W, height: int = H) -> QImage:
        """Ganze Ansicht als Bild (für die Vorschau in den Einstellungen)."""
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.black)
        painter = QPainter(image)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
                               | QPainter.RenderHint.TextAntialiasing)
        painter.drawPixmap(0, 0, self.background(name, width, height))
        painter.scale(width / W, height / H)
        self.draw_dynamic(painter, name, texts, number)
        painter.end()
        return image


class PauseWindow(QWidget):
    """Vollbild-Fenster auf dem Beamer. Zeigt eine Ansicht im Format 16:9 (bei anderem Format mit schwarzem Rand)."""
    escape_pressed = pyqtSignal()

    def __init__(self, renderer: PauseRenderer, screen_index: int = 0):
        super().__init__(None)
        self.renderer = renderer
        self.screen_index = screen_index
        self.scene_name = "announcements"
        self.texts = {}
        self.number = None
        self._pulse_progress = 1.0
        self.setWindowTitle("LiedManager – Pausenfolie")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self._pulse = QVariantAnimation(self)
        self._pulse.setDuration(900)
        self._pulse.setStartValue(0.0)
        self._pulse.setEndValue(1.0)
        self._pulse.valueChanged.connect(self._on_pulse)

    def show_on_beamer(self) -> None:
        screens = QApplication.screens()
        screen = screens[self.screen_index] if 0 <= self.screen_index < len(screens) else QApplication.primaryScreen()
        from ui.widgets import show_fullscreen_on
        show_fullscreen_on(self, screen)

    def set_state(self, scene_name: str, number=None, texts: dict = None) -> None:
        changed_number = number is not None and number != self.number
        self.scene_name = scene_name
        self.number = number
        if texts is not None:
            self.texts = texts
        if changed_number and self.renderer.design.get("pulse", False):
            self._pulse.stop()
            self._pulse.start()
        self.update()

    def _on_pulse(self, value) -> None:
        self._pulse_progress = float(value)
        self.update()

    def _frame(self) -> QRectF:
        """Die 16:9-Fläche im Fenster (mittig, mit schwarzem Rand bei anderem Seitenverhältnis)."""
        scale = min(self.width() / W, self.height() / H)
        width, height = W * scale, H * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        frame = self._frame()
        dpr = self.devicePixelRatioF()
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        painter.drawPixmap(frame.topLeft(), self.renderer.background(self.scene_name, round(frame.width()),
                                                                      round(frame.height()), dpr))
        painter.translate(frame.topLeft())
        painter.scale(frame.width() / W, frame.height() / H)
        running = self._pulse.state() == QAbstractAnimation.State.Running
        pulse = _pulse_values(self._pulse_progress) if running else (1.0, 1.0)
        try:
            self.renderer.draw_dynamic(painter, self.scene_name, self.texts, self.number, pulse)
        except Exception:                               # ein Zeichenfehler darf die Pausenfolie nicht leer lassen
            log.exception("Pausenfolie: Text konnte nicht gezeichnet werden")
        painter.end()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape,):
            self.escape_pressed.emit()
        else:
            super().keyPressEvent(event)


class NativePausentimer(QObject):
    """Pausentimer ohne PowerPoint (gleiche Schnittstelle wie ``PausentimerController``)."""
    running_changed = pyqtSignal(bool)
    error = pyqtSignal(str)

    TICK_MS = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._end_time = QTime(11, 30)
        self._finish = None
        self._window = None
        self._design = None
        self._texts = {}
        self._music_started = False
        self._player = None
        self._output = None
        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)

    # --- Schnittstelle wie beim PowerPoint-Pausentimer ----------------------
    @property
    def running(self) -> bool:
        return self._running

    def seconds_left(self):
        if not self._running or self._finish is None:
            return None
        return max(0, int((self._finish - datetime.datetime.now()).total_seconds()))

    def warm_up(self) -> None:
        pass

    def shutdown(self) -> None:
        self.stop()

    def set_end_time(self, end_time: QTime) -> None:
        self._end_time = end_time
        if self._running:
            self._finish = self._compute_finish()
            self._music_started = False if self._player is None else self._music_started
            self._tick()

    def update_lines(self, lines) -> None:
        """Ansagen haben sich geändert (Hauptfenster oder Web-Remote): sofort auf dem Beamer zeigen."""
        self._texts["announcements"] = "\n".join(lines)
        if self._window is not None:
            self._window.set_state(self._window.scene_name, self._window.number, self._texts)

    def start(self, lines, end_time: QTime) -> None:
        if self._running:
            return
        season = app_settings().value("presentation_season", "frühling", type=str)
        design = pausenfolie.load(season)
        if design is None:
            self.error.emit(f"Für „{season}“ ist noch keine Pausenfolie eingerichtet.\n\nEinstellungen → Pausentimer → "
                            "„Vorlage übernehmen …“.")
            return
        self._design = design
        self._texts = {"announcements": "\n".join(lines),
                       "verse_text": design.get("verse_text", ""),
                       "verse_reference": design.get("verse_reference", "")}
        self._end_time = end_time
        self._finish = self._compute_finish()
        self._music_started = False
        screen_index = app_settings().value("beamer_screen", 0, type=int)
        self._window = PauseWindow(PauseRenderer(design), screen_index)
        # Esc beendet die Pause bewusst nicht – nur der Knopf (oder die Remote), damit sie nicht versehentlich endet
        self._window.texts = self._texts               # Ansagen gleich beim Start (nicht erst beim nächsten Wechsel)
        self._running = True
        atem.switch("presentation")
        power.keep_awake()
        self.running_changed.emit(True)
        self._tick()
        self._window.show_on_beamer()
        self._timer.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        self._stop_music()
        if self._window is not None:
            self._window.close()
            self._window.deleteLater()
            self._window = None
        power.release()
        self.running_changed.emit(False)
        atem.switch("default")

    # --- Ablauf --------------------------------------------------------
    def _compute_finish(self) -> datetime.datetime:
        now = datetime.datetime.now()
        finish = datetime.datetime.combine(now.date(), datetime.time(self._end_time.hour(), self._end_time.minute()))
        if finish <= now:
            finish += datetime.timedelta(days=1)
        return finish

    def _tick(self) -> None:
        if not self._running or self._window is None:
            return
        left = (self._finish - datetime.datetime.now()).total_seconds()
        scene, number = pausenfolie.phase(left, self._design)
        if (scene != self._window.scene_name or number != self._window.number
                or self._window.texts is not self._texts):
            self._window.set_state(scene, number, self._texts)
        self._music(left)

    def _music(self, seconds_left: float) -> None:
        music = (self._design or {}).get("music") or {}
        file = music.get("file")
        if not file or self._music_started:
            return
        start = float(music.get("start_second", 58))
        if seconds_left > start or seconds_left <= 0:
            return
        path = Path(self._design["_dir"]) / file
        if not path.exists():
            return
        self._music_started = True
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        device = devices.find_output(str(app_settings().value(devices.KEY_OUTPUT, "")))
        if device is not None:
            self._output.setDevice(device)
        self._output.setVolume(max(0.0, min(1.0, float(music.get("volume", 0.8)))))
        self._player.setAudioOutput(self._output)
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        late_ms = int(max(0.0, start - seconds_left) * 1000)
        if late_ms > 500:                               # später gestartet (Endzeit geändert): an passender Stelle einsteigen
            player = self._player
            player.mediaStatusChanged.connect(
                lambda status, ms=late_ms: player.setPosition(ms)
                if status == QMediaPlayer.MediaStatus.LoadedMedia else None)
        self._player.play()

    def _stop_music(self) -> None:
        if self._player is not None:
            self._player.stop()
            self._player.deleteLater()
            self._output.deleteLater()
        self._player = self._output = None


def preview_images(season: str, size=(480, 270), lines=None) -> list:
    """Vorschau der vier Ansichten (für die Einstellungen): [(Name, QImage), …]; leer ohne Design."""
    design = pausenfolie.load(season)
    if design is None:
        return []
    renderer = PauseRenderer(design)
    texts = {"announcements": "\n".join(lines or ["Ansagen erscheinen hier", "– eine Zeile pro Ansage –"]),
             "verse_text": design.get("verse_text", ""), "verse_reference": design.get("verse_reference", "")}
    countdown = int((design.get("timing") or {}).get("countdown_seconds", 60))
    result = []
    for scene in pausenfolie.SCENES:
        number = countdown if scene == "countdown" else None
        result.append((pausenfolie.SCENE_NAMES[scene], renderer.render(scene, texts, number, *size)))
    return result



KEY_MODE = "pause_mode"            # "liedmanager" (ohne PowerPoint) oder "powerpoint"
MODES = (("liedmanager", "LiedManager (ohne PowerPoint)"), ("powerpoint", "PowerPoint (wie bisher)"))


def pause_mode() -> str:
    mode = str(app_settings().value(KEY_MODE, "liedmanager", type=str))
    return mode if mode in dict(MODES) else "liedmanager"


def ensure_design(season: str):
    """Design der Jahreszeit; fehlt es, wird die PowerPoint-Vorlage „pausentimer_<jahreszeit>.pptx“ einmal übernommen.
    Gibt (Design oder None, Fehlermeldung) zurück."""
    design = pausenfolie.load(season)
    from services.powerpoint import template_path
    source = template_path(season)
    if design is not None:
        if int(design.get("version", 1)) < pausenfolie.VERSION and source.exists():
            try:                                        # mit einer älteren Programmversion übernommen: neu einlesen
                return pausenfolie.import_pptx(source, season), ""
            except pausenfolie.ImportProblem:
                log.warning("Pausenfolie %s: neues Einlesen fehlgeschlagen, das bisherige Design bleibt", season)
        return design, ""
    if not source.exists():
        return None, (f"Für „{season}“ gibt es noch keine Pausenfolie.\n\nLege die PowerPoint-Vorlage „{source.name}“ in den "
                      f"Ordner\n{source.parent}\noder übernimm sie unter Einstellungen → Pausentimer.")
    try:
        return pausenfolie.import_pptx(source, season), ""
    except pausenfolie.ImportProblem as exc:
        return None, f"Die Pausenfolie „{source.name}“ ließ sich nicht übernehmen:\n{exc}"


class Pausentimer(QObject):
    """Wählt je nach Einstellung den Pausentimer ohne PowerPoint (Standard) oder mit PowerPoint.
    Nach außen dieselbe Schnittstelle wie beide (running, seconds_left, start, stop, set_end_time …)."""
    running_changed = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        from services.powerpoint import PausentimerController
        self._powerpoint = PausentimerController(self)
        self._native = NativePausentimer(self)
        self._active = None
        for controller in (self._powerpoint, self._native):
            controller.running_changed.connect(self.running_changed)
            controller.error.connect(self.error)

    @property
    def running(self) -> bool:
        return self._powerpoint.running or self._native.running

    def seconds_left(self):
        controller = self._active or self._native
        return controller.seconds_left() if controller.running else None

    def start(self, lines, end_time: QTime) -> None:
        if self.running:
            return
        if pause_mode() == "powerpoint":
            self._active = self._powerpoint
        else:
            season = app_settings().value("presentation_season", "frühling", type=str)
            design, problem = ensure_design(season)
            if design is None:
                self.error.emit(problem)
                return
            self._active = self._native
        self._active.start(lines, end_time)

    def stop(self) -> None:
        for controller in (self._native, self._powerpoint):
            if controller.running:
                controller.stop()

    def set_end_time(self, end_time: QTime) -> None:
        self._native.set_end_time(end_time)
        self._powerpoint.set_end_time(end_time)

    def update_lines(self, lines) -> None:
        self._native.update_lines(lines)

    def warm_up(self) -> None:
        if pause_mode() == "powerpoint":
            self._powerpoint.warm_up()

    def shutdown(self) -> None:
        self._native.shutdown()
        self._powerpoint.shutdown()
