"""Klappbarer Pausentimer-Bereich: Endzeit, Start/Stopp und Ansagen-Text."""
from PyQt6.QtCore import QEvent, QObject, Qt, QTime, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QPlainTextEdit, QTimeEdit, QVBoxLayout,
)

from services.settings import app_settings
from ui import theme as t
from ui import widgets as w

DEFAULT_END_TIME = QTime(11, 30)   # Endzeit der Pause: immer wieder 11:30

ANNOUNCEMENTS = [
    "Heute gemeinsames Mittagessen",
    "06.09. Allianzgebetsstunde",
    "12.09. Brüderstunde 19 Uhr",
]


class PausentimerPanel(QFrame):
    BORDER = 1
    HEADER_HEIGHT = 64
    BOTTOM_PAD = 10
    MAX_LINES = 10
    MAX_CHARS = 47

    start_clicked = pyqtSignal()
    end_time_changed = pyqtSignal(QTime)
    toggled = pyqtSignal(bool)          # True = Ansagen-Feld ist aufgeklappt

    def __init__(self, parent=None):
        super().__init__(parent)
        settings = app_settings()
        self._open = False
        self._running = False

        self.setObjectName("Pausentimer")
        self.setStyleSheet(f"QFrame#Pausentimer {{ border-top: 1px solid {t.BORDER}; }}")
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
        self.title.setToolTip("Klicken: Ansagen ein- oder ausklappen")
        self.title.clicked.connect(self.toggle)
        header.addWidget(self.title, 1)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setButtonSymbols(QTimeEdit.ButtonSymbols.NoButtons)
        self.time_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_edit.setFixedSize(72, t.BTN)
        self.time_edit.setToolTip("Endzeit der Pause (Uhrzeit ändern)")
        self.time_edit.setTime(DEFAULT_END_TIME)   # beginnt bei jedem Programmstart wieder mit 11:30
        self.time_edit.setStyleSheet(
            t.input_style("QTimeEdit", "0 8px", color=t.ACCENT, weight=600)
        )
        self.time_edit.timeChanged.connect(self._on_time_changed)
        header.addWidget(self.time_edit, 0, vcenter)

        self.start_btn = w.icon_button(w.ICON_PLAY, t.ACCENT_LIGHT, 16, "Pausentimer starten")
        self.start_btn.clicked.connect(self.start_clicked)
        header.addWidget(self.start_btn, 0, vcenter)

        self.chevron = w.ClickableLabel()
        self.chevron.setStyleSheet("border: 0;")
        self.chevron.setToolTip("Ansagen ein- oder ausklappen")
        self.chevron.clicked.connect(self.toggle)
        header.addWidget(self.chevron, 0, vcenter)
        layout.addLayout(header)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(
            f"Ansagen (max. {self.MAX_LINES} Zeilen / {self.MAX_CHARS} Zeichen)"
        )
        font = t.body_font()
        font.setPixelSize(t.FS_SMALL)
        self.text_edit.setFont(font)
        self.text_edit.setToolTip("Ansagen für die Pausenfolie – eine Zeile pro Ansage")
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit.document().setDocumentMargin(0)
        self.text_edit.installEventFilter(self)

        self.text_height = self.MAX_LINES * QFontMetrics(font).lineSpacing() + 2 * 8 + 2 + 2
        self.text_edit.setFixedHeight(self.text_height)

        saved_text = str(settings.value("pause_text", "\n".join(ANNOUNCEMENTS)))
        self.text_edit.setPlainText(self._clamp(saved_text))
        self.text_edit.setStyleSheet(
            t.input_style("QPlainTextEdit", "8px 12px", color=t.TEXT_SECONDARY, font_size=t.FS_SMALL)
            + " QPlainTextEdit { letter-spacing: 0.5px; line-height: 85%; }"
        )
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.text_edit.setVisible(False)
        layout.addWidget(self.text_edit)

        self._update_chevron()

    # ------------------------------------------------------------------
    # Größen (für das Hauptfenster)
    # ------------------------------------------------------------------
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
        self.start_btn.setToolTip("Präsentation schließen" if running else "Pausentimer starten")
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
        lines = text.split("\n")[: self.MAX_LINES]
        return "\n".join(line[: self.MAX_CHARS] for line in lines)

    def _on_time_changed(self, time: QTime) -> None:
        self.end_time_changed.emit(time)

    def _on_text_changed(self) -> None:
        text = self.text_edit.toPlainText()
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
        if obj is self.text_edit and event.type() == QEvent.Type.KeyPress:
            cursor = self.text_edit.textCursor()
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if (self.text_edit.document().blockCount() >= self.MAX_LINES
                        and not cursor.hasSelection()):
                    return True
            else:
                mods = event.modifiers()
                shortcut = bool(mods & (Qt.KeyboardModifier.ControlModifier
                                        | Qt.KeyboardModifier.MetaModifier))
                text = event.text()
                if (text and text.isprintable() and not shortcut
                        and len(cursor.block().text()) >= self.MAX_CHARS
                        and not cursor.hasSelection()):
                    return True
        return super().eventFilter(obj, event)
