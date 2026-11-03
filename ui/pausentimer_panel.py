"""Klappbarer Pausentimer-Bereich: Endzeit, Start/Stopp und Ansagen-Text."""
import math
import re
import sys

from PyQt6.QtCore import QEvent, QObject, Qt, QTime, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics, QFontMetricsF
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout,
)

from services.settings import app_settings
from ui import theme as t
from ui import widgets as w

DEFAULT_END_TIME = QTime(11, 30)   # Endzeit der Pause: immer wieder 11:30



class TimeField(QLineEdit):
    """Uhrzeit-Feld „HH:mm“ – ein einfaches Textfeld statt QTimeEdit: QTimeEdit zeigte unter Windows (mit eigenem Stil
    und ohne Pfeile) im schmalen Feld gar keine Uhrzeit. Pfeiltasten/Mausrad: Stunde bzw. Minute (je nach Cursor) ±1."""
    timeChanged = pyqtSignal(QTime)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._time = QTime(0, 0)
        self.setInputMask("99:99")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.textEdited.connect(self._on_edited)
        self.editingFinished.connect(lambda: self.setText(self._time.toString("HH:mm")))

    def time(self) -> QTime:
        return QTime(self._time)

    def setTime(self, value: QTime) -> None:
        value = QTime(value.hour(), value.minute())
        changed = value != self._time
        self._time = value
        if self.text() != value.toString("HH:mm"):
            position = self.cursorPosition()
            self.setText(value.toString("HH:mm"))
            self.setCursorPosition(position)
        if changed:
            self.timeChanged.emit(QTime(value))

    def _on_edited(self, text: str) -> None:
        hours, _, minutes = text.partition(":")
        if len(hours.strip()) == 2 and len(minutes.strip()) == 2:
            value = QTime(int(hours), int(minutes))
            if value.isValid():
                self.setTime(value)

    def _step(self, steps: int) -> None:
        if self.cursorPosition() <= 2:
            self.setTime(self._time.addSecs(steps * 3600))
        else:
            self.setTime(self._time.addSecs(steps * 60))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._step(1 if event.key() == Qt.Key.Key_Up else -1)
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self._step(1 if delta > 0 else -1)
        event.accept()


class PausentimerPanel(QFrame):
    BORDER = 1
    HEADER_HEIGHT = 64
    BOTTOM_PAD = 10
    MAX_LINES = 11
    MAX_CHARS = 50
    # Windows zeichnet dieselbe Pixelgröße deutlich zierlicher als macOS – dort eine Stufe größer
    FONT_PX = 12 if sys.platform.startswith("win") else 11
    # So breit ist eine typische, volle Ansage (50 Zeichen). Ziffernreihen wie „0000…“ sind breiter als echter Text;
    # an ihnen gemessen würde die Schrift unnötig klein.
    FIT_SAMPLE = "Gemeindeversammlung am 12.09. um 19:30 Uhr im Saal"
    LETTER_SPACING = 0.3

    start_clicked = pyqtSignal()
    end_time_changed = pyqtSignal(QTime)
    toggled = pyqtSignal(bool)          # True = Ansagen-Feld ist aufgeklappt

    def __init__(self, width: int = 0, parent=None):
        super().__init__(parent)
        settings = app_settings()
        self._open = False
        self._running = False
        self._box = None              # Ansagen-Feld der Vorlage (pause_window.AnnouncementBox) oder None
        self._width = width

        self.setObjectName("Pausentimer")
        self.setStyleSheet(f"QFrame#Pausentimer {{ background: transparent; border: 0; border-top: 1px solid {t.BORDER}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(t.GAP)
        vcenter = Qt.AlignmentFlag.AlignVCenter

        self.title = w.ClickableLabel("Pausentimer")
        self.title.setFixedHeight(self.HEADER_HEIGHT)
        self.title.setStyleSheet(
            f"font-size: {t.FS}px; font-weight: 500; color: {t.TEXT_LABEL}; border: 0;"
        )
        self.title.setToolTip("Ansagen ein-/ausklappen")
        self.title.clicked.connect(self.toggle)
        header.addWidget(self.title, 1)

        self.time_edit = TimeField()
        self.time_edit.setToolTip("Ende der Pause")
        self.time_edit.setTime(DEFAULT_END_TIME)   # beginnt bei jedem Programmstart wieder mit 11:30
        self.time_edit.setStyleSheet(t.input_style("QLineEdit", "0 4px", color=t.ACCENT, weight=600))
        time_font = QFont(self.time_edit.font())
        time_font.setPixelSize(t.FS)
        time_font.setWeight(QFont.Weight.DemiBold)
        self.time_edit.setFont(time_font)
        need = QFontMetrics(time_font).horizontalAdvance("00:00") + 8 + 2 + 18      # Innenabstand, Rahmen, Luft
        self.time_edit.setFixedSize(max(72, need), t.BTN)
        self.time_edit.timeChanged.connect(self._on_time_changed)
        header.addWidget(self.time_edit, 0, vcenter)

        self.start_btn = w.icon_button(w.ICON_PLAY, t.ACCENT_LIGHT, 16, "Pausentimer starten")
        self.start_btn.clicked.connect(self.start_clicked)
        header.addWidget(self.start_btn, 0, vcenter)

        self.chevron = w.ClickableLabel()
        self.chevron.setStyleSheet("border: 0;")
        self.chevron.setToolTip("Ansagen ein-/ausklappen")
        self.chevron.clicked.connect(self.toggle)
        header.addWidget(self.chevron, 0, vcenter)
        layout.addLayout(header)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(
            f"Ansagen (max. {self.MAX_LINES} Zeilen / {self.MAX_CHARS} Zeichen)"
        )
        font = t.body_font()
        font.setPixelSize(self.FONT_PX)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.LETTER_SPACING)
        # Windows rundet Zeichenbreiten sonst auf ganze Pixel – dann passten keine 50 Zeichen und die Schrift wurde kleiner
        # als auf dem Mac. Ohne Hinting gelten (wie am Mac) die echten Breiten.
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        # Erst den Zeichenabstand verringern, erst danach (falls nötig) die Schrift, damit MAX_CHARS Zeichen in eine Zeile passen
        inner = width - 2 * 12 - 2 if width else 0
        sample = self.FIT_SAMPLE

        def too_wide() -> bool:
            return bool(inner) and QFontMetricsF(font).horizontalAdvance(sample) > inner

        if too_wide():
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        while too_wide() and font.pixelSize() > 9:
            font.setPixelSize(font.pixelSize() - 1)
        self.text_edit.setFont(font)
        self._default_font = QFont(font)
        self.text_edit.setToolTip("Eine Zeile pro Ansage")
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit.document().setDocumentMargin(0)
        self.text_edit.installEventFilter(self)
        self.text_edit.viewport().installEventFilter(self)
        for bar in (self.text_edit.verticalScrollBar(), self.text_edit.horizontalScrollBar()):
            bar.rangeChanged.connect(lambda *_a, b=bar: b.setValue(0))

        self.text_height = self.MAX_LINES * QFontMetrics(font).lineSpacing() + 2 * 8 + 2 + 2 + 14   # 14 = Luft, damit nie gescrollt wird
        self.text_edit.setFixedHeight(self.text_height)

        saved_text = str(settings.value("pause_text", ""))          # keine vorausgefüllten Ansagen
        self.text_edit.setPlainText(self._clamp(saved_text))
        self._last_text = self.text_edit.toPlainText()
        self._apply_field_style(font.pixelSize())
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.text_edit.setVisible(False)
        layout.addWidget(self.text_edit)

        self._update_chevron()

    # ------------------------------------------------------------------
    # Größen (für das Hauptfenster)
    # ------------------------------------------------------------------
    def _apply_field_style(self, font_px: int, padding: str = "8px 12px") -> None:
        """``font_px`` 0: keine Schriftgröße im Stil – dann gilt die (stufenlose) Schrift des Felds."""
        style = t.input_style("QPlainTextEdit", padding, color=t.TEXT_SECONDARY, font_size=font_px or t.FS)
        if not font_px:
            style = re.sub(r"font-size:\s*[0-9.]+px;", "", style)
        self.text_edit.setStyleSheet(style)

    def set_box(self, box) -> None:
        """Ansagen-Feld der Pausenfolie übernehmen: Das Eingabefeld bekommt dessen Seitenverhältnis und die Schrift im
        gleichen Maßstab – es passt genau so viel Text hinein wie in das Original-Feld (Zeilen und Breite in der
        gewählten Schriftgröße). ``None``: die festen Grenzen (MAX_LINES Zeilen, MAX_CHARS Zeichen)."""
        self._box = box
        self.field_height = self.text_height
        self.text_edit.setFixedHeight(self.text_height)
        if box is None:
            self.text_edit.setFont(self._default_font)
            self._apply_field_style(self._default_font.pixelSize())
            self.text_edit.setPlaceholderText(f"Ansagen (max. {self.MAX_LINES} Zeilen / {self.MAX_CHARS} Zeichen)")
        else:
            self._box_font_px = None
            self._fit_box_font()             # Feld in den Proportionen der Vorlage, Schrift im selben Maßstab
            self.text_edit.setPlaceholderText(f"Ansagen (max. {box.max_lines} Zeilen)")
        text = self.text_edit.toPlainText()
        clamped = self._clamp(text)
        if clamped != text:
            self.text_edit.setPlainText(clamped)        # löst _on_text_changed aus (speichert, Beamer aktualisiert sich)
        self._last_text = self.text_edit.toPlainText()

    PAD_X, PAD_Y = 12, 8                 # Innenabstand des Ansagen-Felds (links = rechts)

    def _fit_box_font(self) -> None:
        """Volle Breite: Die Schrift wird stufenlos so skaliert, dass eine volle Beamer-Zeile genau bis zum rechten Rand
        reicht (links und rechts gleicher Abstand). Die Höhe reicht genau für alle erlaubten Zeilen."""
        box = self._box
        if box is None:
            return
        inner_w = max(60, (self._width or self.text_edit.width()) - 2 * self.PAD_X - 2)
        max_inner_h = max(40, 3 * self.text_height - 2 * self.PAD_Y - 2)   # nur extrem hohe Felder werden verkleinert
        font = QFont(box.font)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)   # Breiten wachsen genau mit der Größe
        sample = self.FIT_SAMPLE + " 0123456789"
        beamer = max(1.0, box.metrics.horizontalAdvance(sample))
        target = inner_w / box.width * 0.995                # Beamer-Breite -> Feldbreite (minimal Luft gegen Rundung)
        size = 10.0
        font.setPointSizeF(size)
        for _ in range(4):                                  # stufenlos (Bruchteile von Punkten) statt ganzer Pixel
            size *= beamer * target / max(1.0, QFontMetricsF(font).horizontalAdvance(sample))
            font.setPointSizeF(max(4.0, size))
        while size > 4.0 and box.max_lines * QFontMetricsF(font).lineSpacing() > max_inner_h:
            size *= 0.97
            font.setPointSizeF(size)
        used_w = QFontMetricsF(font).horizontalAdvance(sample) / beamer * box.width
        extra_x = max(0, int((inner_w - used_w) / 2))
        self.text_edit.setFont(font)
        self._apply_field_style(0, f"{self.PAD_Y}px {self.PAD_X + extra_x}px")
        # Qt setzt jede Zeile auf ganze Pixel (aufgerundet) – dazu etwas Luft, damit die letzte Zeile nie angeschnitten wird
        line = math.ceil(QFontMetricsF(font).lineSpacing())
        inner_h = box.max_lines * line + math.ceil(line * 0.5)
        self.field_height = inner_h + 2 * self.PAD_Y + 2 + 4
        self.text_edit.setFixedHeight(self.field_height)

    def max_lines(self) -> int:
        return self._box.max_lines if self._box is not None else self.MAX_LINES

    def collapsed_height(self) -> int:
        return self.BORDER + self.HEADER_HEIGHT

    def open_extra_height(self) -> int:
        return getattr(self, "field_height", self.text_height)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def lines(self):
        return self.text_edit.toPlainText().splitlines()

    def end_time(self) -> QTime:
        return self.time_edit.time()

    def set_running(self, running: bool) -> None:
        self._running = running
        svg = w.ICON_STOP if running else w.ICON_PLAY
        self.start_btn.setIcon(w.themed_icon(svg, t.ACCENT_LIGHT, 16))
        self.start_btn.setToolTip("Pausentimer beenden" if running else "Pausentimer starten")
        if not running:  # nach jeder Pause geht es wieder mit 11:30 los
            self.time_edit.setTime(DEFAULT_END_TIME)

    def toggle(self) -> None:
        self._open = not self._open
        self.text_edit.setVisible(self._open)
        self._update_chevron()
        self.toggled.emit(self._open)

    def is_open(self) -> bool:
        return self._open

    # ------------------------------------------------------------------
    # Intern
    # ------------------------------------------------------------------
    def _update_chevron(self) -> None:
        svg = w.ICON_CHEVRON_UP if self._open else w.ICON_CHEVRON_DOWN
        self.chevron.setPixmap(w.themed_icon(svg, t.TEXT_MUTED, 16).pixmap(16, 16))

    def _clamp(self, text: str) -> str:
        lines = text.split("\n")[: self.max_lines()]
        if self._box is None:
            return "\n".join(line[: self.MAX_CHARS] for line in lines)
        fitted = []
        for line in lines:
            while line and not self._box.line_fits(line):
                line = line[:-1]
            fitted.append(line)
        return "\n".join(fitted)

    def _on_time_changed(self, time: QTime) -> None:
        self.end_time_changed.emit(time)

    def _on_text_changed(self) -> None:
        text = self.text_edit.toPlainText()
        if self._box is not None:
            if not self._box.fits(text):                   # passt nicht mehr ins Original-Feld: Eingabe zurücknehmen
                cursor = self.text_edit.textCursor()
                pos = cursor.position() - (len(text) - len(self._last_text))
                self.text_edit.blockSignals(True)
                self.text_edit.setPlainText(self._last_text if self._box.fits(self._last_text) else self._clamp(text))
                cursor.setPosition(max(0, min(pos, len(self.text_edit.toPlainText()))))
                self.text_edit.setTextCursor(cursor)
                self.text_edit.blockSignals(False)
            self._last_text = self.text_edit.toPlainText()
            app_settings().setValue("pause_text", self._last_text)
            return
        lines = text.split("\n")
        if len(lines) > self.MAX_LINES or any(len(line) > self.MAX_CHARS for line in lines):
            cursor = self.text_edit.textCursor()
            pos = cursor.position()
            new_text = self._clamp(text)
            self.text_edit.blockSignals(True)
            self.text_edit.setPlainText(new_text)
            cursor.setPosition(min(pos, len(new_text)))
            self.text_edit.setTextCursor(cursor)
            self.text_edit.blockSignals(False)
        app_settings().setValue("pause_text", self.text_edit.toPlainText())

    def eventFilter(self, obj: QObject, event) -> bool:
        """Verhindert schon beim Tippen mehr als MAX_LINES Zeilen bzw. MAX_CHARS Zeichen pro Zeile."""
        if obj in (self.text_edit, self.text_edit.viewport()) and event.type() == QEvent.Type.Wheel:
            return True                                    # Feld wird nicht gescrollt
        if obj is self.text_edit and event.type() == QEvent.Type.KeyPress:
            cursor = self.text_edit.textCursor()
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if (self.text_edit.document().blockCount() >= self.max_lines()
                        and not cursor.hasSelection()):
                    return True
            else:
                mods = event.modifiers()
                shortcut = bool(mods & (Qt.KeyboardModifier.ControlModifier
                                        | Qt.KeyboardModifier.MetaModifier))
                text = event.text()
                if (self._box is None and text and text.isprintable() and not shortcut
                        and len(cursor.block().text()) >= self.MAX_CHARS
                        and not cursor.hasSelection()):
                    return True
        return super().eventFilter(obj, event)
