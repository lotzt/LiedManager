"""Klappbarer Pausentimer-Bereich: Endzeit, Start/Stopp und Ansagen-Text."""
import sys

from PyQt6.QtCore import QEvent, QObject, Qt, QTime, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics, QFontMetricsF
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QPlainTextEdit, QTimeEdit, QVBoxLayout,
)

from services.settings import app_settings
from ui import theme as t
from ui import widgets as w

DEFAULT_END_TIME = QTime(11, 30)   # Endzeit der Pause: immer wieder 11:30



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

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setButtonSymbols(QTimeEdit.ButtonSymbols.NoButtons)
        self.time_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_edit.setToolTip("Ende der Pause")
        self.time_edit.setTime(DEFAULT_END_TIME)   # beginnt bei jedem Programmstart wieder mit 11:30
        # Windows reserviert sonst trotz NoButtons Platz für die Pfeile – dann ist im schmalen Feld keine Uhrzeit zu sehen
        self.time_edit.setStyleSheet(
            t.input_style("QTimeEdit", "0 4px", color=t.ACCENT, weight=600)
            + "QTimeEdit::up-button, QTimeEdit::down-button { width: 0px; height: 0px; border: 0; padding: 0; }"
        )
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
        self.text_edit.setStyleSheet(
            t.input_style("QPlainTextEdit", padding, color=t.TEXT_SECONDARY, font_size=font_px))

    def set_box(self, box) -> None:
        """Ansagen-Feld der Pausenfolie übernehmen: Das Eingabefeld bekommt dessen Seitenverhältnis und die Schrift im
        gleichen Maßstab – es passt genau so viel Text hinein wie in das Original-Feld (Zeilen und Breite in der
        gewählten Schriftgröße). ``None``: die festen Grenzen (MAX_LINES Zeilen, MAX_CHARS Zeichen)."""
        self._box = box
        full_w = self._width or self.text_edit.width()
        self.text_edit.setFixedHeight(self.text_height)          # das Feld behält immer seine Größe
        if box is None:
            self.text_edit.setFont(self._default_font)
            self._apply_field_style(self._default_font.pixelSize())
            self.text_edit.setPlaceholderText(f"Ansagen (max. {self.MAX_LINES} Zeilen / {self.MAX_CHARS} Zeichen)")
        else:
            # Nur die Schrift passt sich an – so groß, wie das Feld es hergibt: eine volle Beamer-Zeile füllt genau die
            # Feldbreite, und alle erlaubten Zeilen passen untereinander ins Feld
            avail_w = max(60, full_w - 2 * 8 - 2)
            avail_h = max(40, self.text_height - 2 * 6 - 2)
            font = QFont(box.font)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
            px = max(6, int(box.size * avail_w / box.width))
            font.setPixelSize(px)
            while px > 6 and (box.max_lines * QFontMetrics(font).lineSpacing() > avail_h
                              or QFontMetricsF(font).averageCharWidth() * box.width / box.metrics.averageCharWidth()
                              > avail_w + 0.5):
                px -= 1
                font.setPixelSize(px)
            self.text_edit.setFont(font)
            self._apply_field_style(px, "6px 8px")
            self.text_edit.setPlaceholderText(f"Ansagen (max. {box.max_lines} Zeilen)")
        text = self.text_edit.toPlainText()
        clamped = self._clamp(text)
        if clamped != text:
            self.text_edit.setPlainText(clamped)        # löst _on_text_changed aus (speichert, Beamer aktualisiert sich)
        self._last_text = self.text_edit.toPlainText()

    def max_lines(self) -> int:
        return self._box.max_lines if self._box is not None else self.MAX_LINES

    def collapsed_height(self) -> int:
        return self.BORDER + self.HEADER_HEIGHT

    def open_extra_height(self) -> int:
        return self.text_height

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
