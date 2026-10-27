"""Beamer-Fenster: zeigt die Liedbilder oben beginnend, horizontal zentriert, maximal groß und scharf."""
import base64
import binascii
import logging
import os
import re

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PyQt6.QtGui import QImage, QImageIOHandler, QImageReader, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from services.settings import app_settings

log = logging.getLogger(__name__)

IMAGE_COLUMNS = (7, 8, 9, 10)  # bild1..bild4 im Datensatz
MAX_SIDE = 4096                # größere Liedbilder werden schon beim Lesen verkleinert (Beamer haben höchstens 4K)
_BASE64 = re.compile(r"^(data:image/[\w.+-]+;base64,)?[A-Za-z0-9+/=\s]+$")


def _image_bytes(data):
    """Bilddaten aus der Datenbank als Bytes. Meist sind es Bytes; manche Datenbanken speichern das Bild aber als Text:
    als Base64-Text, als Dateipfad oder (SVG) als XML-Text – auch das wird erkannt."""
    if isinstance(data, memoryview):
        return data.tobytes()
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if not isinstance(data, str) or not data.strip():
        return b""
    text = data.strip()
    if len(text) < 1024 and os.path.isfile(text):             # Pfad zu einer Bilddatei
        try:
            with open(text, "rb") as handle:
                return handle.read()
        except OSError:
            return b""
    if len(text) > 64 and _BASE64.match(text[:4096]):          # Base64 (auch „data:image/png;base64,…“)
        try:
            return base64.b64decode(text.split(",", 1)[-1], validate=False)
        except (binascii.Error, ValueError):
            pass
    return text.encode("utf-8")                                # z. B. SVG als Text


def _mostly_dark(image: QImage) -> bool:
    """Ist der sichtbare (nicht durchsichtige) Inhalt überwiegend dunkel – z. B. schwarze Noten/Schrift?
    Dann braucht er einen weißen Hintergrund; heller Inhalt (weiße Schrift) bleibt auf Schwarz."""
    small = image.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
    small = small.convertToFormat(QImage.Format.Format_ARGB32)
    total, count = 0, 0
    for y in range(small.height()):
        for x in range(small.width()):
            color = small.pixelColor(x, y)
            if color.alpha() > 128:
                total += color.lightness()
                count += 1
    return count == 0 or total / count < 128


def decode_image(data, label: str = "") -> QImage:
    """Liest ein Liedbild. Die Drehung aus den Foto-Daten (EXIF, z. B. Handyfotos) wird angewendet; Bilder mit
    durchsichtigem Hintergrund bekommen einen passenden Hintergrund: weiß bei dunklem Inhalt (sonst wäre schwarze
    Schrift auf dem schwarzen Beamer unsichtbar), schwarz bei heller Schrift."""
    raw = _image_bytes(data)
    if not raw:
        return QImage()
    buffer = QBuffer()
    buffer.setData(QByteArray(raw))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    size = reader.size()
    no_rotation = reader.transformation() == QImageIOHandler.Transformation.TransformationNone
    if no_rotation and size.isValid() and max(size.width(), size.height()) > MAX_SIDE:
        # Sehr große Bilder (z. B. 10 000 Pixel) gleich verkleinert lesen: schneller, braucht wenig Speicher und
        # bleibt unter der Speichergrenze von Qt, an der solche Bilder sonst ohne Meldung scheitern
        reader.setScaledSize(size.scaled(MAX_SIDE, MAX_SIDE, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        image = QImage.fromData(raw)                           # zweiter Versuch ohne Formaterkennung des Readers
    if not image.isNull() and max(image.width(), image.height()) > MAX_SIDE:     # gedrehte Fotos: erst jetzt verkleinern
        image = image.scaled(MAX_SIDE, MAX_SIDE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    if image.isNull():
        log.warning("Liedbild %s lässt sich nicht lesen (%s, %d Bytes, beginnt mit %r)", label,
                    reader.errorString(), len(raw), raw[:12])
        return QImage()
    if image.hasAlphaChannel():
        flat = QImage(image.size(), QImage.Format.Format_RGB32)
        flat.fill(Qt.GlobalColor.white if _mostly_dark(image) else Qt.GlobalColor.black)
        painter = QPainter(flat)
        painter.drawImage(0, 0, image)
        painter.end()
        image = flat
    return image


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
        number = song_data[1] if len(song_data) > 1 else "?"
        for position, idx in enumerate(IMAGE_COLUMNS, 1):
            data = song_data[idx] if idx < len(song_data) else None
            if data:
                image = decode_image(data, f"{number}/bild{position}")
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
                # Immer oben (wie das Kamera-Vollbild): ein Klick ins Hauptfenster oder in ein anderes Programm darf das
                # Beamer-Bild nicht verdecken – unter Windows sah das aus, als würde es geschlossen
                flags |= Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            self._frameless = fullscreen

        if fullscreen:
            from ui.widgets import show_fullscreen_on
            show_fullscreen_on(self, screen)                  # zuverlässig auf den Beamer (auch unter Windows)
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
