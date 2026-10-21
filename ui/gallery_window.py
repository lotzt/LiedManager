"""Beamer-Galerie für abgelegte Bilder: Klick = nächstes Bild, Rechtsklick = zurück, Schließen-Button.

Bildwechsel werden kurz überblendet; wer über das letzte Bild hinausblättert, sieht kurz den Hinweis „Ende“."""
import time
from collections import OrderedDict

from PyQt6.QtCore import QAbstractAnimation, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QLabel

from ui import theme as t
from ui import widgets as w
from ui.images_panel import ICON_CLOSE, MAX_SIDE, load_image
from ui.presentation_window import ImagePresentationWindow

ICON_CHEVRON_LEFT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M15 6l-6 6 6 6"></path>
</svg>"""

ICON_CHEVRON_RIGHT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M9 6l6 6-6 6"></path>
</svg>"""

OVERLAY_BG = "rgba(26, 24, 23, 225)"
IDLE_MS = 2500          # so lange nach der letzten Mausbewegung bleiben Buttons und Mauszeiger sichtbar
WHEEL_PAUSE = 0.35      # Sekunden Pause zwischen zwei Seitenwechseln per Mausrad/Trackpad
CACHE_SIZE = 4
FADE_MS = 150           # Dauer der Überblendung zwischen zwei Bildern
END_HINT_MS = 2000      # So lange bleibt der „Ende“-Hinweis sichtbar
END_HINT_TEXT = "Ende  ·  Esc beendet"


class GalleryWindow(ImagePresentationWindow):
    """Zeigt die Bilder der Ablage einzeln im Vollbild auf dem Beamer-Bildschirm.

    Bedienung:  Klick / Pfeil rechts / Leertaste / Bild-ab = weiter · Rechtsklick / Pfeil links / Bild-auf = zurück
                Esc / Q / Schließen-Button = beenden.
    Die Bedienelemente erscheinen nur, solange die Maus bewegt wird – für das Publikum bleibt das Bild sauber.
    """
    close_requested = pyqtSignal()
    index_changed = pyqtSignal(int)      # Nummer des Bildes, das jetzt auf dem Beamer steht

    def __init__(self, paths, start_index: int = 0, target_screen_index: int = 0, main_window=None):
        super().__init__(None, target_screen_index, main_window)
        self._paths = list(paths)
        self._index = max(0, min(start_index, len(self._paths) - 1))
        self._cache = OrderedDict()      # Pfad -> QImage | None
        self._failed = False
        self._last_wheel = 0.0
        self._overlay_visible = False
        self._fade_old = None            # vorheriges Bild (QPixmap) während der Überblendung
        self._fade_progress = 1.0

        self.setWindowTitle("LiedManager – Bilder")
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.BlankCursor)

        self._close_btn = self._overlay_button(ICON_CLOSE, "Galerie schließen (Esc)", icon=16)
        self._prev_btn = self._overlay_button(ICON_CHEVRON_LEFT, "Vorheriges Bild (Rechtsklick oder Pfeil links)")
        self._next_btn = self._overlay_button(ICON_CHEVRON_RIGHT, "Nächstes Bild (Klick oder Pfeil rechts)")
        self._close_btn.clicked.connect(self.close_requested)
        self._prev_btn.clicked.connect(lambda: self.step(-1))
        self._next_btn.clicked.connect(lambda: self.step(1))

        self._page_label = QLabel(self)
        self._page_label.setStyleSheet(
            f"background: {OVERLAY_BG}; border: 1px solid {t.ACCENT_BORDER}; border-radius: 15px; "
            f"padding: 5px 16px; color: {t.TEXT_PRIMARY}; font-size: 13px; font-weight: 500;"
        )
        self._page_label.hide()

        self._end_label = QLabel(END_HINT_TEXT, self)
        self._end_label.setStyleSheet(
            f"background: {OVERLAY_BG}; border: 1px solid {t.ACCENT_BORDER}; border-radius: 18px; "
            f"padding: 8px 22px; color: {t.TEXT_PRIMARY}; font-size: 15px; font-weight: 500;"
        )
        self._end_label.hide()
        self._end_timer = QTimer(self)
        self._end_timer.setSingleShot(True)
        self._end_timer.setInterval(END_HINT_MS)
        self._end_timer.timeout.connect(self._end_label.hide)

        self._fade_anim = QVariantAnimation(self)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setDuration(FADE_MS)
        self._fade_anim.valueChanged.connect(self._on_fade_value)
        self._fade_anim.finished.connect(self._on_fade_finished)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(IDLE_MS)
        self._idle_timer.timeout.connect(self._hide_overlay)

        self._show_current()

    # ------------------------------------------------------------------
    # Bilder
    # ------------------------------------------------------------------
    def _image(self, index: int):
        path = self._paths[index]
        if path in self._cache:
            self._cache.move_to_end(path)
            return self._cache[path]
        image = load_image(path, MAX_SIDE)
        self._cache[path] = image
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return image

    def _show_current(self, animate: bool = False) -> None:
        old = self._rendered              # aktuell sichtbares Bild, bevor es ersetzt wird
        image = self._image(self._index)
        self._images = [image] if image is not None else []   # Darstellung übernimmt ImagePresentationWindow
        self._failed = image is None
        self._rendered_key = None
        self._end_label.hide()
        self._update_controls()
        self.index_changed.emit(self._index)

        self._fade_anim.stop()
        self._fade_old = None
        if animate and self.isVisible() and not old.isNull():
            self._fade_old = old
            self._fade_progress = 0.0
            self._fade_anim.start()
        self.update()
        QTimer.singleShot(80, self._prefetch)

    def _on_fade_value(self, value) -> None:
        self._fade_progress = float(value)
        self.update()

    def _on_fade_finished(self) -> None:
        self._fade_old = None
        self._fade_progress = 1.0
        self.update()

    def _show_end_hint(self) -> None:
        """Kurzer Hinweis, dass hinter dem letzten Bild nichts mehr kommt (statt eines scheinbar toten Klicks)."""
        self._end_label.adjustSize()
        self._end_label.move((self.width() - self._end_label.width()) // 2,
                             self.height() - self._end_label.height() - 90)
        self._end_label.show()
        self._end_label.raise_()
        self._end_timer.start()

    def _prefetch(self) -> None:
        """Das nächste Bild schon im Hintergrund laden, damit das Weiterklicken ohne Verzögerung klappt."""
        nxt = self._index + 1
        if nxt < len(self._paths) and self.isVisible():
            self._image(nxt)

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def image_count(self) -> int:
        return len(self._paths)

    def step(self, delta: int) -> None:
        if delta > 0 and self._index >= len(self._paths) - 1:
            self._show_end_hint()
            return
        self.goto(self._index + delta)

    def goto(self, index: int) -> None:
        index = max(0, min(index, len(self._paths) - 1))
        if index != self._index:
            self._index = index
            self._show_current(animate=True)

    # ------------------------------------------------------------------
    # Bedienelemente
    # ------------------------------------------------------------------
    def _overlay_button(self, svg: str, tooltip: str, icon: int = 20):
        style = t.round_button_style(background=OVERLAY_BG, border=t.ACCENT_BORDER, hover_border=t.ACCENT)
        button = w.icon_button(svg, t.ACCENT_LIGHT, icon, tooltip, style=style, size=t.BTN)
        button.setParent(self)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.hide()
        return button

    def _controls(self):
        multiple = len(self._paths) > 1
        return [(self._close_btn, True), (self._prev_btn, multiple),
                (self._next_btn, multiple), (self._page_label, multiple)]

    def _update_controls(self) -> None:
        total = len(self._paths)
        self._page_label.setText(f"{self._index + 1} / {total}")
        self._page_label.adjustSize()
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < total - 1)
        self._layout_controls()
        if self._overlay_visible:
            self._set_overlay(True)

    def _layout_controls(self) -> None:
        margin = 20
        self._close_btn.move(self.width() - self._close_btn.width() - margin, margin)
        middle = (self.height() - self._prev_btn.height()) // 2
        self._prev_btn.move(margin, middle)
        self._next_btn.move(self.width() - self._next_btn.width() - margin, middle)
        self._page_label.move((self.width() - self._page_label.width()) // 2,
                              self.height() - self._page_label.height() - margin)

    def _set_overlay(self, visible: bool) -> None:
        self._overlay_visible = visible
        for widget, wanted in self._controls():
            widget.setVisible(visible and wanted)
            if visible and wanted:
                widget.raise_()

    def _on_mouse_activity(self) -> None:
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if not self._overlay_visible:
            self._set_overlay(True)
        self._idle_timer.start()

    def _hide_overlay(self) -> None:
        if any(widget.underMouse() for widget, _wanted in self._controls()):
            self._idle_timer.start()     # Maus ruht auf einem Button: sichtbar lassen
            return
        self._set_overlay(False)
        self.setCursor(Qt.CursorShape.BlankCursor)

    # ------------------------------------------------------------------
    # Ereignisse
    # ------------------------------------------------------------------
    def mouseMoveEvent(self, event):
        self._on_mouse_activity()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.step(1)
        elif event.button() == Qt.MouseButton.RightButton:
            self.step(-1)
        else:
            super().mousePressEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        now = time.monotonic()
        if delta and now - self._last_wheel > WHEEL_PAUSE:
            self._last_wheel = now
            self.step(-1 if delta > 0 else 1)
        event.accept()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close_requested.emit()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Space, Qt.Key.Key_PageDown,
                     Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.step(1)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Backspace):
            self.step(-1)
        elif key == Qt.Key.Key_Home:
            self.goto(0)
        elif key == Qt.Key.Key_End:
            self.goto(len(self._paths) - 1)
        else:
            event.ignore()
            return
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_controls()

    def paintEvent(self, event):
        """Bild in der Fenstermitte (Lieder beginnen oben, einzelne Bilder wirken mittig besser)."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        self._render()
        fading = (self._fade_old is not None
                  and self._fade_anim.state() == QAbstractAnimation.State.Running)
        if fading:
            # Überblendung: altes Bild blendet aus, neues addiert sich ein (Summe bleibt überall korrekt hell)
            progress = self._fade_progress
            painter.setOpacity(1.0 - progress)
            self._draw_centered(painter, self._fade_old)
            painter.setOpacity(progress)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            self._draw_centered(painter, self._rendered)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setOpacity(1.0)
        elif not self._rendered.isNull():
            self._draw_centered(painter, self._rendered)
        if self._rendered.isNull() and self._failed:
            painter.setPen(QColor(t.TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Dieses Bild konnte nicht geladen werden.")
        painter.end()

    def _draw_centered(self, painter: QPainter, pixmap: QPixmap) -> None:
        if pixmap is None or pixmap.isNull():
            return
        dpr = pixmap.devicePixelRatio()
        x = (self.width() - pixmap.width() / dpr) / 2
        y = (self.height() - pixmap.height() / dpr) / 2
        painter.drawPixmap(round(x), round(y), pixmap)

    def closeEvent(self, event):
        self._fade_anim.stop()
        self._end_timer.stop()
        self._idle_timer.stop()
        self._cache.clear()
        super().closeEvent(event)
