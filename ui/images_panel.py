"""Bilder-Ablage: Bilder per Drag & Drop ins Programm ziehen, Vorschau im Reiter „Bilder“ der Seitenleiste.

* ``ImageDropFilter``  fängt das Ablegen von Bilddateien/Ordnern im ganzen Programm ab (auch über Textfeldern).
* ``ImagesPanel``      zeigt die abgelegten Bilder als Vorschau; Doppelklick/Enter wirft sie auf den Beamer.
* ``load_image``       lädt ein Bild verkleinert und nach EXIF-Ausrichtung gedreht (wird auch von der Galerie genutzt).
"""
import os
import re

from PyQt6.QtCore import (
    QEvent, QObject, QPoint, QRectF, QSize, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QCursor, QImageIOHandler, QImageReader, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMenu, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ui import theme as t
from ui import widgets as w
from ui.tooltip import show_tip

MAX_SIDE = 3840          # größere Bilder werden beim Laden auf 4K-Kantenlänge verkleinert
THUMB_W, THUMB_H = 200, 112
THUMB_DPR = 2            # Vorschau in doppelter Auflösung (scharf auf Retina-Displays)

ICON_CLOSE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="2" stroke-linecap="round">
  <path d="M6 6l12 12M18 6L6 18"></path>
</svg>"""

_suffixes = None


# ----------------------------------------------------------------------
# Dateien erkennen und laden
# ----------------------------------------------------------------------
def image_suffixes() -> set:
    """Dateiendungen, die Qt auf diesem Rechner lesen kann (jpg, png, gif, bmp, webp, tiff …)."""
    global _suffixes
    if _suffixes is None:
        _suffixes = {bytes(fmt).decode("ascii", "ignore").lower() for fmt in QImageReader.supportedImageFormats()}
        if "jpeg" in _suffixes:
            _suffixes.add("jpg")
    return _suffixes


def is_image_file(path: str) -> bool:
    return os.path.splitext(path)[1][1:].lower() in image_suffixes()


def natural_key(name: str):
    """Sortierschlüssel, der „bild2“ vor „bild10“ stellt."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def image_paths_from_mime(mime) -> list:
    """Bilddateien und Ordner aus einem Drag-&-Drop-Vorgang (nur lokale Dateien)."""
    if mime is None or not mime.hasUrls():
        return []
    paths = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        path = url.toLocalFile()
        if os.path.isdir(path) or is_image_file(path):
            paths.append(path)
    return paths


def expand_paths(paths) -> list:
    """Ordner werden durch die darin liegenden Bilder ersetzt (alphabetisch, ohne Unterordner)."""
    files = []
    for path in paths:
        if os.path.isdir(path):
            try:
                names = [n for n in os.listdir(path) if not n.startswith(".") and is_image_file(n)]
            except OSError:
                continue
            files.extend(os.path.join(path, n) for n in sorted(names, key=natural_key))
        else:
            files.append(path)
    return files


def load_image(path: str, max_side: int = MAX_SIDE):
    """Lädt ein Bild (EXIF-Drehung angewendet) und verkleinert es auf höchstens ``max_side`` Pixel Kantenlänge.

    Gibt ``None`` zurück, wenn die Datei kein lesbares Bild ist.
    """
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    try:
        # Schnell-Weg: Ohne Dreh-Information kann schon beim Dekodieren verkleinert werden
        size = reader.size()
        no_rotation = reader.transformation() == QImageIOHandler.Transformation.TransformationNone
        if no_rotation and size.isValid() and max(size.width(), size.height()) > max_side:
            reader.setScaledSize(size.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio))
    except Exception:
        pass
    image = reader.read()
    if image.isNull():
        return None
    if max(image.width(), image.height()) > max_side:
        image = image.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    return image


def make_thumbnail(image) -> QPixmap:
    """Vorschaubild im Seitenverhältnis des Originals auf schwarzem Grund mit runden Ecken."""
    width, height = THUMB_W * THUMB_DPR, THUMB_H * THUMB_DPR
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, width, height), 8 * THUMB_DPR, 8 * THUMB_DPR)
    painter.setClipPath(clip)
    painter.fillRect(0, 0, width, height, QColor("#000000"))
    scaled = image.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    painter.drawImage((width - scaled.width()) // 2, (height - scaled.height()) // 2, scaled)
    painter.end()
    pixmap.setDevicePixelRatio(THUMB_DPR)
    return pixmap


# ----------------------------------------------------------------------
# Drag & Drop im ganzen Programm
# ----------------------------------------------------------------------
class ImageDropFilter(QObject):
    """Nimmt Bilder/Ordner an, die irgendwo auf ein Programmfenster gezogen werden.

    Ein Filter auf Anwendungsebene ist nötig, weil Textfelder (Suche, Prediger, Ansagen) Ablagen sonst selbst
    behandeln und den Dateipfad als Text einfügen würden.
    """

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        kind = event.type()
        if (kind in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop)
                and isinstance(obj, QWidget)
                and QApplication.activeModalWidget() is None):
            paths = image_paths_from_mime(event.mimeData())
            if paths:
                event.acceptProposedAction()
                if kind == QEvent.Type.Drop:
                    # erst nach Ende des Drag-Vorgangs weiterarbeiten (Meldungsfenster blockieren sonst den Finder/Explorer)
                    QTimer.singleShot(0, lambda: self._callback(paths))
                return True
        return False


# ----------------------------------------------------------------------
# Vorschau-Liste
# ----------------------------------------------------------------------
class _ThumbDelegate(QStyledItemDelegate):
    """Zeichnet jede Vorschau als Karte: ruhig = neutrale Kontur, Hover = Bronze gedämpft, gewählt = Bronze."""
    PAD = 6
    GAP = 6          # Abstand zur nächsten Karte
    RADIUS = 12

    def sizeHint(self, option, index):
        return QSize(THUMB_W + 2 * self.PAD, THUMB_H + 2 * self.PAD + self.GAP)

    def paint(self, painter, option, index):
        pixmap = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(pixmap, QPixmap):
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        card_w = THUMB_W + 2 * self.PAD
        card_h = THUMB_H + 2 * self.PAD
        card = QRectF(option.rect.x() + (option.rect.width() - card_w) / 2.0, option.rect.y(), card_w, card_h)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            pen, fill = QPen(QColor(t.ACCENT), 2), QColor(t.ACCENT_TINT)
        elif hovered:
            pen, fill = QPen(QColor(t.ACCENT_BORDER), 2), QColor(t.SURFACE_HOVER_TOP)
        else:
            pen, fill = QPen(QColor(t.BORDER), 2), QColor(0, 0, 0, 0)

        frame = QPainterPath()
        frame.addRoundedRect(card.adjusted(1, 1, -1, -1), self.RADIUS, self.RADIUS)
        painter.fillPath(frame, fill)
        painter.setPen(pen)
        painter.drawPath(frame)

        target = QRectF(card.x() + self.PAD, card.y() + self.PAD, THUMB_W, THUMB_H)
        painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        painter.restore()


class _ThumbList(w.SmoothListWidget):
    """Vorschau-Liste mit sanftem Mausrad-Scrollen.

    * Ein Rastschritt am Mausrad bewegt die Liste nur um etwa ein drittel Bild und gleitet ruhig nach (statt zu springen).
      Trackpads (Pixel-Delta) scrollen direkt und fein wie gewohnt.
    * Ein Klick oder Doppelklick auf ein halb sichtbares Bild scrollt die Liste NICHT mehr von allein;
      nur Pfeiltasten und das Programm selbst (neue Bilder, Entfernen) bringen das aktuelle Bild ins Sichtfeld.
    """
    remove_requested = pyqtSignal()
    escape_requested = pyqtSignal()
    open_current = pyqtSignal()

    _allow_scroll_to = False     # Klassenattribut: schon beim Aufbau der Basisklasse muss es existieren
    WHEEL_STEP = 48          # Pixel pro Rastschritt am Mausrad (etwa ein drittel Bild)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(_ThumbDelegate(self))
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setMovement(QListWidget.Movement.Static)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setStyleSheet("QListWidget { background: transparent; border: 0; outline: 0; }")
        self.viewport().setStyleSheet("background: transparent;")
        self.setDragEnabled(False)

    def scrollTo(self, index, hint=QAbstractItemView.ScrollHint.EnsureVisible):
        """Qt scrollt sonst bei jedem Klick auf ein angeschnittenes Bild – das passiert nur noch auf Anforderung."""
        if self._allow_scroll_to:
            super().scrollTo(index, hint)

    def scroll_to_row(self, row: int) -> None:
        item = self.item(row)
        if item is None:
            return
        self._allow_scroll_to = True
        try:
            self.scrollToItem(item)
        finally:
            self._allow_scroll_to = False

    def set_current_row_visible(self, row: int) -> None:
        self._allow_scroll_to = True
        try:
            self.setCurrentRow(row)
        finally:
            self._allow_scroll_to = False

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_requested.emit()
        elif key == Qt.Key.Key_Escape:
            self.escape_requested.emit()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.open_current.emit()
        else:
            self._allow_scroll_to = True       # Pfeiltasten dürfen das gewählte Bild ins Sichtfeld holen
            try:
                super().keyPressEvent(event)
            finally:
                self._allow_scroll_to = False
            return
        event.accept()

    def viewportEvent(self, event):
        """Eigener (abgerundeter) Tooltip pro Bild statt des eckigen Standard-Tooltips."""
        if event.type() == QEvent.Type.ToolTip:
            item = self.itemAt(event.pos())
            if item is not None and item.toolTip():
                show_tip(item.toolTip(), event.globalPos())
            return True
        return super().viewportEvent(event)


def _rounded_menu(parent) -> QMenu:
    menu = QMenu(parent)
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint
                        | Qt.WindowType.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    menu.setStyleSheet(f"""
        QMenu {{ background: {t.SURFACE}; border: 1px solid {t.ACCENT_BORDER}; border-radius: 10px;
                 padding: 5px; color: {t.TEXT_PRIMARY}; font-size: {t.FS}px; }}
        QMenu::item {{ padding: 7px 18px; border-radius: 7px; }}
        QMenu::item:selected {{ background: {t.ACCENT_TINT}; color: {t.ACCENT_LIGHT}; }}
        QMenu::separator {{ height: 1px; background: {t.BORDER}; margin: 4px 8px; }}
    """)
    return menu


# ----------------------------------------------------------------------
# Das Bilder-Panel
# ----------------------------------------------------------------------
class ImagesPanel(QWidget):
    """Bilder-Bereich der Seitenleiste (Reiter „Bilder“). Zeigt einen Hinweis zum Ablegen, solange noch nichts abgelegt wurde; mit Bildern gehört der ganze Platz der Vorschau.

    Signale:
        open_requested(int)   Bild (Zeilennummer) soll auf dem Beamer gezeigt werden
        escape_requested()    Esc im Panel -> Hauptfenster entscheidet, was geschlossen wird
        images_changed()      Anzahl der Bilder hat sich geändert
    """
    open_requested = pyqtSignal(int)
    escape_requested = pyqtSignal()
    images_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.title = QLabel("Keine Bilder")
        self.title.setStyleSheet(t.caption_style())
        header.addWidget(self.title, 1)
        self.clear_btn = w.icon_button(ICON_CLOSE, t.ACCENT_LIGHT, 12, "Alle Bilder entfernen", size=28)
        self.clear_btn.clicked.connect(self.clear)
        header.addWidget(self.clear_btn)
        layout.addLayout(header)

        # Leerer Zustand: gleiche Optik wie ein freier Kamera-Platz
        self.empty_label = QLabel("Bilder oder Ordner\nhierher ziehen")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(
            f"background: #000000; border: 2px solid {t.BORDER}; border-radius: {t.RADIUS}px; "
            f"color: {t.TEXT_MUTED}; font-size: 13px;"
        )
        self.empty_label.setToolTip("Bilder oder einen Ordner mit Bildern auf das Programm ziehen")
        layout.addWidget(self.empty_label, 1)

        self.list = _ThumbList()
        self.list.itemDoubleClicked.connect(lambda item: self.open_requested.emit(self.list.row(item)))
        self.list.open_current.connect(self._open_current)
        self.list.remove_requested.connect(self.remove_selected)
        self.list.escape_requested.connect(self.escape_requested)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_menu)
        layout.addWidget(self.list, 1)

        self._after_change()

    # ------------------------------------------------------------------
    # Zugriff
    # ------------------------------------------------------------------
    def paths(self) -> list:
        return list(self._paths)

    def count(self) -> int:
        return len(self._paths)

    # ------------------------------------------------------------------
    # Bilder hinzufügen / entfernen
    # ------------------------------------------------------------------
    def add_paths(self, paths):
        """Fügt Bilddateien (oder alle Bilder eines Ordners) hinzu. Gibt (Anzahl neu, [nicht lesbare Dateinamen]) zurück."""
        added, failed = 0, []
        first_new_row = None
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            for path in expand_paths(paths):
                if path in self._paths:
                    continue
                image = load_image(path, max_side=THUMB_W * THUMB_DPR * 2)
                if image is None:
                    failed.append(os.path.basename(path))
                    continue
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, make_thumbnail(image))
                item.setToolTip(f"{os.path.basename(path)}\nDoppelklick: auf dem Beamer zeigen\nEntf: Bild entfernen")
                self.list.addItem(item)
                self._paths.append(path)
                if first_new_row is None:
                    first_new_row = self.list.count() - 1
                added += 1
        finally:
            QApplication.restoreOverrideCursor()

        if added:
            self.list.set_current_row_visible(first_new_row)
            self.list.scroll_to_row(first_new_row)
            self._after_change()
        return added, failed

    def remove_selected(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        self.list.takeItem(row)
        del self._paths[row]
        if self.list.count():
            self.list.set_current_row_visible(min(row, self.list.count() - 1))
        self._after_change()

    def clear(self) -> None:
        self.list.clear()
        self._paths.clear()
        self._after_change()

    def _after_change(self) -> None:
        count = len(self._paths)
        self.title.setText((f"{count} Bild" if count == 1 else f"{count} Bilder") if count else "Keine Bilder")
        self.empty_label.setVisible(count == 0)
        self.list.setVisible(count > 0)
        self.clear_btn.setEnabled(count > 0)
        self.images_changed.emit()

    # ------------------------------------------------------------------
    # Bedienung
    # ------------------------------------------------------------------
    def select_row(self, row: int) -> None:
        """Markiert das Bild, das gerade auf dem Beamer läuft (heller Rahmen) und holt es ins Sichtfeld."""
        if 0 <= row < self.list.count() and row != self.list.currentRow():
            self.list.set_current_row_visible(row)
            self.list.scroll_to_row(row)

    def _open_current(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            self.open_requested.emit(row)

    def _show_menu(self, pos: QPoint) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        self.list.setCurrentItem(item)
        menu = _rounded_menu(self)
        show = menu.addAction("Auf dem Beamer zeigen")
        remove = menu.addAction("Bild entfernen")
        menu.addSeparator()
        clear = menu.addAction("Alle Bilder entfernen")
        chosen = menu.exec(self.list.viewport().mapToGlobal(pos))
        if chosen is show:
            self._open_current()
        elif chosen is remove:
            self.remove_selected()
        elif chosen is clear:
            self.clear()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.escape_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)
