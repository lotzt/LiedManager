"""Reiter „Mischpult“: ATEM-Videomischer und Behringer X AIR."""
import threading

from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from services import atem
from ui import theme as t


class MixerTab:
    """Teil von ``SettingsDialog`` (Mixin): baut die Karten dieses Reiters und reagiert auf seine Felder."""

    def create_atem_tab(self):
        self.atem_enabled_checkbox = self._checkbox("Automatisch ansteuern")

        self.atem_enabled_checkbox.setToolTip("Mischer automatisch umschalten")
        self.atem_ip_input = self._line_edit("z. B. 192.168.10.240")
        self.atem_ip_input.setToolTip("IP-Adresse des Mischers")
        self.atem_test_btn = self._outline_button("Verbindung testen")
        self.atem_test_btn.clicked.connect(self.test_atem_connection)
        self.atem_test_btn.setToolTip("Verbindung prüfen")
        ip_row = QHBoxLayout()
        ip_row.setSpacing(t.GAP)
        ip_row.addWidget(self.atem_ip_input, 1)
        ip_row.addWidget(self.atem_test_btn)
        ip_box = QWidget()
        ip_box_layout = QVBoxLayout(ip_box)
        ip_box_layout.setContentsMargins(0, 0, 0, 0)
        ip_box_layout.setSpacing(6)
        ip_caption = QLabel("IP-Adresse")
        ip_caption.setStyleSheet(t.caption_style())
        ip_box_layout.addWidget(ip_caption)
        ip_box_layout.addLayout(ip_row)

        self.atem_status_label = QLabel()
        self._set_atem_status("idle", "Noch nicht getestet")

        self.atem_pres_spin = self._spinbox()
        self.atem_cam_spin = self._spinbox()
        self.atem_default_spin = self._spinbox()
        self.atem_start_spin = self._spinbox(0, 20)
        self.atem_start_spin.setSpecialValueText("Schwarz")          # 0 = Schwarzbild (Black) des Mischers
        self.atem_start_spin.setToolTip("Beim Programmstart")
        self.atem_pres_spin.setToolTip("Beamer-Bild und Pausentimer")
        self.atem_cam_spin.setToolTip("Kamerabilder")
        self.atem_default_spin.setToolTip("Nach dem Schließen")
        grid = QGridLayout()
        grid.setHorizontalSpacing(t.GAP)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        rows = (
            ("Präsentation / Pausentimer", self.atem_pres_spin),
            ("Seitenleisten-Kamera", self.atem_cam_spin),
            ("Standard beim Schließen", self.atem_default_spin),
            ("Beim Programmstart", self.atem_start_spin),
        )
        for row, (text, spin) in enumerate(rows):
            label = QLabel(text)
            label.setStyleSheet(f"font-size: {t.FS}px; color: {t.TEXT_LABEL};")
            grid.addWidget(label, row, 0)
            grid.addWidget(spin, row, 1)

        first_items = [self.atem_enabled_checkbox]
        if not atem.available():
            missing = QLabel("ATEM-Modul (PyATEMMax) fehlt – wird beim nächsten Start installiert.")
            missing.setWordWrap(True)
            missing.setStyleSheet(t.hint_style())
            first_items.append(missing)
        first_items += [ip_box, self.atem_status_label]

        self.xair_enabled_checkbox = self._checkbox("Über die Webseite steuern")
        self.xair_enabled_checkbox.setToolTip("Kanäle 1–8 in der Web-Fernsteuerung")
        self.xair_ip_input = self._line_edit("z. B. 192.168.10.50")
        self.xair_ip_input.setToolTip("IP-Adresse des Pults")

        inputs_caption = QLabel("Eingänge")
        inputs_caption.setStyleSheet(t.caption_style())
        return {
            "atem": self._card(*first_items, inputs_caption, grid, title="ATEM-Mischer"),   # Verbindung und Eingänge in einer Karte
            "xair": self._card(self.xair_enabled_checkbox, self._field("IP-Adresse", self.xair_ip_input), title="Behringer X AIR",
                               info="Lauter, leiser und Mute für die Kanäle 1–8 in der Web-Fernsteuerung."),
        }

    def _set_atem_status(self, kind: str, text: str):
        color = {"ok": t.ACCENT_LIGHT, "error": t.REC_RED, "busy": t.TEXT_SECONDARY}.get(kind, t.TEXT_MUTED)
        self.atem_status_label.setText(f"●  {text}")
        self.atem_status_label.setStyleSheet(
            f"font-size: {t.FS_SMALL}px; font-weight: 500; color: {color}; background: transparent; border: 0;"
        )

    def test_atem_connection(self):
        ip = self.atem_ip_input.text().strip()
        if not ip:
            self._set_atem_status("error", "Bitte zuerst eine IP-Adresse eingeben")
            return
        self.atem_test_btn.setEnabled(False)
        self._set_atem_status("busy", "Verbindung wird getestet …")
        threading.Thread(target=self._run_atem_test, args=(ip,), daemon=True).start()

    def _run_atem_test(self, ip: str):
        ok, message = atem.test_connection(ip)
        try:
            self.atem_test_done.emit(ok, message)
        except RuntimeError:  # Dialog wurde währenddessen geschlossen
            pass

    def _on_atem_test_done(self, ok: bool, message: str):
        self.atem_test_btn.setEnabled(True)
        self._set_atem_status("ok" if ok else "error", "Verbunden" if ok else f"Keine Verbindung – {message}")
