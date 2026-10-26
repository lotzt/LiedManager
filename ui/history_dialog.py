"""Fenster „Liedhistorie“: gespielte Lieder nach Tag, mit Suche und den am häufigsten gespielten Liedern."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout

from services import history
from ui import theme as t


class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Liedhistorie")
        self.resize(520, 560)
        self._days = history.read()
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Suche nach Nummer, Titel oder Datum")
        self.search.textChanged.connect(self._fill)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.top_label = QLabel()
        self.top_label.setWordWrap(True)
        self.top_label.setStyleSheet(t.hint_style())
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.top_label)
        self._fill()
        self._show_top()

    def _fill(self, *_args) -> None:
        self.tree.clear()
        days = history.filter_days(self._days, self.search.text())
        for header, _day, entries in days:
            top = QTreeWidgetItem([f"{header}  ({len(entries)})"])
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            self.tree.addTopLevelItem(top)
            for number, title in entries:
                child = QTreeWidgetItem([f"{number} – {title}" if title else number])
                child.setFlags(child.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                top.addChild(child)
            top.setExpanded(bool(self.search.text().strip()) or self.tree.topLevelItemCount() <= 3)
        if not days:
            self.tree.addTopLevelItem(QTreeWidgetItem(["Noch keine Lieder in der Liste."]))

    def _show_top(self) -> None:
        top = history.top_songs(self._days, 5)
        if top:
            self.top_label.setText("Am häufigsten: " + " · ".join(f"{nr} {title} ({n}×)".replace("  ", " ")
                                                                   for nr, title, n in top))
