"""Kamera-Panel im Hauptfenster (Reiter „Kamera“): zwei Live-Kameras im 16:9-Format, Vollbild per Doppelklick."""
import logging

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QKeyEvent, QPainterPath, QRegion
from PyQt6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication, QFrame, QLabel, QVBoxLayout, QWidget,
)

from services import atem
from services.settings import app_settings
from ui import theme as t
from ui import widgets as w
from ui.tooltip import hide_tip, show_tip

log = logging.getLogger(__name__)

SLOT_BORDER = 2      # Rahmenbreite (immer gleich, damit sich beim Hovern/Wählen nichts verschiebt)
SLOT_INSET = 4       # Abstand Rahmen -> Bild (schwarzer „Passepartout“, hält die Ecken sauber rund)
SLOT_RADIUS = t.RADIUS
VIDEO_RADIUS = 8
ASPECT_W, ASPECT_H = 16, 9   # typisches Kameraformat


class CameraSlot(QFrame):
    """Ein Kamerabild mit Rahmen.

    Rahmen: Ruhe = neutral, Maus darüber = Bronze gedämpft, per Klick gewählt = Bronze, Vollbild aktiv = Bronze gestrichelt.

    Der Hover wird per Abfrage der Mausposition erkannt (CameraPanel), weil das native Videobild
    unter macOS/Windows keine Mausereignisse an Qt weitergibt.
    """
    fullscreen_toggled = pyqtSignal(int)
    escape_pressed = pyqtSignal(int)

    PLACEHOLDERS = {
        "empty": "Keine Kamera",
        "missing": "Kamera nicht verfügbar",
        "fullscreen": "Im Vollbild  ·  Esc beendet",
    }

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.state = "empty"
        self.setObjectName("CamSlot")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)   # nur per Klick gewählt, nie automatisch
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Kamerabild\nDoppelklick: auf dem Beamer zeigen\nEsc: Vollbild beenden")
        self.setStyleSheet(f"""
            QFrame#CamSlot {{
                background: #000000;
                border: {SLOT_BORDER}px solid {t.BORDER};
                border-radius: {SLOT_RADIUS}px;
            }}
            QFrame#CamSlot[idle="true"] {{ background: {t.SURFACE_LOW}; }}
            QFrame#CamSlot[hover="true"] {{ border-color: {t.ACCENT_BORDER}; }}
            QFrame#CamSlot:focus {{ border-color: {t.ACCENT}; }}
            QFrame#CamSlot[fullscreen="true"] {{ border: {SLOT_BORDER}px dashed {t.ACCENT_BORDER}; }}
            QFrame#CamSlot[fullscreen="true"]:focus {{ border: {SLOT_BORDER}px dashed {t.ACCENT}; }}
            QFrame#CamSlot QLabel {{
                background: transparent; border: 0; color: {t.TEXT_MUTED}; font-size: 13px;
            }}
        """)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(SLOT_INSET, SLOT_INSET, SLOT_INSET, SLOT_INSET)
        self._layout.setSpacing(0)

        self.video = QVideoWidget()
        self.video.setStyleSheet("background: #000000;")
        self.video.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._layout.addWidget(self.video, 1)

        self.placeholder_icon = QLabel()
        self.placeholder_icon.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.placeholder_icon.setPixmap(w.themed_icon(w.ICON_CAMERA, t.TEXT_MUTED, 28).pixmap(28, 28))
        self._layout.addWidget(self.placeholder_icon, 1)

        self.placeholder = QLabel()
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._layout.addWidget(self.placeholder, 1)

        self.set_state("empty")

    # ------------------------------------------------------------------
    def set_state(self, state: str) -> None:
        """"live" (Bild sichtbar) | "empty" | "missing" | "fullscreen" (Bild läuft im Vollbild-Fenster)."""
        self.state = state
        if state != "fullscreen":
            self.video.setVisible(state == "live")
        self.placeholder.setVisible(state != "live")
        self.placeholder_icon.setVisible(state in ("empty", "missing"))
        self.setProperty("idle", state in ("empty", "missing"))
        self.placeholder.setText(self.PLACEHOLDERS.get(state, ""))
        self.setProperty("fullscreen", state == "fullscreen")
        self._repolish()
        self._update_mask()

    def _repolish(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)

    def set_hovered(self, hovered: bool) -> None:
        if bool(self.property("hover")) != hovered:
            self.setProperty("hover", hovered)
            self._repolish()

    def take_video_back(self) -> None:
        """Holt das Videobild aus dem Vollbild-Fenster zurück in den Rahmen."""
        self.video.setParent(self)
        self._layout.insertWidget(0, self.video, 1)
        self.set_state("live")

    def _update_mask(self) -> None:
        """Rundet die Ecken des Videobilds (bei Vollbild bleibt es eckig)."""
        if self.state != "live" or self.video.parent() is not self:
            return
        width = self.width() - 2 * SLOT_INSET
        height = self.height() - 2 * SLOT_INSET
        if width <= 2 * VIDEO_RADIUS or height <= 2 * VIDEO_RADIUS:
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, width, height), VIDEO_RADIUS, VIDEO_RADIUS)
        self.video.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_mask()

    def mouseDoubleClickEvent(self, event):
        """Doppelklick = aufs Beamer-Bild werfen bzw. wieder zurück (wie bei den Bildern)."""
        if event.button() == Qt.MouseButton.LeftButton and self.state in ("live", "fullscreen"):
            self.fullscreen_toggled.emit(self.index)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit(self.index)
            event.accept()
        else:
            super().keyPressEvent(event)


class FullscreenWindow(QWidget):
    """Schwarzes Vollbild-Fenster für ein Kamerabild (Esc beendet es)."""
    close_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class CameraPanel(QWidget):
    """Kamera-Bereich der Seitenleiste mit ATEM-Integration (ein normales Widget, kein eigenes Fenster)."""

    SLOT_COUNT = 2
    SLOT_GAP = t.GAP - 2

    fullscreen_opening = pyqtSignal()   # ein Kamerabild geht gleich auf den Beamer -> anderes dort schließen

    def __init__(self, parent=None):
        super().__init__(parent)
        self._streams = [None] * self.SLOT_COUNT        # je Platz: (QCamera, QMediaCaptureSession)
        self._fullscreen = {}                           # Platz -> FullscreenWindow
        self._atem_active = False
        self._tip_slot = None
        self._tip_pos = QCursor.pos()
        self._tip_ticks = 0
        self._tip_shown = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.SLOT_GAP)
        self.slots = []
        for index in range(self.SLOT_COUNT):
            slot = CameraSlot(index, self)
            slot.fullscreen_toggled.connect(self.toggle_fullscreen)
            slot.escape_pressed.connect(self.close_fullscreen)
            layout.addWidget(slot)
            self.slots.append(slot)
        layout.addStretch(1)   # klappen die Ansagen auf, bleibt die Bildgröße gleich (16:9)

        self._init_camera_streams()

        # Hover-Rahmen: Mausposition regelmäßig prüfen (funktioniert auch über dem nativen Videobild)
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(80)
        self._hover_timer.timeout.connect(self._poll_hover)
        self._hover_timer.start()

    _slot_height = None     # feste Höhe je Kamerafeld (von der Seitenleiste gesetzt), sonst 16:9 nach Breite

    def set_slot_height(self, height: int) -> None:
        """Feste Höhe je Kamerafeld; das Panel ist dann genau so hoch wie alle Felder samt Abständen."""
        self._slot_height = height
        self.setFixedHeight(self.SLOT_COUNT * height + (self.SLOT_COUNT - 1) * self.SLOT_GAP)
        for slot in self.slots:
            slot.setFixedHeight(height)

    def resizeEvent(self, event):
        """Jedes Kamerabild bekommt das Seitenverhältnis 16:9 passend zur Breite des Panels (außer bei fester Höhe)."""
        super().resizeEvent(event)
        height = self._slot_height or round(self.width() * ASPECT_H / ASPECT_W)
        for slot in self.slots:
            if slot.height() != height:
                slot.setFixedHeight(height)

    # ------------------------------------------------------------------
    # Hover
    # ------------------------------------------------------------------
    def _slot_under_cursor(self):
        if not self.isVisible():
            return None
        pos = QCursor.pos()
        # liegt ein anderes Fenster (Einstellungen, Meldung …) über der Stelle, gehört der Hover nicht uns
        active = QApplication.activeWindow()
        if active is None or active is not self.window():       # App im Hintergrund oder anderes Fenster aktiv: kein Hover
            return None
        top = QApplication.widgetAt(pos)
        if top is not None and top.window() is not self.window():
            return None
        for slot in self.slots:
            if slot.isVisible() and slot.rect().contains(slot.mapFromGlobal(pos)):
                return slot
        return None

    def _poll_hover(self):
        hovered = self._slot_under_cursor()
        for slot in self.slots:
            slot.set_hovered(slot is hovered)

        # Über dem nativen Videobild löst Qt keine Tooltips aus -> Erklärung nach kurzer Ruhezeit selbst zeigen
        pos = QCursor.pos()
        if hovered is not self._tip_slot or (pos - self._tip_pos).manhattanLength() > 6:
            if self._tip_shown:
                hide_tip()
                self._tip_shown = False
            self._tip_slot, self._tip_pos, self._tip_ticks = hovered, pos, 0
            return
        if hovered is not None and not self._tip_shown:
            self._tip_ticks += 1
            if self._tip_ticks >= 8:  # ca. 0,6 s
                show_tip(hovered.toolTip(), pos)
                self._tip_shown = True

    # ------------------------------------------------------------------
    # Kamera-Streams
    # ------------------------------------------------------------------
    def _init_camera_streams(self):
        settings = app_settings()
        try:
            available = {d.description(): d for d in QMediaDevices.videoInputs()}
        except Exception as exc:
            log.warning("Kamera-Geräte konnten nicht abgefragt werden: %s", exc)
            available = {}

        for index, slot in enumerate(self.slots):
            name = settings.value(f"camera_{index + 1}_name", "", type=str)
            if not name or name == "Keine Kamera":
                slot.set_state("empty")
                continue
            device = available.get(name)
            if device is None:
                slot.set_state("missing")
                continue
            try:
                camera = QCamera(device, self)
                session = QMediaCaptureSession(self)
                session.setCamera(camera)
                session.setVideoOutput(slot.video)
                camera.start()
                self._streams[index] = (camera, session)
                slot.set_state("live")
            except Exception as exc:
                log.error("Fehler beim Starten von Kamera %d: %s", index + 1, exc)
                slot.set_state("missing")

        self._check_atem_trigger()

    def _stop_cameras(self):
        for stream in self._streams:
            if stream:
                try:
                    stream[0].stop()
                except Exception:
                    pass

    def update_streams_from_settings(self):
        """Bestehende Kameras stoppen, Vollbildansichten schließen und Streams neu laden."""
        for index in list(self._fullscreen):
            self.close_fullscreen(index)
        self._stop_cameras()
        for stream in self._streams:
            if stream:
                for obj in stream:
                    obj.deleteLater()
        self._streams = [None] * self.SLOT_COUNT
        self._init_camera_streams()

    def _check_atem_trigger(self):
        has_camera = any(self._streams)
        if has_camera and not self._atem_active:
            atem.switch("camera")
            self._atem_active = True
        elif not has_camera and self._atem_active:
            atem.switch("default")
            self._atem_active = False

    # ------------------------------------------------------------------
    # Vollbild
    # ------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            for index in list(self._fullscreen):
                self.close_fullscreen(index)
            event.accept()
            return
        super().keyPressEvent(event)

    def toggle_fullscreen(self, index: int):
        if index in self._fullscreen:
            self.close_fullscreen(index)
            return
        slot = self.slots[index]
        if slot.state != "live":
            return

        # Auf dem Beamer ist immer nur eines zu sehen: das andere Kamerabild und alles, was das Hauptfenster
        # dort geöffnet hat (Lied, Bilder-Galerie), wird geschlossen
        for other in list(self._fullscreen):
            self.close_fullscreen(other)
        self.fullscreen_opening.emit()

        screens = QApplication.screens()
        screen_index = app_settings().value("beamer_screen", 0, type=int)
        target = screens[screen_index] if 0 <= screen_index < len(screens) else screens[0]

        fs_win = FullscreenWindow()
        fs_win.setWindowTitle(f"Live Kamera {index + 1} – Vollbild")
        fs_win.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        fs_win.setStyleSheet("background: #000000;")
        fs_win.close_requested.connect(lambda i=index: self.close_fullscreen(i))
        fs_layout = QVBoxLayout(fs_win)
        fs_layout.setContentsMargins(0, 0, 0, 0)

        slot.video.clearMask()
        slot.video.setParent(fs_win)
        fs_layout.addWidget(slot.video)
        slot.video.show()

        fs_win.show()
        if fs_win.windowHandle():
            fs_win.windowHandle().setScreen(target)
        fs_win.setGeometry(target.geometry())
        fs_win.showFullScreen()

        slot.set_state("fullscreen")
        self._fullscreen[index] = fs_win

    def close_fullscreen(self, index: int):
        fs_win = self._fullscreen.pop(index, None)
        if fs_win is None:
            return
        slot = self.slots[index]
        slot.take_video_back()
        fs_win.close()
        fs_win.deleteLater()

    # ------------------------------------------------------------------
    # Beenden
    # ------------------------------------------------------------------
    def fullscreen_indices(self) -> list:
        """Nummern der Kameras, die gerade im Vollbild laufen."""
        return sorted(self._fullscreen)

    def close_all_fullscreen(self) -> bool:
        """Schließt alle Kamera-Vollbilder. ``True``, wenn eines offen war."""
        opened = bool(self._fullscreen)
        for index in list(self._fullscreen):
            self.close_fullscreen(index)
        return opened

    def stop_streams(self):
        for index in list(self._fullscreen):
            self.close_fullscreen(index)
        self._stop_cameras()
        if self._atem_active:
            atem.switch("default")
            self._atem_active = False
