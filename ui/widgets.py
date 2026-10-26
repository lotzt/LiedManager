"""Wiederverwendbare UI-Bausteine: Icons, Fortschrittsbalken, Pegelanzeige, Labels."""
from functools import lru_cache

from PyQt6.QtCore import (
    QByteArray, QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRectF, QSize, Qt, pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QFontMetrics, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap,
    QRadialGradient,
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QAbstractItemView, QComboBox, QLabel, QListWidget, QPushButton, QWidget

from ui import theme as t

# Pixmap-Skalierungen, die jedem Icon mitgegeben werden (scharf auf 1x/2x/3x-Displays)
_ICON_SCALES = (1, 2, 3)

# Anzahl der Leuchtstufen des pulsierenden Aufnahme-Punkts (jede Stufe wird nur einmal gerendert)
REC_PULSE_STEPS = 12


def _new_pixmap(px: int) -> QPixmap:
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def _quality_painter(device) -> QPainter:
    painter = QPainter(device)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing
        | QPainter.RenderHint.SmoothPixmapTransform
        | QPainter.RenderHint.TextAntialiasing
    )
    return painter


# ----------------------------------------------------------------------
# Icons
# ----------------------------------------------------------------------
@lru_cache(maxsize=128)
def svg_icon(svg_markup: str, size: int = 20) -> QIcon:
    """Rendert ein Inline-SVG in mehreren Auflösungen zu einem QIcon (gecacht, scharf auf HiDPI)."""
    renderer = QSvgRenderer(QByteArray(svg_markup.encode("utf-8")))
    icon = QIcon()
    for scale in _ICON_SCALES:
        px = size * scale
        pixmap = _new_pixmap(px)
        painter = _quality_painter(pixmap)
        renderer.render(painter, QRectF(0, 0, px, px))
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def themed_icon(svg_template: str, color: str, size: int = 20) -> QIcon:
    return svg_icon(svg_template.format(color=color), size)


@lru_cache(maxsize=64)
def _rec_dot_icon(state: str, size: int, step: int) -> QIcon:
    intensity = step / REC_PULSE_STEPS
    icon = QIcon()
    for scale in _ICON_SCALES:
        px = size * scale
        pixmap = _new_pixmap(px)
        painter = _quality_painter(pixmap)
        painter.setPen(Qt.PenStyle.NoPen)

        c = px / 2.0
        center = QPointF(c, c)
        dot_r = px * 0.25
        highlight = QPointF(c - dot_r * 0.30, c - dot_r * 0.35)

        if state == "rec":
            glow_r = px * 0.5
            alpha = int(170 * intensity)
            glow = QRadialGradient(center, glow_r)
            glow.setColorAt(0.00, QColor(240, 101, 74, alpha))
            glow.setColorAt(0.40, QColor(240, 101, 74, int(alpha * 0.45)))
            glow.setColorAt(0.75, QColor(240, 101, 74, int(alpha * 0.12)))
            glow.setColorAt(1.00, QColor(240, 101, 74, 0))
            painter.setBrush(glow)
            painter.drawEllipse(center, glow_r, glow_r)

            dot = QRadialGradient(highlight, dot_r * 1.5)
            dot.setColorAt(0.0, QColor("#FF9078"))
            dot.setColorAt(1.0, QColor("#E5503A"))
            painter.setBrush(dot)
            painter.drawEllipse(center, dot_r, dot_r)

        elif state == "paused":
            glow_r = px * 0.42
            glow = QRadialGradient(center, glow_r)
            glow.setColorAt(0.0, QColor(192, 138, 83, 70))
            glow.setColorAt(1.0, QColor(192, 138, 83, 0))
            painter.setBrush(glow)
            painter.drawEllipse(center, glow_r, glow_r)

            dot = QRadialGradient(highlight, dot_r * 1.5)
            dot.setColorAt(0.0, QColor(t.ACCENT_GLOW))
            dot.setColorAt(1.0, QColor(t.ACCENT))
            painter.setBrush(dot)
            painter.drawEllipse(center, dot_r, dot_r)

        else:  # idle
            dot = QRadialGradient(highlight, dot_r * 1.5)
            dot.setColorAt(0.0, QColor(t.ACCENT_LIGHT))
            dot.setColorAt(1.0, QColor(t.ACCENT_DEEP))
            painter.setBrush(dot)
            painter.drawEllipse(center, dot_r, dot_r)

        painter.end()
        icon.addPixmap(pixmap)
    return icon


def make_rec_dot_icon(state: str = "idle", size: int = 28, intensity: float = 1.0) -> QIcon:
    """Aufnahme-Punkt mit weichem Leuchten (gecacht; ``intensity`` 0..1 wird in Stufen gerastert)."""
    step = round(max(0.0, min(1.0, intensity)) * REC_PULSE_STEPS)
    if state != "rec":
        step = REC_PULSE_STEPS  # Leuchtstärke spielt nur bei der laufenden Aufnahme eine Rolle
    return _rec_dot_icon(state, size, step)


# --- SVG-Icons (Farbe wird per .format(color=...) gesetzt) ---
ICON_GEAR = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"></circle>
  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
</svg>"""

ICON_BELL = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z"></path>
  <path d="M10 20.5a2 2 0 0 0 4 0"></path>
</svg>"""

ICON_SEARCH = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="1.8" stroke-linecap="round">
  <circle cx="11" cy="11" r="7"></circle>
  <path d="M20 20l-3.5-3.5"></path>
</svg>"""

ICON_PLAY = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
  fill="{color}" stroke="{color}" stroke-width="1.5" stroke-linejoin="round">
  <path d="M7 4.5v15l13-7.5z"></path>
</svg>"""

ICON_PAUSE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{color}">
  <rect x="6" y="5" width="4.5" height="14" rx="1"></rect>
  <rect x="13.5" y="5" width="4.5" height="14" rx="1"></rect>
</svg>"""

ICON_STOP = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{color}">
  <rect x="4" y="4" width="16" height="16" rx="2.5"></rect>
</svg>"""

ICON_CHECK = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M5 12.5l4.5 4.5L19 7.5"></path>
</svg>"""

ICON_CHEVRON_UP = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M6 15l6-6 6 6"></path>
</svg>"""

ICON_CHEVRON_DOWN = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M6 9l6 6 6-6"></path>
</svg>"""

ICON_CAMERA = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 8.5a2 2 0 0 1 2-2h2.4l1.4-2h6.4l1.4 2H19a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
  <circle cx="12" cy="12.8" r="3.4"></circle>
</svg>"""

ICON_IMAGES = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="4.5" width="18" height="15" rx="2.5"></rect>
  <circle cx="9" cy="10" r="1.7"></circle>
  <path d="M21 16.5l-5-5-8.5 8"></path>
</svg>"""


def icon_button(svg_template: str, color: str, icon_size: int, tooltip: str = "",
                style: str = None, size: int = t.BTN) -> QPushButton:
    """Runder Icon-Button im Standard-Look. Nimmt beim Klicken keinen Fokus (Suchfeld behält ihn)."""
    btn = QPushButton()
    btn.setIcon(themed_icon(svg_template, color, icon_size))
    btn.setIconSize(QSize(icon_size, icon_size))
    btn.setFixedSize(size, size)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    btn.setStyleSheet(style or t.round_button_style(radius=size // 2))
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


# ----------------------------------------------------------------------
# Labels
# ----------------------------------------------------------------------
class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ElidingLabel(ClickableLabel):
    """Einzeiliges, anklickbares Label, das zu lange Texte mit „…“ kürzt (voller Text als Tooltip)."""

    _full_text = ""  # Klassen-Default: changeEvent kann schon während der Konstruktion feuern
    _hint = ""

    def __init__(self, text: str = "", parent=None):
        super().__init__("", parent)
        self.setWordWrap(False)
        self.setText(text)

    def setText(self, text: str):
        self._full_text = text or ""
        self._refresh_tooltip()
        self._update_elided()

    def setHint(self, hint: str):
        """Zusatzzeile im Tooltip (z. B. was ein Klick bewirkt)."""
        self._hint = hint
        self._refresh_tooltip()

    def _refresh_tooltip(self):
        parts = [p for p in (self._full_text, self._hint) if p]
        self.setToolTip("\n".join(parts))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._update_elided()

    def _update_elided(self):
        width = self.width()
        if width <= 1:
            super().setText(self._full_text)
            return
        elided = QFontMetrics(self.font()).elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, width
        )
        if elided != self.text():
            super().setText(elided)


# ----------------------------------------------------------------------
# Fortschritt & Pegel
# ----------------------------------------------------------------------
class ProgressTrack(QWidget):
    """Fortschrittsbalken mit Knopf. Per Klick oder Ziehen kann vor- und zurückgespult werden.

    Sendet ``seek_requested`` (0..100 in Prozent), solange geklickt/gezogen wird.
    Der Knopf wird um seinen Radius eingerückt, damit er am Anfang und Ende nie abgeschnitten wird.
    """
    seek_requested = pyqtSignal(float)

    KNOB_R = 6.0
    TRACK_H = 4.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 0.0  # 0..100
        self._dragging = False
        self._hover = False
        self.setFixedHeight(20)
        self.setMinimumWidth(80)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # --- Geometrie ---
    def _inset(self) -> float:
        return self.KNOB_R + 2.0  # Platz für Knopf + Glow

    def _span(self) -> float:
        return max(1.0, self.width() - 2 * self._inset())

    def _value_at(self, x: float) -> float:
        return max(0.0, min(100.0, (x - self._inset()) / self._span() * 100.0))

    # --- API ---
    def set_progress(self, value: float):
        if self._dragging:  # während des Ziehens bestimmt die Maus die Position
            return
        value = max(0.0, min(100.0, value))
        if abs(value - self._progress) < 0.05:  # unsichtbare Änderungen nicht neu zeichnen
            return
        self._progress = value
        self.update()

    # --- Maus ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._seek_to(event.position().x())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._seek_to(event.position().x())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._seek_to(event.position().x())
            self._dragging = False
            self.update()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def _seek_to(self, x: float):
        self._progress = self._value_at(x)
        self.update()
        self.seek_requested.emit(self._progress)

    # --- Zeichnen ---
    def paintEvent(self, event):
        painter = _quality_painter(self)
        painter.setPen(Qt.PenStyle.NoPen)

        inset = self._inset()
        span = self._span()
        cy = self.height() / 2.0
        th = self.TRACK_H
        active = self._hover or self._dragging

        # Schiene
        painter.setBrush(QColor(t.TRACK_BG))
        painter.drawRoundedRect(QRectF(inset, cy - th / 2, span, th), th / 2, th / 2)

        # Füllung
        knob_x = inset + span * (self._progress / 100.0)
        fill_w = knob_x - inset
        if fill_w > 0:
            gradient = QLinearGradient(inset, 0, inset + span, 0)
            gradient.setColorAt(0.0, QColor(t.ACCENT_DEEP))
            gradient.setColorAt(0.6, QColor(t.ACCENT))
            gradient.setColorAt(1.0, QColor(t.ACCENT_LIGHT))
            painter.setBrush(gradient)
            painter.drawRoundedRect(QRectF(inset, cy - th / 2, fill_w, th), th / 2, th / 2)

        # Knopf (wächst beim Hovern/Ziehen leicht, mit weichem Schein)
        r = self.KNOB_R + (1.0 if active else 0.0)
        glow_r = r + 3.0
        glow = QRadialGradient(QPointF(knob_x, cy), glow_r)
        glow.setColorAt(0.0, QColor(217, 164, 106, 90 if active else 50))
        glow.setColorAt(1.0, QColor(217, 164, 106, 0))
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(knob_x, cy), glow_r, glow_r)

        knob = QRadialGradient(QPointF(knob_x - r * 0.3, cy - r * 0.35), r * 1.6)
        knob.setColorAt(0.0, QColor(t.ACCENT_GLOW))
        knob.setColorAt(1.0, QColor(t.ACCENT_LIGHT))
        painter.setBrush(knob)
        painter.drawEllipse(QPointF(knob_x, cy), r, r)
        painter.end()


class LevelMeter(QWidget):
    """Aussteuerungsanzeige: Pegel wächst von links als Kapsel mit nach außen gerundetem Ende."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0.0  # 0..1
        self.setFixedHeight(6)
        self.setMinimumWidth(80)
        self._gradient = None
        self._gradient_width = -1

    def set_level(self, value: float):
        value = max(0.0, min(1.0, value))
        if abs(value - self._level) < 0.004:  # unter einem halben Pixel: nichts zu zeichnen
            return
        self._level = value
        self.update()

    def _fill_gradient(self, width: float) -> QLinearGradient:
        if self._gradient is None or self._gradient_width != width:
            gradient = QLinearGradient(0, 0, width, 0)  # Farbe hängt an der Position, nicht an der Länge
            gradient.setColorAt(0.00, QColor(t.ACCENT_GLOW))
            gradient.setColorAt(0.30, QColor(t.ACCENT_LIGHT))
            gradient.setColorAt(0.55, QColor(t.ACCENT))
            gradient.setColorAt(0.78, QColor("#B5683C"))
            gradient.setColorAt(0.92, QColor("#D05A40"))
            gradient.setColorAt(1.00, QColor(t.REC_RED))
            self._gradient, self._gradient_width = gradient, width
        return self._gradient

    def paintEvent(self, event):
        painter = _quality_painter(self)
        painter.setPen(Qt.PenStyle.NoPen)

        width = float(self.width())
        height = float(self.height())
        radius = height / 2.0

        # Schiene (Kapsel)
        painter.setBrush(QColor(t.TRACK_BG))
        painter.drawRoundedRect(QRectF(0, 0, width, height), radius, radius)

        # Pegel: eigene Kapsel nur so lang wie der Pegel -> Ende rundet nach außen
        fill_w = width * self._level
        if fill_w > 0.5:
            fill_w = max(fill_w, height)  # mindestens ein voller Kreis
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, fill_w, height), radius, radius)
            painter.fillPath(path, self._fill_gradient(width))
        painter.end()


def round_combo_popup(combo: QComboBox) -> None:
    """Rundet die aufklappende Liste einer ComboBox (durchsichtiges Popup-Fenster + runde Liste)."""
    view = combo.view()
    popup = view.window()
    if popup is None or popup is combo.window():
        return
    popup.setObjectName("ComboPopup")
    popup.setWindowFlags(popup.windowFlags()
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
    popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    popup.setStyleSheet("QFrame#ComboPopup { background: transparent; border: 0; }")
    layout = popup.layout()
    if layout is not None:
        layout.setContentsMargins(0, 0, 0, 0)


# ----------------------------------------------------------------------
# Listen mit sanftem Mausrad-Scrollen
# ----------------------------------------------------------------------
class SmoothListWidget(QListWidget):
    """Liste mit ruhigem Mausrad-Scrollen (gemeinsam für Bilder-Vorschau und Treffer der Textsuche).

    * Ein Rastschritt am Mausrad bewegt die Liste nur um ``WHEEL_STEP`` Pixel und gleitet ruhig nach (statt zu springen);
      schnelles Drehen addiert sich.
    * Trackpads (Pixel-Delta) scrollen direkt und fein, gedämpft um ``TRACKPAD_FACTOR``.
    """
    WHEEL_STEP = 48          # Pixel pro Rastschritt am Mausrad
    GLIDE_MS = 220           # Dauer des Nachgleitens
    TRACKPAD_FACTOR = 0.5    # Trackpad-Bewegung wird auf die Hälfte gedämpft

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wheel_target = None
        self._glide = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._glide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._glide.setDuration(self.GLIDE_MS)
        self.verticalScrollBar().setSingleStep(16)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        pixels = event.pixelDelta().y()
        if pixels != 0 or delta == 0:
            self._glide.stop()
            self._wheel_target = None
            if pixels:                         # Trackpad: direkt, aber gedämpft
                bar = self.verticalScrollBar()
                bar.setValue(bar.value() - round(pixels * self.TRACKPAD_FACTOR))
                event.accept()
                return
            super().wheelEvent(event)
            return
        bar = self.verticalScrollBar()
        running = self._glide.state() == QPropertyAnimation.State.Running and self._wheel_target is not None
        start = self._wheel_target if running else bar.value()
        target = max(bar.minimum(), min(bar.maximum(), round(start - delta / 120 * self.WHEEL_STEP)))
        self._wheel_target = target
        self._glide.stop()
        self._glide.setStartValue(bar.value())
        self._glide.setEndValue(target)
        self._glide.start()
        event.accept()
