"""Bausteine des Einstellungsdialogs: Felder, Karten, Seiten und Unter-Reiter im Stil des Hauptfensters."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from ui import theme as t
from ui.widgets import round_combo_popup

FIELD_H = 40
CARD_PAD = 18
CARD_GAP = 16


class FormBuilder:
    """Teil von ``SettingsDialog`` (Mixin): baut die Karten dieses Reiters und reagiert auf seine Felder."""

    @staticmethod
    def _field(caption: str, widget: QWidget, hint: str = "") -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(caption)
        label.setStyleSheet(t.caption_style())
        layout.addWidget(label)
        layout.addWidget(widget)
        if hint:
            layout.addSpacing(4)
            hint_label = QLabel(hint)
            hint_label.setWordWrap(True)
            hint_label.setStyleSheet(t.hint_style())
            layout.addWidget(hint_label)
        return box

    @staticmethod
    def _two_fields(*fields: QWidget, equal: bool = False) -> QWidget:
        """Mehrere Felder nebeneinander in einer Zeile (spart Platz); das erste ist etwas breiter.
        ``equal``: alle Felder exakt gleich breit (z. B. Kamera 1/2, Ausgabe/Mikrofon)."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.GAP)
        for index, field in enumerate(fields):
            if equal:
                field.setMinimumWidth(0)
                field.setSizePolicy(QSizePolicy.Policy.Ignored, field.sizePolicy().verticalPolicy())
            layout.addWidget(field, 1 if equal else (3 if index == 0 else 2))
        return row

    @staticmethod
    def _inline(field: QWidget, *widgets: QWidget) -> QWidget:
        """Feld mit Beschriftung und daneben (auf Höhe des Felds) weitere Elemente, z. B. ein Schalter."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.GAP * 2)
        layout.addWidget(field)
        for widget in widgets:
            widget.setFixedHeight(FIELD_H)
            layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addStretch(1)
        return row

    @staticmethod
    def _device_combo() -> QComboBox:
        """Auswahlliste für Geräte: lange Gerätenamen werden gekürzt statt das Feld zu verbreitern."""
        combo = FormBuilder._combo()
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(8)
        combo.setProperty("no_fit", True)
        return combo

    @staticmethod
    def _subtabs(*entries) -> QWidget:
        """Unterteilt eine lange Seite in kleine Unter-Reiter (Name, Karten …)."""
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        row = QHBoxLayout()
        row.setSpacing(6)
        stack = QStackedWidget()
        group = QButtonGroup(box)
        group.setExclusive(True)
        for index, (label, *cards) in enumerate(entries):
            btn = QPushButton(label.replace("&", "&&"))   # „&“ sonst als Tastenkürzel (Unterstrich) gedeutet
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.setAutoDefault(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(t.pill_button_style(radius=15, font_size=12) + "QPushButton { padding: 0 12px; }")
            group.addButton(btn, index)
            row.addWidget(btn)
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(14)
            for card in cards:
                page_layout.addWidget(card)
            page_layout.addStretch()
            stack.addWidget(page)
        row.addStretch()
        group.idClicked.connect(stack.setCurrentIndex)
        group.button(0).setChecked(True)
        box.subtab_group = group                   # für Tests
        layout.addLayout(row)
        layout.addWidget(stack)
        return box

    @staticmethod
    def _info_button(text: str) -> QToolButton:
        """Kleiner „i“-Knopf: die Erklärung erscheint beim Darüberfahren (statt als Text im Dialog)."""
        button = QToolButton()
        button.setText("i")
        button.setFixedSize(20, 20)
        button.setCursor(Qt.CursorShape.WhatsThisCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip(text)
        button.setStyleSheet(
            f"QToolButton {{ border: 1px solid {t.BORDER}; border-radius: 10px; background: transparent; "
            f"color: {t.TEXT_MUTED}; font-size: 11px; font-weight: 700; }}"
            f"QToolButton:hover {{ border-color: {t.ACCENT}; color: {t.ACCENT_LIGHT}; }}")
        return button

    @classmethod
    def _card(cls, *items, title: str = "", info: str = "") -> QFrame:
        """Rahmen mit einfacher Überschrift; längere Erklärungen stehen im „i“-Knopf (Hover)."""
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(CARD_PAD, CARD_PAD, CARD_PAD, CARD_PAD)
        layout.setSpacing(CARD_GAP)
        if title:
            header = QHBoxLayout()
            header.setSpacing(8)
            heading = QLabel(title)
            heading.setStyleSheet(f"font-size: {t.FS + 2}px; font-weight: 700; color: {t.TEXT_PRIMARY}; "
                                  "background: transparent; border: 0;")
            header.addWidget(heading)
            header.addStretch()
            if info:
                header.addWidget(cls._info_button(info))
            layout.addLayout(header)
        for item in items:
            if isinstance(item, QWidget):
                layout.addWidget(item)
            else:
                layout.addLayout(item)
        return card

    @staticmethod
    def _page(*cards) -> QWidget:
        """Eine Seite des Dialogs. Sie liegt in einer Bildlauf-Fläche: Reicht der Platz nicht (lange Hinweistexte,
        kleiner Bildschirm), wird gescrollt, statt Felder oder Text abzuschneiden."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 4)
        layout.setSpacing(14)
        for card in cards:
            layout.addWidget(card)
        layout.addStretch()
        page.setAutoFillBackground(False)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }"
                             "QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(page)
        return scroll

    @staticmethod
    def _combo() -> QComboBox:
        combo = QComboBox()
        combo.setFixedHeight(FIELD_H)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.setStyleSheet(t.combo_style())
        round_combo_popup(combo)  # aufklappende Liste mit runden Ecken
        return combo

    @staticmethod
    def _line_edit(placeholder: str = "") -> QLineEdit:
        edit = QLineEdit()
        edit.setFixedHeight(FIELD_H)
        edit.setPlaceholderText(placeholder)
        edit.setStyleSheet(t.input_style("QLineEdit", "0 12px"))
        return edit

    @staticmethod
    def _checkbox(text: str) -> QCheckBox:
        box = QCheckBox(text)
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        box.setStyleSheet(t.checkbox_style())
        return box

    @staticmethod
    def _spinbox(low: int = 1, high: int = 20) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setFixedSize(92, FIELD_H)            # wird nach dem Aufbau an den Inhalt angepasst (siehe _fit_fields)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setStyleSheet(t.spinbox_style())
        return spin

    @staticmethod
    def _outline_button(text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(FIELD_H)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoDefault(False)
        btn.setStyleSheet(t.pill_button_style(radius=t.RADIUS))
        return btn

    @staticmethod
    def _select_data(combo: QComboBox, key):
        index = combo.findData(key)
        if index >= 0:
            combo.setCurrentIndex(index)
