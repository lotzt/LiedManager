"""Reiter „Lieder“: Datenbank, Abgleich mit dem Server, gespielte Lieder und CCLI-Meldung."""
import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout, QWidget

from paths import default_db_path
from services import ccli, ccli_melden
from ui import theme as t
from ui.sync_ui import KEY_SYNC_AUTO, KEY_SYNC_TOKEN, KEY_SYNC_URL, STATUS_OFF


class SongsTab:
    """Teil von ``SettingsDialog`` (Mixin): baut die Karten dieses Reiters und reagiert auf seine Felder."""

    def create_data_tab(self):
        self.db_path_input = self._line_edit(default_db_path())
        self.db_path_input.setToolTip("Leer = automatisch suchen")
        self.db_path_browse_btn = self._outline_button("Durchsuchen …")
        self.db_path_browse_btn.clicked.connect(self.browse_database_path)
        self.db_path_browse_btn.setToolTip("Datenbank wählen")
        self.db_path_reset_btn = self._outline_button("Automatisch")
        self.db_path_reset_btn.clicked.connect(lambda: self.db_path_input.clear())
        self.db_path_reset_btn.setToolTip("Wieder automatisch suchen")
        db_row = QHBoxLayout()
        db_row.setSpacing(t.GAP)
        db_row.addWidget(self.db_path_input, 1)
        db_row.addWidget(self.db_path_browse_btn)
        db_row.addWidget(self.db_path_reset_btn)
        db_box = QWidget()
        db_layout = QVBoxLayout(db_box)
        db_layout.setContentsMargins(0, 0, 0, 0)
        db_layout.setSpacing(6)
        db_caption = QLabel("Datei")
        db_caption.setStyleSheet(t.caption_style())
        db_layout.addWidget(db_caption)
        db_layout.addLayout(db_row)

        return {"db": self._card(db_box, title="Datenbank"), "sync": self._build_sync_card()}

    def _build_sync_card(self) -> QFrame:
        """Abgleich der Datenbank mit dem eigenen Server (Reiter „Lieder“)."""
        self.sync_auto_checkbox = self._checkbox("Automatisch abgleichen (jede Minute)")
        self.sync_auto_checkbox.setToolTip("Aus: nur per Knopf")
        self.sync_auto_checkbox.toggled.connect(self._sync_auto_toggled)
        self.sync_url_input = self._line_edit("https://deine-domain.de/sync/sync.php")
        self.sync_url_input.setToolTip("Adresse von sync.php")
        self.sync_token_input = self._line_edit("Token (steht in sync.php)")
        self.sync_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.sync_token_input.setToolTip("Token aus sync.php")
        self.sync_now_btn = self._outline_button("Jetzt abgleichen")
        self.sync_now_btn.setToolTip("Änderungen senden und holen")
        self.sync_now_btn.clicked.connect(self._sync_now_clicked)
        self.sync_force_btn = self._outline_button("Alles neu hochladen")
        self.sync_force_btn.setToolTip("Dieser Stand gilt für alle Geräte\nVorher sichern!")
        self.sync_force_btn.clicked.connect(self._sync_force_clicked)
        self.sync_url_input.editingFinished.connect(self._apply_sync_fields)
        self.sync_token_input.editingFinished.connect(self._apply_sync_fields)
        self.sync_status_label = QLabel(STATUS_OFF)
        self.sync_status_label.setWordWrap(True)
        self.sync_status_label.setStyleSheet(t.hint_style())
        token_row = QHBoxLayout()                      # Token und die beiden Abgleich-Knöpfe in einer Reihe
        token_row.setSpacing(t.GAP)
        token_row.addWidget(self.sync_token_input, 1)
        token_row.addWidget(self.sync_now_btn)
        token_row.addWidget(self.sync_force_btn)
        token_box = QWidget()
        token_layout = QVBoxLayout(token_box)
        token_layout.setContentsMargins(0, 0, 0, 0)
        token_layout.setSpacing(6)
        token_caption = QLabel("Token")
        token_caption.setStyleSheet(t.caption_style())
        token_layout.addWidget(token_caption)
        token_layout.addLayout(token_row)
        return self._card(self.sync_auto_checkbox,
                          self._field("Server-Adresse", self.sync_url_input),
                          token_box, self.sync_status_label,
                          title="Abgleich mit Server",
                          info="Teilt Lied-Änderungen zwischen den Geräten. Überall dieselbe Adresse und dasselbe Token.")

    def set_sync_status(self, text: str) -> None:
        self.sync_status_label.setText(text)

    def _apply_sync_fields(self):
        """Adresse oder Token geändert: speichern und die Verbindung sofort darauf einstellen (keine Adresse = Abgleich aus)."""
        self._save_sync_fields()
        self._update_sync_buttons()
        sync = getattr(self.parent(), "sync", None)
        if sync is not None:
            sync.configure()
            self.sync_status_label.setText(sync.status)
        elif not self.sync_url_input.text().strip():
            self.sync_status_label.setText(STATUS_OFF)

    def _sync_auto_toggled(self, on: bool):
        """Automatischen Abgleich sofort ein- oder ausschalten, ohne die Verbindung zu trennen."""
        self.settings.setValue(KEY_SYNC_AUTO, on)
        self.settings.sync()
        sync = getattr(self.parent(), "sync", None)
        if sync is not None:
            sync.configure()
            self.sync_status_label.setText(sync.status)

    def _update_sync_buttons(self):
        on = bool(self.sync_url_input.text().strip())
        self.sync_auto_checkbox.setEnabled(on)
        self.sync_now_btn.setEnabled(on)
        self.sync_force_btn.setEnabled(on)

    def _save_sync_fields(self):
        """Adresse und Token sofort speichern – sie bleiben auch erhalten, wenn der Dialog mit „Abbrechen“ geschlossen wird."""
        s = self.settings
        s.setValue(KEY_SYNC_URL, self.sync_url_input.text().strip())
        s.setValue(KEY_SYNC_TOKEN, self.sync_token_input.text().strip())
        s.sync()

    def _sync_now_clicked(self):
        self._save_sync_fields()
        self.sync_requested.emit(self.sync_url_input.text().strip(), self.sync_token_input.text().strip())

    def _sync_force_clicked(self):
        url = self.sync_url_input.text().strip()
        if not url:
            self.set_sync_status("Bitte zuerst die Server-Adresse und das Token eintragen.")
            return
        answer = QMessageBox.question(
            self, "Alles neu hochladen?",
            "Die Datenbank auf diesem Gerät wird zum Stand für ALLE Geräte:\n\n"
            "• Alle Lieder werden zum Server hochgeladen (kann dauern).\n"
            "• Lieder, die in dieser Datenbank fehlen, werden auf allen Geräten gelöscht.\n"
            "• Andere Geräte überschreiben ihre Lieder mit diesem Stand.\n\n"
            "Das lässt sich nicht rückgängig machen. Hast du eine Sicherungskopie der Datenbank?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._save_sync_fields()
        self.sync_force_requested.emit(url, self.sync_token_input.text().strip())

    def browse_database_path(self):
        start = self.db_path_input.text().strip() or default_db_path()
        path, _ = QFileDialog.getOpenFileName(
            self, "Datenbank auswählen", start,
            "Datenbanken (*.db *.sqlite *.sqlite3);;Alle Dateien (*)",
        )
        if path:
            self.db_path_input.setText(path)

    def show_history(self):
        from ui.history_dialog import HistoryDialog
        HistoryDialog(self).exec()

    @staticmethod
    def _songs(count: int) -> str:
        return f"{count} Lied" if count == 1 else f"{count} Lieder"

    def _show_ccli_pending(self) -> None:
        open_count = len(ccli.read_report())
        self.ccli_status_label.setText(
            f"{open_count} CCLI-{'Nummer wartet' if open_count == 1 else 'Nummern warten'} auf die Meldung."
            if open_count else "Keine offenen CCLI-Meldungen.")

    def start_ccli_report(self):
        if getattr(self, "_ccli_thread", None) is not None and self._ccli_thread.is_alive():
            return
        if not ccli_melden.playwright_available():
            from paths import FROZEN
            self.ccli_status_label.setText(
                "„Bei CCLI melden“ fehlt in diesem Build (Playwright war beim Bauen nicht installiert)." if FROZEN else
                f"Dafür fehlt Playwright. Einmalig im Terminal: {ccli_melden.INSTALL_HINT}")
            return
        db = getattr(self.parent(), "db", None)
        # Meldeliste immer erst aktualisieren: neu gespielte Lieder kommen hinter noch offene Nummern
        path, _count, without = ccli.export_report(db.db_name if db is not None and db.available else None)
        todo = ccli_melden.pending(path)
        if not todo:
            self.ccli_status_label.setText("Nichts zu melden." if not without else
                                           f"Nichts zu melden – {self._songs(without)} ohne CCLI-Nummer.")
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Bei CCLI melden")
        box.setText(f"{self._songs(len(todo))} werden bei CCLI gemeldet.")
        box.setInformativeText(
            "Es öffnet sich ein Browser mit CCLI „Suchen & Melden“. Falls nötig, dort einloggen."
            + (f"\n\n{self._songs(without)} ohne CCLI-Nummer werden übersprungen." if without else ""))
        start = box.addButton("Browser öffnen", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not start:
            return
        self._ccli_stop = False
        self._ccli_answer, self._ccli_event = "", threading.Event()
        self.ccli_report_btn.setEnabled(False)
        self.ccli_status_label.setText("Browser wird geöffnet …")
        self._ccli_thread = threading.Thread(target=self._ccli_worker, args=(path,), daemon=True)
        self._ccli_thread.start()

    def _ccli_ask(self, title: str, text: str, buttons: tuple) -> str:
        """Aus dem Arbeitsthread: Rückfrage im Hauptthread stellen und auf die Antwort warten."""
        self._ccli_event.clear()
        self._ccli_buttons = buttons
        self.ccli_ask.emit(title, text)
        self._ccli_event.wait()
        return self._ccli_answer

    def _on_ccli_ask(self, title: str, text: str):
        """Rückfrage im selben Stil wie die übrigen Meldungen: kurzer Satz, Erklärung darunter, deutsche Knöpfe.
        Der letzte Knopf ist immer „Abbrechen/Aufhören“ (auch mit Esc)."""
        main, _, info = text.partition("\n")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(main)
        if info:
            box.setInformativeText(info)
        added = {}
        for index, (key, label) in enumerate(self._ccli_buttons):
            last = index == len(self._ccli_buttons) - 1
            button = box.addButton(label, QMessageBox.ButtonRole.RejectRole if last else QMessageBox.ButtonRole.AcceptRole)
            added[button] = key
            if index == 0:
                box.setDefaultButton(button)
        box.exec()
        self._ccli_answer = added.get(box.clickedButton(), self._ccli_buttons[-1][0])
        self._ccli_event.set()

    def _ccli_worker(self, path):
        try:
            counts = ccli_melden.run(
                path,
                wait_login=lambda: self._ccli_ask(
                    "Bei CCLI melden", "Bist du bei CCLI eingeloggt?\n"
                    "Im Browser ist CCLI „Suchen & Melden“ geöffnet. Falls nötig, dort einloggen – danach hier „Weiter“.",
                    (("ok", "Weiter"), ("stop", "Abbrechen"))) == "ok",
                after_first=lambda number, status: self._ccli_ask(
                    "Bei CCLI melden", f"CCLI-Nummer {number} wurde gemeldet.\n"
                    "Bitte im Browser prüfen, ob das richtige Lied gemeldet ist.",
                    (("next", "Weiter"), ("auto", "Rest automatisch"), ("stop", "Aufhören"))),
                progress=lambda i, n, text: self.ccli_progress.emit(f"{i}/{n} {text}"),
                should_stop=lambda: self._ccli_stop)
            summary = f"{counts['gemeldet']} gemeldet, {counts['fehler']} Fehler, {counts['offen']} offen."
        except ccli_melden.MeldenError as exc:
            summary = str(exc)
        except Exception as exc:
            summary = f"Meldung abgebrochen: {exc}"
        self.ccli_progress.emit("\x00" + summary)

    def _on_ccli_progress(self, text: str):
        if text.startswith("\x00"):
            self.ccli_status_label.setText(text[1:])
            self.ccli_report_btn.setEnabled(True)
        else:
            self.ccli_status_label.setText(text)

    def create_songlog_cards(self) -> dict:
        """Gespielte Lieder (Liste, Historie) und die CCLI-Meldung."""
        self.songlog_checkbox = self._checkbox("Gespielte Lieder speichern")
        self.songlog_checkbox.setToolTip("Jedes gezeigte Lied wird gespeichert")
        self.history_btn = self._outline_button("Liedhistorie")
        self.history_btn.setToolTip("Gespielte Lieder anzeigen")
        self.history_btn.clicked.connect(self.show_history)
        self.ccli_report_btn = self._outline_button("Bei CCLI melden")
        self.ccli_report_btn.setToolTip("Gespielte Lieder bei CCLI melden")
        self.ccli_report_btn.clicked.connect(self.start_ccli_report)
        self.no_report_input = self._line_edit("z. B. So 10:00–11:00; Mi 19:00–20:00")
        self.no_report_input.setToolTip("Mehrere Zeiten mit „;“ trennen · leer = alles melden")
        self.ccli_status_label = QLabel()
        self.ccli_status_label.setWordWrap(True)
        self.ccli_status_label.setStyleSheet(t.hint_style())
        self.ccli_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._show_ccli_pending()                      # wie die anderen Statuszeilen: nie leer

        history_row = QHBoxLayout()
        history_row.addWidget(self.history_btn)
        history_row.addStretch(1)
        return {
            "songlog": self._card(self.songlog_checkbox, history_row, title="Gespielte Lieder",
                                  info="Grundlage für die CCLI-Meldung."),
            "ccli": self._card(self.ccli_report_btn,
                               self._field("Nicht melden (Zeiten)", self.no_report_input),
                               self.ccli_status_label,
                               title="CCLI-Meldung",
                               info="Meldet nur die CCLI-Nummern der gespielten Lieder."),
        }
