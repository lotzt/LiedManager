"""Seitenleiste links im Hauptfenster: die Kameras, darunter die Bilder-Ablage (scrollbar). Keine Reiterleiste."""
from PyQt6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout,
                             QWidget)

from ui import theme as t
from ui import widgets as w

TAB_CAMERA, TAB_IMAGES = 0, 1


class TabButton(QPushButton):
    """Gleich breiter Reiter mit Icon und Beschriftung; optional mit Zähler-Plakette (Anzahl der Bilder)."""
    HEIGHT = 32
    ICON = 16

    def __init__(self, svg: str, text: str, tooltip: str, parent=None):
        super().__init__(text, parent)
        self.badge = 0
        self.setCheckable(True)
        self.setFixedHeight(self.HEIGHT)
        self.setAutoDefault(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # Tastatur bleibt im Suchfeld
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(w.themed_icon(svg, t.ACCENT_LIGHT, self.ICON))
        self.setIconSize(QSize(self.ICON, self.ICON))
        self.setToolTip(tooltip)
        self.setStyleSheet(
            t.round_button_style(radius=self.HEIGHT // 2)
            + f"QPushButton {{ padding: 0 12px; font-size: {t.FS_SMALL + 1}px; color: {t.TEXT_LABEL}; }}"
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
        rect = QRectF(self.width() - width - 8, (self.height() - 16) / 2, width, 16)
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

    Oben eine Leiste mit zwei gleich breiten Reitern (``QButtonGroup``), darunter der Inhalt in einem
    ``QStackedWidget``. Das Hauptfenster wechselt automatisch auf „Bilder“, sobald Bilder hineingezogen werden.
    Die Seitenleiste ist so hoch wie das Fenster – klappen die Ansagen auf, wächst sie (samt Trennlinie) mit.
    """
    MARGIN_L, MARGIN_R, MARGIN_V = 12, 6, 12   # Abstand des Rahmens zum Fensterrand / zum Hauptfeld
    PAD = 12                   # Innenabstand im Rahmen
    CONTENT_WIDTH = 206        # Breite des 16:9-Kamerabilds; Höhe der Seitenleiste = Fensterhöhe, darunter bleibt Platz für den Bilder-Hinweis
    WIDTH = MARGIN_L + MARGIN_R + 2 * PAD + CONTENT_WIDTH
    TAB_GAP = 10

    tab_changed = pyqtSignal(int)

    def __init__(self, camera_panel, images_panel, parent=None):
        super().__init__(parent)
        self.setObjectName("SidePanel")
        self.setFixedWidth(self.WIDTH)
        self.setStyleSheet(
            f"QFrame#SidePanel {{ background: {t.CARD_BG}; border: 0; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.MARGIN_L, self.MARGIN_V, self.MARGIN_R, self.MARGIN_V)
        outer.setSpacing(0)
        # Ein Rahmen um Reiter und Inhalt – endet oben und unten genau wie der Rahmen des Hauptfelds
        pane = QFrame()
        pane.setObjectName("Pane")
        pane.setStyleSheet(
            f"QFrame#Pane {{ background: {t.SURFACE_LOW}; border: 1px solid {t.BORDER}; border-radius: {t.RADIUS}px; }}")
        outer.addWidget(pane)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(self.PAD, self.PAD, self.PAD, self.PAD)
        layout.setSpacing(self.TAB_GAP)

        self.stack = QStackedWidget()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        # Eine scrollbare Seite: oben die Kameras, darunter eine Zeile mit der Anzahl („Keine Bilder“ + ✕), darunter das
        # Bilder-Feld. Die Zeile liegt genau auf Höhe der Pausentimer-Kopfzeile rechts und ist genauso hoch; die Kameras
        # enden an deren Oberkante, das Feld beginnt an deren Unterkante (= Oberkante des Ansagen-Textfelds). Weil der
        # Text mittig in der Zeile steht, sind die Abstände Kamera → „Keine Bilder“ → Feld immer exakt gleich.
        from ui.camera_panel import ASPECT_H, ASPECT_W
        self._camera = camera_panel
        self._slot_gap = camera_panel.SLOT_GAP
        self._slot_count = camera_panel.SLOT_COUNT
        self._slot_h = round(self.CONTENT_WIDTH * ASPECT_H / ASPECT_W)     # vorläufig, bis set_field_span die Lage kennt
        camera_panel.set_slot_height(self._slot_h)
        self._cam_h = camera_panel.height()
        content = QWidget()
        cam_layout = QVBoxLayout(content)
        cam_layout.setContentsMargins(0, 0, 0, 0)
        cam_layout.setSpacing(0)                     # Abstände ergeben sich allein aus den festen Höhen
        cam_layout.addWidget(camera_panel)
        self.images_count_box = QWidget()
        count_layout = QHBoxLayout(self.images_count_box)
        count_layout.setContentsMargins(0, 0, 0, 0)
        count_layout.setSpacing(8)
        self.images_count_label = QLabel("Keine Bilder")
        self.images_count_label.setStyleSheet(t.caption_style())
        self.images_count_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        count_layout.addWidget(self.images_count_label, 1, Qt.AlignmentFlag.AlignVCenter)
        count_layout.addWidget(images_panel.take_clear_button(), 0, Qt.AlignmentFlag.AlignVCenter)
        cam_layout.addWidget(self.images_count_box)
        images_panel.setMinimumHeight(0)
        self._images_panel = images_panel
        cam_layout.addWidget(images_panel)
        cam_layout.addStretch(1)                     # übriger Platz bleibt unten frei – nichts rückt auseinander
        cam_page = QScrollArea()
        cam_page.setWidgetResizable(True)
        cam_page.setFrameShape(QFrame.Shape.NoFrame)
        cam_page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cam_page.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)   # keine Leiste; das Mausrad / Trackpad scrollt
        cam_page.setStyleSheet("QScrollArea { background: transparent; border: 0; } QScrollArea > QWidget > QWidget { background: transparent; }")
        cam_page.setWidget(content)
        self._scroll = cam_page
        images_page = QWidget()                      # Platzhalter: den Reiter „Bilder“ gibt es nicht mehr, nur der Zähler bleibt
        tabs = QHBoxLayout()
        tabs.setSpacing(8)
        entries = (
            (w.ICON_CAMERA, cam_page, "Kamera", "Kamera\nLive-Kamerabilder anzeigen"),
            (w.ICON_IMAGES, images_page, "Bilder",
             "Bilder\nAbgelegte Bilder anzeigen – Bilder oder Ordner einfach auf das Programm ziehen"),
        )
        for index, (svg, page, text, tooltip) in enumerate(entries):
            button = TabButton(svg, text, tooltip)
            self.group.addButton(button, index)
            tabs.addWidget(button, 1)
            self.stack.addWidget(page)
        self.group.idClicked.connect(self._on_tab_clicked)
        self.group.button(TAB_CAMERA).setChecked(True)

        for button in self.group.buttons():           # Reiterleiste ist entfernt; die Knöpfe bleiben nur für den Zähler
            button.setParent(self)
            button.hide()
        layout.addWidget(self.stack, 1)
        self._open = False
        self._field_top = None            # Lage des Ansagen-Textfelds in Seitenleisten-Koordinaten (siehe set_field_span)
        self._field_height = 0
        self._head_h = 0

    # ------------------------------------------------------------------
    def set_field_span(self, top: int, height: int, header_height: int) -> None:
        """Lage rechts in Koordinaten des Seitenleisten-Inhalts: ``top`` = Oberkante des Ansagen-Textfelds,
        ``height`` = seine Höhe, ``header_height`` = Höhe der Pausentimer-Kopfzeile direkt darüber."""
        self._field_top = top
        self._field_height = height
        self._head_h = header_height
        self._apply_rows()
        self.set_open(self._open)

    def _apply_rows(self) -> None:
        """Kameras enden an der Oberkante der Pausentimer-Kopfzeile; die Anzahl-Zeile füllt die Kopfzeile genau aus."""
        if self._field_top is None:
            return
        head_top = self._field_top - self._head_h
        slot_h = max(40, (head_top - (self._slot_count - 1) * self._slot_gap) // self._slot_count)
        if slot_h != self._slot_h or self._camera.height() != self._cam_h:
            self._slot_h = slot_h
            self._camera.set_slot_height(slot_h)
            self._cam_h = self._camera.height()
        # ein ungerader Rest (1 px) landet in der Anzahl-Zeile, damit das Feld trotzdem exakt am Textfeld beginnt
        self.images_count_box.setFixedHeight(max(24, self._field_top - self._cam_h))

    def set_open(self, is_open: bool) -> None:
        """Zugeklappt: Kameras, darunter die Anzahl; die Bilder-Ablage liegt unter dem sichtbaren Bereich (nach unten
        scrollen). Aufgeklappt: Bilder-Feld auf gleicher Höhe und so hoch wie das Textfeld der Ansagen."""
        self._open = is_open
        if is_open:
            self._apply_open_panel()
        else:
            self._apply_closed_panel()
        self._scroll.verticalScrollBar().setValue(0)
        poll = getattr(self, "_poll", None)
        if is_open:
            self._hide_until_aligned()
            if poll is not None:
                poll.start()
        else:
            self._show_images()
            if poll is not None:
                poll.stop()

    def _apply_open_panel(self) -> None:
        panel = self._images_panel
        height = self._field_height or self._slot_h
        if panel.count() == 0:                         # ohne Bilder genau so hoch wie das Textfeld
            panel.setMinimumHeight(height)
            panel.setMaximumHeight(height)
        else:                                          # mit Bildern so hoch wie alle Vorschauen – sonst lässt sich nicht scrollen
            panel.setMinimumHeight(max(height, panel.list.minimumHeight()))
            panel.setMaximumHeight(16777215)

    def _apply_closed_panel(self) -> None:
        """Zugeklappt: Ohne Bilder ist das leere Feld so hoch wie ein Kamerabild und endet beim Herunterscrollen vollständig
        (mit runden Ecken) am unteren Rand. Mit Bildern wächst die Ablage mit der Vorschau."""
        panel = self._images_panel
        if panel.count() == 0:
            panel.setMinimumHeight(self._slot_h)
            panel.setMaximumHeight(self._slot_h)
        else:
            panel.setMinimumHeight(panel.list.minimumHeight())   # ganze Liste, damit bis zum letzten Bild gescrollt werden kann
            panel.setMaximumHeight(16777215)

    def _hide_until_aligned(self) -> None:
        """Beim Aufklappen springt das Feld sonst kurz an eine falsche Stelle: unsichtbar halten, bis es ausgerichtet ist."""
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        effect = QGraphicsOpacityEffect(self._images_panel)
        effect.setOpacity(0.0)
        self._images_panel.setGraphicsEffect(effect)
        QTimer.singleShot(450, self._show_images)        # Notausgang, falls die Ausrichtung nie läuft

    def _show_images(self) -> None:
        self._images_panel.setGraphicsEffect(None)

    def set_align_source(self, header_label, text_edit) -> None:
        """Merkt sich Pausentimer-Kopfzeile und Ansagen-Textfeld und misst bei jeder Lage-/Größenänderung (Fenstergröße,
        Aufklappen, Skalierung) nach, damit Kameras, Anzahl-Zeile und Bilder-Feld exakt dazu passen."""
        self._align_header = header_label
        self._align_source = text_edit
        self._align_timer = QTimer(self)
        self._align_timer.setSingleShot(True)
        self._align_timer.setInterval(40)
        self._align_timer.timeout.connect(self._realign)
        self._poll = QTimer(self)                      # Sicherheitsnetz: Abweichung (z. B. durch spätere Layout-Änderungen) wird ausgeglichen
        self._poll.setInterval(150)
        self._poll.timeout.connect(self._check_alignment)
        widget = header_label.parentWidget()
        while widget is not None:                      # Verschiebt sich ein Elternteil, bekommt die Kopfzeile selbst kein Move-Ereignis
            widget.installEventFilter(self)
            widget = widget.parentWidget()
        header_label.installEventFilter(self)
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if (getattr(self, "_align_timer", None) is not None
                and event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show)):
            self._align_timer.start()
        return super().eventFilter(obj, event)

    def _measure(self):
        """Gemessene Lage rechts (Oberkante Textfeld, Höhe Kopfzeile) in Koordinaten des Seitenleisten-Inhalts."""
        from PyQt6.QtCore import QPoint
        header = getattr(self, "_align_header", None)
        if header is None or not header.isVisible():
            return None
        window = header.window()
        scroll = self._scroll.verticalScrollBar().value()
        content_top = self._scroll.widget().mapTo(window, QPoint(0, 0)).y() + scroll
        field_top = header.mapTo(window, QPoint(0, 0)).y() + header.height() - content_top
        return field_top, header.height()

    def _check_alignment(self) -> None:
        measured = self._measure()
        if measured is not None and measured != (self._field_top, self._head_h):
            self._realign()

    def _realign(self) -> None:
        if getattr(self, "_align_source", None) is not None:
            self.align_field(self._align_source)

    def align_field(self, text_edit=None) -> None:
        """Am fertigen Layout nachmessen und Kameras / Anzahl-Zeile / Bilder-Feld exakt an Kopfzeile und Textfeld ausrichten –
        so stimmt es unabhängig von Schrift, Skalierung und Abständen."""
        measured = self._measure()
        if measured is not None:
            field_top, head_h = measured
            if text_edit is not None and text_edit.height() > 0:
                self._field_height = text_edit.height()
            if (field_top, head_h) != (self._field_top, self._head_h):
                self._field_top, self._head_h = field_top, head_h
                self._apply_rows()
            if self._open:
                self._apply_open_panel()
            else:
                self._apply_closed_panel()
            self._scroll.widget().layout().activate()
        self._show_images()

    def current_tab(self) -> int:
        return self.stack.currentIndex()

    def show_tab(self, index: int) -> None:
        """Ohne Reiterleiste gibt es nur noch eine Seite (Kameras, darunter die Bilder-Ablage)."""
        self.group.button(TAB_CAMERA).setChecked(True)
        self._on_tab_clicked(TAB_CAMERA)

    def set_images_count(self, count: int) -> None:
        self._images_count = count
        if self._open:
            self._apply_open_panel()
        else:
            self._apply_closed_panel()
        self.images_count_label.setText((f"{count} Bild" if count == 1 else f"{count} Bilder") if count else "Keine Bilder")
        button = self.group.button(TAB_IMAGES)
        button.set_badge(count)
        button.setToolTip(
            "Bilder\nAbgelegte Bilder anzeigen – Bilder oder Ordner einfach auf das Programm ziehen"
            if not count else f"Bilder · {count}\nAbgelegte Bilder anzeigen"
        )

    def _on_tab_clicked(self, index: int) -> None:
        if self.stack.currentIndex() != index:
            self.stack.setCurrentIndex(index)
            self.tab_changed.emit(index)
