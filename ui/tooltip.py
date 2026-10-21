"""Abgerundete Tooltips (Hover-Erklärungen) – einheitlich auf macOS und Windows.

Die Standard-Tooltips von Qt lassen sich nicht zuverlässig abrunden. Deshalb fängt ein Filter alle
Tooltip-Ereignisse ab und zeigt stattdessen dieses eigene, durchsichtige Fenster mit runden Ecken.
Jedes Widget mit ``setToolTip(...)`` bekommt so automatisch den neuen Look.
"""
from PyQt6.QtCore import QEvent, QObject, QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

from ui import theme as t

RADIUS = 10
MAX_WIDTH = 300
SHOW_MS = 9000

_HIDE_EVENTS = (
    QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel,
    QEvent.Type.KeyPress, QEvent.Type.WindowDeactivate, QEvent.Type.FocusOut,
)


class RoundedToolTip(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._label = QLabel(self)
        self._label.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: {t.FS_SMALL + 1}px; background: transparent; border: 0;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(13, 9, 13, 9)
        layout.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(SHOW_MS)
        self._timer.timeout.connect(self.hide)

    def show_text(self, text: str, global_pos: QPoint) -> None:
        label = self._label
        label.setWordWrap(False)
        label.setText(text)
        width = label.sizeHint().width()
        if width > MAX_WIDTH:
            label.setWordWrap(True)
            width = MAX_WIDTH
            label.setFixedSize(width, label.heightForWidth(width))
        else:
            label.setFixedSize(width, label.sizeHint().height())
        self.layout().activate()
        self.resize(self.sizeHint())

        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(global_pos.x() + 14, area.right() - self.width())
        y = global_pos.y() + 20
        if y + self.height() > area.bottom():
            y = global_pos.y() - self.height() - 8
        self.move(max(area.left(), x), max(area.top(), y))

        self.show()
        self.raise_()
        self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, RADIUS, RADIUS)
        painter.fillPath(path, QColor(t.SURFACE))
        painter.setPen(QPen(QColor(t.ACCENT_BORDER), 1))
        painter.drawPath(path)
        painter.end()


class ToolTipFilter(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tip = RoundedToolTip()

    def eventFilter(self, obj, event):
        try:
            et = event.type()
            if et == QEvent.Type.ToolTip and isinstance(obj, QWidget):
                text = obj.toolTip()
                if text:
                    self._tip.show_text(text, event.globalPos())
                    return True  # Standard-Tooltip unterdrücken
                return False     # Eltern-Widget darf seinen Tooltip zeigen
            if et in _HIDE_EVENTS and self._tip.isVisible():
                self._tip.hide()
        except RuntimeError:
            pass  # beim Beenden hat Qt das Tooltip-Fenster schon abgebaut
        return False


_filter = None


def install_tooltips(app: QApplication) -> ToolTipFilter:
    global _filter
    _filter = ToolTipFilter(app)
    app.installEventFilter(_filter)
    return _filter


def show_tip(text: str, global_pos: QPoint) -> None:
    """Zeigt einen Tooltip von Hand (für Bereiche, die selbst keine Qt-Tooltips auslösen, z. B. Videobilder)."""
    if _filter is not None and text:
        try:
            _filter._tip.show_text(text, global_pos)
        except RuntimeError:
            pass  # Programm wird gerade beendet


def hide_tip() -> None:
    if _filter is not None:
        try:
            _filter._tip.hide()
        except RuntimeError:
            pass  # Programm wird gerade beendet
