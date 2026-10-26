"""Aufnahme-Leiste: Aufnahmeknopf, Prediger-Feld, Zeit, Pegel, Speichern."""
import math
import time

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from services.recorder import IDLE, PAUSED, REC, AudioRecorder
from ui import theme as t
from ui import widgets as w

REC_ICON = 28
PULSE_PERIOD = 1.6      # Sekunden pro Puls
PULSE_INTERVAL_MS = 50


class RecordingPanel(QFrame):
    def __init__(self, recorder: AudioRecorder, parent=None):
        super().__init__(parent)
        self.recorder = recorder
        self.setObjectName("RecPanel")
        self.setStyleSheet(t.panel_style("RecPanel"))

        layout = QHBoxLayout(self)
        # 58 px Leiste − 2 px Rahmen − 2 × 6 px = genau 44 px (Knopfhöhe): Knöpfe und Mitte sitzen exakt mittig
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(t.GAP)
        vcenter = Qt.AlignmentFlag.AlignVCenter

        self.rec_main_btn = QPushButton()
        self.rec_main_btn.setFixedSize(t.BTN, t.BTN)
        self.rec_main_btn.setIconSize(QSize(REC_ICON, REC_ICON))
        self.rec_main_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rec_main_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.rec_main_btn.clicked.connect(recorder.toggle)
        layout.addWidget(self.rec_main_btn, 0, vcenter)

        middle = QVBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(6)                 # 32 (Prediger) + 6 + 6 (Pegel) = 44 = Knopfhöhe
        row = QHBoxLayout()
        row.setSpacing(8)

        self.preacher_input = QLineEdit()
        self.preacher_input.setPlaceholderText("Prediger")
        self.preacher_input.setFixedHeight(32)
        self.preacher_input.setToolTip("Name des Predigers – steht im Dateinamen der Aufnahme (Datum - Prediger)")
        self.preacher_input.setStyleSheet(
            t.input_style("QLineEdit", "0 10px", background=t.CARD_BG)
        )
        row.addWidget(self.preacher_input, 1)

        self.rec_time_label = QLabel("00:00")
        self.rec_time_label.setMinimumWidth(44)
        self.rec_time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.rec_time_label.setToolTip("Dauer der laufenden Aufnahme")
        row.addWidget(self.rec_time_label)
        middle.addLayout(row)

        self.level_meter = w.LevelMeter()
        self.level_meter.setToolTip("Aussteuerung des Mikrofons (Pegel)")
        middle.addWidget(self.level_meter)
        layout.addLayout(middle, 1)

        self.rec_stop_btn = w.icon_button(w.ICON_CHECK, t.ACCENT_LIGHT, 20, "Aufnahme speichern")
        self.rec_stop_btn.clicked.connect(self.save_recording)
        self._stop_opacity = QGraphicsOpacityEffect(self.rec_stop_btn)
        self.rec_stop_btn.setGraphicsEffect(self._stop_opacity)
        layout.addWidget(self.rec_stop_btn, 0, vcenter)

        self._pulse_step = -1
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(PULSE_INTERVAL_MS)
        self._pulse_timer.timeout.connect(self._pulse)

        recorder.state_changed.connect(self._apply_state)
        recorder.tick.connect(self._on_tick)
        recorder.saved.connect(lambda _path: self.preacher_input.clear())
        self._apply_state(IDLE)

    # ------------------------------------------------------------------
    def save_recording(self) -> None:
        self.recorder.stop_and_save(self.preacher_input.text())

    def _on_tick(self, seconds: float, level: float) -> None:
        mm, ss = divmod(int(seconds), 60)
        self.rec_time_label.setText(f"{mm:02d}:{ss:02d}")
        self.level_meter.set_level(level)

    def _pulse(self) -> None:
        phase = (time.monotonic() % PULSE_PERIOD) / PULSE_PERIOD
        intensity = 0.65 + 0.35 * (0.5 + 0.5 * math.sin(phase * 2 * math.pi - math.pi / 2))
        icon = w.make_rec_dot_icon("rec", REC_ICON, intensity)
        step = round(intensity * w.REC_PULSE_STEPS)
        if step != self._pulse_step:  # nur neu setzen, wenn sich die Leuchtstufe wirklich ändert
            self._pulse_step = step
            self.rec_main_btn.setIcon(icon)

    def _apply_state(self, state: str) -> None:
        running = state == REC
        self._pulse_step = -1
        self.rec_main_btn.setIcon(w.make_rec_dot_icon(state, REC_ICON))
        if running:
            self._pulse_timer.start()
            self.rec_main_btn.setStyleSheet(t.round_button_style(
                background=t.REC_RUNNING_BG, border=t.ACCENT, hover_border=t.REC_RED,
            ))
        else:
            self._pulse_timer.stop()
            self.rec_main_btn.setStyleSheet(t.round_button_style())
        self.rec_main_btn.setToolTip({
            IDLE: "Aufnahme starten",
            REC: "Aufnahme pausieren",
            PAUSED: "Aufnahme fortsetzen",
        }[state])

        color = t.REC_TIME_RUNNING if running else t.TEXT_MUTED
        self.rec_time_label.setStyleSheet(f"font-size: {t.FS}px; font-weight: 600; color: {color};")
        if state == IDLE:
            self.rec_time_label.setText("00:00")

        active = state != IDLE
        self.rec_stop_btn.setEnabled(active)
        self._stop_opacity.setOpacity(1.0 if active else 0.35)
