"""Abspiel-Leiste: Play/Pause, Titelname, Fortschrittsbalken, Stopp."""
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui import theme as t
from ui import widgets as w


class PlayerPanel(QFrame):
    toggle_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    seek_requested = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PlayerPanel")
        self.setStyleSheet(t.panel_style("PlayerPanel"))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)       # 58 − 2 (Rahmen) − 12 = 44 = Knopfhöhe: Knöpfe exakt mittig
        layout.setSpacing(t.GAP)
        vcenter = Qt.AlignmentFlag.AlignVCenter

        self.play_pause_btn = QPushButton()
        self.play_pause_btn.setFixedSize(t.BTN, t.BTN)
        self.play_pause_btn.setIconSize(QSize(18, 18))
        self.play_pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_pause_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.play_pause_btn.setStyleSheet(t.round_button_style())
        self.play_pause_btn.clicked.connect(self.toggle_requested)
        layout.addWidget(self.play_pause_btn, 0, vcenter)
        self.set_playing(False)

        column = QVBoxLayout()
        column.setSpacing(8)
        self.track_name_label = QLabel("")
        self.track_name_label.setStyleSheet(
            f"font-size: {t.FS_SMALL}px; font-weight: 500; color: {t.TRACK_NAME_COLOR};"
        )
        self.progress_track = w.ProgressTrack()
        self.progress_track.seek_requested.connect(self.seek_requested)
        self.progress_track.setToolTip("Klicken oder ziehen zum Vor- und Zurückspulen")
        self.track_name_label.setToolTip("Aktuell abgespielte Audiodatei")
        column.addWidget(self.track_name_label)
        column.addWidget(self.progress_track)
        layout.addLayout(column, 1)

        stop_btn = w.icon_button(w.ICON_STOP, t.ACCENT_LIGHT, 14, "Wiedergabe beenden")
        stop_btn.clicked.connect(self.stop_requested)
        layout.addWidget(stop_btn, 0, vcenter)

    def set_track_name(self, text: str) -> None:
        self.track_name_label.setText(text)

    def set_playing(self, playing: bool) -> None:
        svg = w.ICON_PAUSE if playing else w.ICON_PLAY
        self.play_pause_btn.setIcon(w.themed_icon(svg, t.ACCENT_LIGHT, 18))
        self.play_pause_btn.setToolTip("Pause" if playing else "Wiedergabe")

    def set_progress(self, percent: float) -> None:
        self.progress_track.set_progress(percent)
