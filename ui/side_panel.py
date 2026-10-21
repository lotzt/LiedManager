"""Seitenleiste links im Hauptfenster: senkrechte Icon-Reiter „Kamera“ und „Bilder“ neben einem umschaltbaren Bereich."""
from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout

from ui import theme as t
from ui import widgets as w

TAB_CAMERA, TAB_IMAGES = 0, 1


class RailButton(QPushButton):
    """Kleiner runder Reiter mit Icon; optional mit Zähler-Plakette (Anzahl der Bilder)."""
    SIZE = 40
    ICON = 20

    def __init__(self, svg: str, tooltip: str, parent=None):
        super().__init__(parent)
        self.badge = 0
        self.setCheckable(True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAutoDefault(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # Tastatur bleibt im Suchfeld
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(w.themed_icon(svg, t.ACCENT_LIGHT, self.ICON))
        self.setIconSize(QSize(self.ICON, self.ICON))
        self.setToolTip(tooltip)
        self.setStyleSheet(
            t.round_button_style(radius=self.SIZE // 2)
            + f"QPushButton:checked {{ border-color: {t.ACCENT}; background: {t.ACCENT_TINT}; }}"
        )

    def set_badge(self, count: int) -> None:
        self.badge = count
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.badge:
            return
        text = str(self.badge) if self.badge < 100 else "99+"
        width = 16 if len(text) == 1 else 22
        rect = QRectF(self.width() - width - 1, 1, width, 16)   # innerhalb des Buttons, sonst wird sie abgeschnitten
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(t.CARD_BG))
        painter.setBrush(QColor(t.ACCENT))
        painter.drawRoundedRect(rect, 8, 8)
        font = QFont(self.font())
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#1A1210"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()


class SidePanel(QFrame):
    """Zwei Bereiche in einem Rahmen: Live-Kameras und abgelegte Bilder.

    Links eine schmale senkrechte Leiste mit zwei Icon-Reitern (``QButtonGroup``), rechts der Inhalt in einem
    ``QStackedWidget``. Das Hauptfenster wechselt automatisch auf „Bilder“, sobald Bilder hineingezogen werden.
    Die Seitenleiste ist so hoch wie das Fenster – klappen die Ansagen auf, wächst sie (samt Trennlinie) mit.
    """
    PAD = 14
    RAIL_PAD = 8
    RAIL_GAP = 8
    CONTENT_WIDTH = 262        # 16:9-Kamerabild: zwei Bilder füllen das eingeklappte Fenster genau aus
    WIDTH = RAIL_PAD + RailButton.SIZE + RAIL_GAP + CONTENT_WIDTH + PAD
    COLLAPSED_WIDTH = RAIL_PAD + RailButton.SIZE + RAIL_PAD      # eingeklappt bleibt nur die Leiste mit den Reitern

    tab_changed = pyqtSignal(int)
    collapsed_changed = pyqtSignal(bool)

    def __init__(self, camera_panel, images_panel, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self.setObjectName("SidePanel")
        self.setFixedWidth(self.WIDTH)
        self.setStyleSheet(
            f"QFrame#SidePanel {{ background: {t.CARD_BG}; border: 0; border-right: 1px solid {t.BORDER}; }}"
        )

        layout = self._layout = QHBoxLayout(self)
        # 20 = gleicher Abstand oben wie das Suchfeld
        layout.setContentsMargins(self.RAIL_PAD, 20, self.PAD, self.PAD)
        layout.setSpacing(self.RAIL_GAP)

        self.stack = QStackedWidget()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        rail = QVBoxLayout()
        rail.setSpacing(8)
        entries = (
            (w.ICON_CAMERA, camera_panel, "Kamera\nLive-Kamerabilder anzeigen – nochmal klicken zum Ein- und Ausklappen"),
            (w.ICON_IMAGES, images_panel,
             "Bilder\nAbgelegte Bilder anzeigen – Bilder oder Ordner einfach auf das Programm ziehen"),
        )
        for index, (svg, page, tooltip) in enumerate(entries):
            button = RailButton(svg, tooltip)
            self.group.addButton(button, index)
            rail.addWidget(button)
            self.stack.addWidget(page)
        rail.addStretch()
        self.group.idClicked.connect(self._on_tab_clicked)
        self.group.button(TAB_CAMERA).setChecked(True)

        layout.addLayout(rail)
        layout.addWidget(self.stack, 1)

    # ------------------------------------------------------------------
    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        """Klappt den Inhalt ein (nur die Reiter-Leiste bleibt) oder aus; das Hauptfenster passt seine Breite an."""
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.stack.setVisible(not collapsed)
        self._layout.setContentsMargins(self.RAIL_PAD, 20, self.RAIL_PAD if collapsed else self.PAD, self.PAD)
        self._layout.setSpacing(0 if collapsed else self.RAIL_GAP)
        self.setFixedWidth(self.COLLAPSED_WIDTH if collapsed else self.WIDTH)
        self.collapsed_changed.emit(collapsed)

    def current_tab(self) -> int:
        return self.stack.currentIndex()

    def show_tab(self, index: int) -> None:
        """Wechselt den Reiter (auch von außen, z. B. nach dem Ablegen von Bildern)."""
        self.group.button(index).setChecked(True)
        self.set_collapsed(False)
        self._on_tab_clicked(index)

    def set_images_count(self, count: int) -> None:
        button = self.group.button(TAB_IMAGES)
        button.set_badge(count)
        button.setToolTip(
            "Bilder\nAbgelegte Bilder anzeigen – Bilder oder Ordner einfach auf das Programm ziehen"
            if not count else f"Bilder · {count}\nAbgelegte Bilder anzeigen"
        )

    def _on_tab_clicked(self, index: int) -> None:
        """Klick auf den gerade offenen Reiter klappt die Seitenleiste ein, Klick auf einen Reiter klappt sie wieder aus."""
        if index == self.stack.currentIndex():
            self.set_collapsed(not self._collapsed)
            return
        self.set_collapsed(False)
        if self.stack.currentIndex() != index:
            self.stack.setCurrentIndex(index)
            self.tab_changed.emit(index)
