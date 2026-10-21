"""Beamer-Fenster: zeigt die Liedbilder oben beginnend, horizontal zentriert, maximal groß und scharf."""
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from services.settings import app_settings

IMAGE_COLUMNS = (7, 8, 9, 10)  # bild1..bild4 im Datensatz


class ImagePresentationWindow(QWidget):
    """Zeichnet die (bis zu vier) Bilder eines Liedes nebeneinander, skaliert auf die Fenstergröße.

    Die Bilder werden direkt aus den Originalen auf die tatsächliche Bildschirmauflösung herunterskaliert
    (einmal pro Fenstergröße, danach nur noch Kopieren) – das ist schneller und schärfer als eine
    Zwischengröße.
    """

    def __init__(self, song_data=None, target_screen_index: int = 0, main_window=None):
        super().__init__()
        self.song_data = None
        self.target_screen_index = target_screen_index
        self.main_window = main_window
        self._images = []
        self._rendered = QPixmap()
        self._rendered_key = None
        self._frameless = None

        self.setWindowTitle("LiedManager – Beamer")
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        if song_data:
            self.load_song(song_data)

    # ------------------------------------------------------------------
    # Inhalt
    # ------------------------------------------------------------------
    def load_song(self, song_data):
        if not isinstance(song_data, (list, tuple)):
            return
        self.song_data = song_data
        self._images = []
        for idx in IMAGE_COLUMNS:
            data = song_data[idx] if idx < len(song_data) else None
            if data and isinstance(data, (bytes, bytearray)):
                image = QImage.fromData(bytes(data))
                if not image.isNull():
                    self._images.append(image)
        self._rendered_key = None
        self.update()

    def _render(self):
        """Setzt alle Bilder in Fenstergröße zusammen (Höhe oder Breite füllt das Fenster)."""
        dpr = self.devicePixelRatioF()
        avail_w = max(1, round(self.width() * dpr))
        avail_h = max(1, round(self.height() * dpr))
        key = (avail_w, avail_h)
        if key == self._rendered_key:
            return
        self._rendered_key = key
        self._rendered = QPixmap()
        if not self._images:
            return

        aspect = sum(img.width() / img.height() for img in self._images)
        target_h = avail_h if avail_w / avail_h >= aspect else int(avail_w / aspect)
        target_h = max(1, target_h)

        scaled = []
        for img in self._images:
            width = max(1, round(img.width() / img.height() * target_h))
            scaled.append(img.scaled(width, target_h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        total_w = sum(img.width() for img in scaled)

        canvas = QImage(total_w, target_h, QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.GlobalColor.black)
        painter = QPainter(canvas)
        x = 0
        for img in scaled:
            painter.drawImage(x, 0, img)
            x += img.width()
        painter.end()

        self._rendered = QPixmap.fromImage(canvas)
        self._rendered.setDevicePixelRatio(dpr)

    # ------------------------------------------------------------------
    # Anzeige
    # ------------------------------------------------------------------
    def _target_screen(self):
        screens = QApplication.screens()
        if 0 <= self.target_screen_index < len(screens):
            return screens[self.target_screen_index]
        return QApplication.primaryScreen()

    def show_on_target_screen(self):
        """Zeigt das Fenster auf dem gewählten Bildschirm (Vollbild oder – laut Einstellung – als Fenster)."""
        screen = self._target_screen()
        fullscreen = app_settings().value("fullscreen_mode", True, type=bool)

        if self._frameless != fullscreen:  # Fenster-Flags nur bei Moduswechsel ändern (vermeidet Flackern)
            flags = Qt.WindowType.Window
            if fullscreen:
                flags |= Qt.WindowType.FramelessWindowHint
            self.setWindowFlags(flags)
            self._frameless = fullscreen

        if fullscreen:
            self.setGeometry(screen.geometry())
            self.showFullScreen()
        else:
            area = screen.availableGeometry()
            width = int(area.width() * 0.6)
            height = min(int(width * 9 / 16), int(area.height() * 0.8))
            self.showNormal()
            self.setGeometry(QRect(area.x() + (area.width() - width) // 2,
                                   area.y() + (area.height() - height) // 2, width, height))
            self.show()

        # Fokus zurück ans Hauptfenster und ins Suchfeld
        if self.main_window:
            self.main_window.focus_search()

    # ------------------------------------------------------------------
    # Ereignisse
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        self._render()
        if not self._rendered.isNull():
            dpr = self._rendered.devicePixelRatio()
            x = (self.width() - self._rendered.width() / dpr) / 2
            painter.drawPixmap(round(x), 0, self._rendered)
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def keyPressEvent(self, event):
        """ESC (oder Q) wird an das Hauptfenster weitergeleitet."""
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            if self.main_window:
                self.main_window.handle_escape()
            else:
                self.close()
        else:
            super().keyPressEvent(event)
