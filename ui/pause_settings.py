"""Einstellungen der Pausenfolie (Teil von Einstellungen → Anzeige).

Art (ohne PowerPoint / PowerPoint), Jahreszeit, Vorlage übernehmen, Vorschau, Bibelvers, Ablauf, Musik sowie Text, Schrift,
Größe und Farbe jeder Text-Ebene. Gespeichert wird im Design der Jahreszeit (``services/pausenfolie.py``).
"""
import logging
import shutil
from pathlib import Path

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QColor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QColorDialog, QFileDialog, QFontComboBox, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QWidget,
)

from paths import custom_pausentimer_dir
from services import pausenfolie
from services.settings import app_settings
from ui import theme as t
from ui.pause_window import KEY_MODE, MODES, pause_mode, preview_images
from ui.widgets import round_combo_popup

log = logging.getLogger(__name__)

# (Ansicht, Rolle, Beschriftung, Text änderbar)
TEXT_ROWS = (
    ("announcements", "static", "Überschrift Ansagen", True),
    ("announcements", "announcements", "Ansagen", False),
    ("verse", "static", "Überschrift Bibelvers", True),
    ("verse", "verse", "Bibelvers", False),
    ("countdown", "number", "Countdown-Zahl", False),
    ("end", "end", "Text am Ende", True),
)


class PauseSettings(QObject):
    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog
        self._season = None
        self._design = None
        d = dialog

        self.mode_combo = d._combo()
        for key, label in MODES:
            self.mode_combo.addItem(label, key)
        self.mode_combo.setToolTip("Ohne PowerPoint: LiedManager zeigt die Pausenfolie selbst (schnell, kein Fremdfenster).\n"
                                   "PowerPoint: wie bisher über die PowerPoint-Vorlage.")
        self.import_btn = d._outline_button("Vorlage übernehmen …")
        self.import_btn.setToolTip("Liest die Vorlage dieser Jahreszeit ein: Bilder, Texte, Schriften, Farben, Bibelvers und Musik.\n"
                                   "Weiter in PowerPoint gestalten und danach einfach erneut übernehmen.")
        self.import_btn.clicked.connect(self.import_template)
        self.media_btn = d._outline_button("Bilder-Ordner")
        self.media_btn.setToolTip("Hier liegen die Bilder der Pausenfolie. Eine Datei durch eine gleichnamige ersetzen,\n"
                                  "dann erscheint das neue Bild (z. B. ein anderes Foto).")
        self.media_btn.clicked.connect(self.open_media_folder)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(t.hint_style())

        self.preview_labels = []
        self.preview_box = QWidget()
        grid = QGridLayout(self.preview_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        for index in range(4):
            label = QLabel()
            label.setFixedSize(224, 126)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(f"background: #000; border: 1px solid {t.BORDER}; border-radius: 6px; color: {t.TEXT_MUTED};")
            grid.addWidget(label, index // 2, index % 2)
            self.preview_labels.append(label)
        self.preview_btn = d._outline_button("Vorschau aktualisieren")
        self.preview_btn.clicked.connect(self.refresh_preview)

        self.verse_edit = QPlainTextEdit()
        self.verse_edit.setFixedHeight(84)
        self.verse_edit.setPlaceholderText("Bibelvers")
        self.verse_edit.setStyleSheet(t.input_style("QPlainTextEdit", "8px 12px"))
        self.reference_edit = d._line_edit("z. B. Lukas 2,14")

        self.verse_minutes = d._spinbox(0, 60)
        self.verse_minutes.setSuffix(" min")
        self.verse_minutes.setToolTip("So viele Minuten vor Pausenende erscheint der Bibelvers (0 = nie)")
        self.countdown_seconds = d._spinbox(5, 300)
        self.countdown_seconds.setSuffix(" s")
        self.countdown_seconds.setToolTip("So lange läuft der Countdown am Ende der Pause")
        self.pulse_checkbox = d._checkbox("Zahl pulsiert leicht bei jedem Sekundenwechsel (aus = wie in PowerPoint)")

        self.music_label = QLabel()
        self.music_label.setStyleSheet(f"color: {t.TEXT_LABEL}; font-size: {t.FS}px;")
        self.music_label.setWordWrap(True)
        self.music_btn = d._outline_button("Andere Musik …")
        self.music_btn.clicked.connect(self.choose_music)
        self.no_music_btn = d._outline_button("Keine Musik")
        self.no_music_btn.clicked.connect(self.remove_music)
        self.music_start = d._spinbox(0, 300)
        self.music_start.setSuffix(" s")
        self.music_start.setToolTip("So viele Sekunden vor Pausenende setzt die Musik ein")
        self.music_volume = d._spinbox(0, 100)
        self.music_volume.setSuffix(" %")

        self.text_rows = []                            # (Ansicht, Rolle, Textfeld|None, Schrift, Größe, Farbknopf)
        self.text_grid = QWidget()
        rows = QGridLayout(self.text_grid)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setHorizontalSpacing(8)
        rows.setVerticalSpacing(8)
        for column, caption in enumerate(("", "Text", "Schrift", "Größe", "Farbe")):
            if caption:
                head = QLabel(caption)
                head.setStyleSheet(t.caption_style())
                rows.addWidget(head, 0, column)
        for row, (scene, role, caption, editable) in enumerate(TEXT_ROWS, 1):
            label = QLabel(caption)
            label.setStyleSheet(f"font-size: {t.FS}px; color: {t.TEXT_LABEL};")
            rows.addWidget(label, row, 0)
            text = d._line_edit() if editable else None
            if text is not None:
                text.setMinimumWidth(170)
                rows.addWidget(text, row, 1)
            font = QFontComboBox()
            font.setFixedHeight(t.BTN - 8)
            font.setStyleSheet(t.combo_style())
            round_combo_popup(font)
            font.setMinimumWidth(210)
            rows.addWidget(font, row, 2)
            size = d._spinbox(6, 900)
            size.setSuffix(" px")
            size.setFixedWidth(120)
            rows.addWidget(size, row, 3)
            color = QPushButton()
            color.setFixedSize(44, 32)
            color.setCursor(Qt.CursorShape.PointingHandCursor)
            color.clicked.connect(lambda _c=False, b=color: self.pick_color(b))
            rows.addWidget(color, row, 4)
            self.text_rows.append((scene, role, text, font, size, color))

        d.season_combo.currentIndexChanged.connect(self._season_changed)

    # ------------------------------------------------------------------
    def cards(self) -> list:
        d = self.dialog
        buttons = QHBoxLayout()
        buttons.setSpacing(t.GAP)
        buttons.addWidget(self.import_btn, 1)
        buttons.addWidget(d.open_presentations_btn, 1)
        buttons.addWidget(self.media_btn, 1)
        preview_row = QHBoxLayout()
        preview_row.addWidget(self.preview_btn)
        preview_row.addStretch(1)
        times = d._two_fields(d._field("Bibelvers ab", self.verse_minutes), d._field("Countdown", self.countdown_seconds))
        music_buttons = QHBoxLayout()
        music_buttons.setSpacing(t.GAP)
        music_buttons.addWidget(self.music_btn)
        music_buttons.addWidget(self.no_music_btn)
        music_buttons.addStretch(1)
        music_values = d._two_fields(d._field("Musik ab", self.music_start), d._field("Lautstärke", self.music_volume))
        return [
            d._card(d._two_fields(d._field("Pausenfolie", self.mode_combo), d._field("Jahreszeit", d.season_combo)),
                    buttons, self.status_label, self.preview_box, preview_row,
                    title="Pausenfolie",
                    info="Ohne PowerPoint zeigt LiedManager die Pausenfolie selbst – gestaltet wie deine PowerPoint-Vorlage "
                         "„pausentimer_<Jahreszeit>.pptx“ (einmal übernehmen). Ansagen ändern sich sofort auf dem Beamer."),
            d._card(d._field("Bibelvers", self.verse_edit), d._field("Stelle", self.reference_edit), times,
                    self.pulse_checkbox,
                    title="Pausenfolie: Bibelvers & Ablauf",
                    info="Bis zur Bibelvers-Zeit stehen die Ansagen auf dem Beamer, danach der Bibelvers, am Ende der Countdown."),
            d._card(self.music_label, music_buttons, music_values,
                    title="Pausenfolie: Musik",
                    info="Die Musik aus der Vorlage (oder eine eigene MP3) setzt kurz vor Pausenende ein – über die Audio-Ausgabe "
                         "aus Einstellungen → Audio."),
            d._card(self.text_grid,
                    title="Pausenfolie: Schrift",
                    info="Text, Schriftart, Größe (in Pixeln einer 1920 × 1080-Folie) und Farbe jeder Text-Ebene. "
                         "Fehlt eine Schrift auf diesem Rechner, nimmt das Programm Arial."),
        ]

    # ------------------------------------------------------------------
    def load(self) -> None:
        index = self.mode_combo.findData(pause_mode())
        self.mode_combo.setCurrentIndex(max(0, index))
        self._load_season(self.dialog.season_combo.currentData())

    def _season_changed(self, _index) -> None:
        if self._season is not None:
            self._commit()
            self._save_design()
        self._load_season(self.dialog.season_combo.currentData())

    def _load_season(self, season) -> None:
        self._season = season
        from ui.pause_window import ensure_design
        self._design = ensure_design(season)[0] if season else None   # übernimmt die Vorlage bei Bedarf automatisch
        has = self._design is not None
        for widget in (self.verse_edit, self.reference_edit, self.verse_minutes, self.countdown_seconds,
                       self.pulse_checkbox, self.music_btn, self.no_music_btn, self.music_start, self.music_volume,
                       self.text_grid, self.media_btn, self.preview_btn):
            widget.setEnabled(has)
        if not has:
            template = custom_pausentimer_dir() / f"pausentimer_{season}.pptx"
            self.status_label.setText(
                "Für diese Jahreszeit ist noch keine Pausenfolie übernommen. "
                + (f"Die Vorlage „{template.name}“ liegt bereit – auf „Vorlage übernehmen …“ klicken "
                   "(oder einfach den Pausentimer starten, dann geschieht es automatisch)." if template.exists() else
                   f"Lege „{template.name}“ in den Pausenfolien-Ordner oder wähle eine Vorlage aus."))
            self._show_previews([])
            return
        design = self._design
        self.verse_edit.setPlainText(design.get("verse_text", ""))
        self.reference_edit.setText(design.get("verse_reference", ""))
        timing = design.get("timing") or {}
        self.verse_minutes.setValue(int(timing.get("verse_minutes", 5)))
        self.countdown_seconds.setValue(int(timing.get("countdown_seconds", 60)))
        self.pulse_checkbox.setChecked(bool(design.get("pulse", False)))
        music = design.get("music") or {}
        self.music_start.setValue(int(music.get("start_second", 58)))
        self.music_volume.setValue(round(float(music.get("volume", 0.8)) * 100))
        self._show_music()
        for scene, role, text, font, size, color in self.text_rows:
            layer = pausenfolie.text_layer(design, scene, role)
            for widget in (text, font, size, color):
                if widget is not None:
                    widget.setEnabled(layer is not None)
            if layer is None:
                continue
            if text is not None:
                text.setText(layer.get("text", ""))
            font.setCurrentFont(QFont(layer.get("font") or "Arial"))
            font.setProperty("shown", font.currentFont().family())   # nur bei echter Änderung zurückschreiben
            size.setValue(round(float(layer.get("size", 40))))
            size.setProperty("shown", size.value())
            self._set_color_button(color, layer.get("color", "#000000"))
        missing = pausenfolie.missing_fonts(design)
        from PyQt6.QtGui import QFontDatabase
        missing = [name for name in missing if name not in QFontDatabase.families()]
        self.status_label.setText(f"Übernommen aus „{design.get('source', '?')}“."
                                  + (f" Auf diesem Rechner fehlen die Schriften: {', '.join(missing)} – bitte installieren "
                                     "(sonst wird Arial verwendet)." if missing else ""))
        self.refresh_preview()

    def _show_music(self) -> None:
        file = ((self._design or {}).get("music") or {}).get("file")
        self.music_label.setText(f"Musik: {Path(file).name}" if file else "Keine Musik")
        self.no_music_btn.setEnabled(bool(file))

    @staticmethod
    def _set_color_button(button, color: str) -> None:
        button.setProperty("color", color)
        button.setStyleSheet(f"QPushButton {{ background: {color}; border: 1px solid {t.ACCENT_BORDER}; border-radius: 8px; }}"
                             f"QPushButton:hover {{ border-color: {t.ACCENT}; }}")

    def pick_color(self, button) -> None:
        chosen = QColorDialog.getColor(QColor(button.property("color") or "#000000"), self.dialog, "Farbe wählen")
        if chosen.isValid():
            self._set_color_button(button, chosen.name())

    # ------------------------------------------------------------------
    def _commit(self) -> None:
        """Feldwerte ins Design der aktuellen Jahreszeit übernehmen (ohne zu speichern)."""
        design = self._design
        if design is None:
            return
        design["verse_text"] = " ".join(self.verse_edit.toPlainText().split())
        design["verse_reference"] = self.reference_edit.text().strip()
        design["timing"] = {"verse_minutes": self.verse_minutes.value(), "countdown_seconds": self.countdown_seconds.value()}
        design["pulse"] = self.pulse_checkbox.isChecked()
        music = design.setdefault("music", {})
        music["start_second"] = self.music_start.value()
        music["volume"] = self.music_volume.value() / 100
        for scene, role, text, font, size, color in self.text_rows:
            layer = pausenfolie.text_layer(design, scene, role)
            if layer is None:
                continue
            if text is not None:
                layer["text"] = text.text()
            if font.currentFont().family() != font.property("shown"):   # fehlende Schrift nicht durch Ersatz überschreiben
                layer["font"] = font.currentFont().family()
            if size.value() != size.property("shown"):
                layer["size"] = size.value()
            layer["color"] = button_color = color.property("color") or layer.get("color", "#000000")
            if role == "verse" and layer.get("reference_style"):
                layer["reference_style"]["color"] = button_color

    def _save_design(self) -> None:
        if self._design is not None and self._season:
            try:
                pausenfolie.save(self._season, self._design)
            except OSError as exc:
                QMessageBox.warning(self.dialog, "Pausenfolie", f"Die Pausenfolie konnte nicht gespeichert werden:\n{exc}")

    def save(self) -> None:
        app_settings().setValue(KEY_MODE, self.mode_combo.currentData())
        self._commit()
        self._save_design()

    # ------------------------------------------------------------------
    def refresh_preview(self) -> None:
        if self._design is None or not self._season:
            self._show_previews([])
            return
        self._commit()
        self._save_design()                            # die Vorschau zeichnet das gespeicherte Design
        lines = self.dialog.parent().pausentimer_panel.lines() if hasattr(self.dialog.parent(), "pausentimer_panel") else None
        try:
            images = preview_images(self._season, (448, 252), [line for line in (lines or []) if line.strip()] or None)
        except Exception:                              # Vorschau darf die Einstellungen nie blockieren
            log.exception("Vorschau der Pausenfolie fehlgeschlagen")
            images = []
        self._show_previews(images)

    def _show_previews(self, images) -> None:
        for index, label in enumerate(self.preview_labels):
            if index < len(images):
                name, image = images[index]
                pixmap = QPixmap.fromImage(image).scaled(label.width() * 2, label.height() * 2,
                                                         Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)
                pixmap.setDevicePixelRatio(2)
                label.setPixmap(pixmap)
                label.setToolTip(name)
            else:
                label.clear()
                label.setText(pausenfolie.SCENE_NAMES[pausenfolie.SCENES[index]])

    def import_template(self) -> None:
        season = self.dialog.season_combo.currentData()
        start = custom_pausentimer_dir() / f"pausentimer_{season}.pptx"
        path, _ = QFileDialog.getOpenFileName(self.dialog, "PowerPoint-Vorlage übernehmen",
                                              str(start if start.exists() else custom_pausentimer_dir()),
                                              "PowerPoint (*.pptx)")
        if not path:
            return
        try:
            pausenfolie.import_pptx(path, season)
        except pausenfolie.ImportProblem as exc:
            QMessageBox.warning(self.dialog, "Pausenfolie", str(exc))
            return
        if Path(path).resolve() != start.resolve():   # Vorlage auch für den PowerPoint-Pausentimer bereitlegen
            try:
                start.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, start)
            except OSError:
                pass
        self._season = None                            # nichts Altes zurückschreiben
        self._load_season(season)

    def open_media_folder(self) -> None:
        if self._season:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            folder = pausenfolie.design_dir(self._season) / "media"
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def choose_music(self) -> None:
        if self._design is None:
            return
        path, _ = QFileDialog.getOpenFileName(self.dialog, "Musik für den Countdown", str(Path.home()),
                                              "Audio (*.mp3 *.m4a *.wav *.aac)")
        if not path:
            return
        folder = pausenfolie.design_dir(self._season) / "media"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / Path(path).name
        try:
            shutil.copyfile(path, target)
        except OSError as exc:
            QMessageBox.warning(self.dialog, "Pausenfolie", f"Die Musik konnte nicht übernommen werden:\n{exc}")
            return
        self._design.setdefault("music", {})["file"] = "media/" + target.name
        self._show_music()

    def remove_music(self) -> None:
        if self._design is not None:
            self._design.setdefault("music", {})["file"] = ""
            self._show_music()

