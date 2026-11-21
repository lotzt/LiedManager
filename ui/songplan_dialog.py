"""Fenster „Vorgemerkte Lieder“: die Liste bearbeiten (eine Liednummer pro Zeile) und darunter sehen, welche Lieder
das sind. Steht in einer Zeile nur ein Buchstabe (z. B. „p“), zeigt die Liste darunter alle Nummern damit zur Auswahl.

Gleiche Liste wie auf der Website (``services/songplan.py``): die Lieder kommen nacheinander in die Suchzeile und
fallen erst heraus, wenn sie auf dem Beamer waren.
"""
import re

from PyQt6.QtCore import QEvent, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QTextCursor
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                             QVBoxLayout)

from services import songplan
from ui import theme as t
from ui import widgets as w

ICON_LIST = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
  stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M9 6h11M9 12h11M9 18h11"></path><circle cx="4.5" cy="6" r="1"></circle>
  <circle cx="4.5" cy="12" r="1"></circle><circle cx="4.5" cy="18" r="1"></circle>
</svg>"""

_LETTER = re.compile(r"^[A-Za-z]$")


def plan_icon(count: int, size: int = 18) -> QIcon:
    """Listen-Symbol für die Suchzeile; mit Anzahl der vorgemerkten Lieder als kleine Plakette."""
    base = w.themed_icon(ICON_LIST, t.ACCENT_LIGHT if count else t.TEXT_MUTED, size)
    if not count:
        return base
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.drawPixmap(0, 0, base.pixmap(size * scale, size * scale))
    text = str(count) if count < 10 else "9+"
    badge = QRectF(size * scale * 0.42, size * scale * 0.42, size * scale * 0.58, size * scale * 0.58)
    painter.setPen(QColor(t.CARD_BG))
    painter.setBrush(QColor(t.ACCENT))
    painter.drawEllipse(badge)
    font = QFont()
    font.setPixelSize(int(size * scale * 0.42))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#1A1210"))
    painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)


def plan_tooltip(count: int) -> str:
    if not count:
        return "Vorgemerkte Lieder – keine. Klicken: Liste bearbeiten"
    return (f"Vorgemerkte Lieder: {count} – sie kommen nacheinander in die Suchzeile.\n"
            "Klicken: Liste ansehen und bearbeiten")


class SongPlanDialog(QDialog):
    """Bearbeiten speichert sofort (kurz verzögert); ``changed`` meldet es dem Hauptfenster."""
    changed = pyqtSignal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Vorgemerkte Lieder")
        self.resize(440, 560)
        self._letter_block = -1            # Zeile, deren Buchstabe gerade durch eine Nummer ersetzt werden kann

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        info = QLabel(
            "Die Lieder kommen der Reihe nach in die Suchzeile – zweimal Enter zeigt das Lied auf dem Beamer. "
            "Ein Lied fällt erst aus der Liste, wenn es auf dem Beamer war; nur Nachschauen zählt nicht. "
            "Die Liste lässt sich auch auf der Website bearbeiten.")
        info.setWordWrap(True)
        info.setStyleSheet(t.hint_style())
        layout.addWidget(info)

        caption = QLabel("Liednummern – eine pro Zeile")
        caption.setStyleSheet(t.caption_style())
        layout.addWidget(caption)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("z. B.\np012\n45\n\nNur ein Buchstabe (z. B. „p“) zeigt alle Nummern damit.")
        self.edit.setTabChangesFocus(True)
        self.edit.setPlainText("\n".join(songplan.get()))
        self.edit.setStyleSheet(t.input_style("QPlainTextEdit", "6px 10px"))
        self.edit.installEventFilter(self)
        layout.addWidget(self.edit, 2)

        self.list_caption = QLabel()
        self.list_caption.setStyleSheet(t.caption_style())
        layout.addWidget(self.list_caption)
        self.list = QListWidget()
        self.list.setStyleSheet(t.list_style())
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.itemActivated.connect(self._pick)
        self.list.itemDoubleClicked.connect(self._pick)
        layout.addWidget(self.list, 3)

        buttons = QHBoxLayout()
        clear = QPushButton("Liste leeren")
        clear.setStyleSheet(t.pill_button_style())
        clear.clicked.connect(lambda: self.edit.setPlainText(""))
        done = QPushButton("Fertig")
        done.setStyleSheet(t.pill_button_style())
        done.setDefault(True)
        done.clicked.connect(self.accept)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        buttons.addWidget(done)
        layout.addLayout(buttons)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save)
        self.edit.textChanged.connect(self._save_timer.start)
        self.edit.textChanged.connect(self._update_list)
        self.edit.cursorPositionChanged.connect(self._update_list)
        self._update_list()

    # ------------------------------------------------------------------
    def _lines(self) -> list:
        return [line.strip() for line in self.edit.toPlainText().split("\n") if line.strip()]

    def _save(self) -> None:
        songs = [line for line in self._lines() if not _LETTER.match(line)]    # halbfertige Buchstaben nicht speichern
        if songs != songplan.get():
            songplan.set_songs(songs)
            self.changed.emit()

    def _title(self, number: str) -> str:
        songs = self.db.search_songs(number) if self.db is not None else []
        if len(songs) == 1:
            song = songs[0]
            title = song.titel if song.titel and song.titel != "None" else ""
            return f"Nr. {song.nummer}" + (f" – {title}" if title else "")
        return f"{number} – nicht gefunden" if not songs else f"{number} – keine eindeutige Nummer"

    def _update_list(self) -> None:
        block = self.edit.textCursor().block()
        text = block.text().strip()
        self.list.clear()
        if _LETTER.match(text):
            self._letter_block = block.blockNumber()
            songs = self.db.search_songs(text) if self.db is not None else []
            self.list_caption.setText(f"Alle Nummern mit „{text}“ – Doppelklick oder Enter übernimmt"
                                      if songs else f"Keine Nummern mit „{text}“")
            for song in songs:
                title = song.titel if song.titel and song.titel != "None" else ""
                item = QListWidgetItem(f"Nr. {song.nummer}" + (f" – {title}" if title else ""))
                item.setData(Qt.ItemDataRole.UserRole, str(song.nummer))
                self.list.addItem(item)
            return
        self._letter_block = -1
        lines = [line for line in self._lines() if not _LETTER.match(line)]
        self.list_caption.setText("Reihenfolge" if lines else "Noch keine Lieder vorgemerkt")
        for position, number in enumerate(lines, 1):
            item = QListWidgetItem(f"{position}.  {self._title(number)}")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.list.addItem(item)

    def _pick(self, item) -> None:
        number = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        block = self.edit.document().findBlockByNumber(self._letter_block)
        if not number or not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(number)
        self.edit.setTextCursor(cursor)
        self.edit.setFocus()

    def eventFilter(self, obj, event):
        # Pfeil runter im Textfeld springt in die Auswahl, solange dort Nummern zu einem Buchstaben stehen
        if (obj is self.edit and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Down
                and self._letter_block >= 0 and self.list.count()):
            self.list.setFocus()
            self.list.setCurrentRow(0)
            return True
        return super().eventFilter(obj, event)

    def done(self, result) -> None:
        self._save_timer.stop()
        self._save()
        super().done(result)
