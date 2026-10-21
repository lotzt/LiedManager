import sys


def _setup_logging():
    import logging

    from paths import FROZEN, user_data_dir
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    if FROZEN:  # gebaute App hat keine Konsole -> Log-Datei im Datenordner
        logging.basicConfig(level=logging.INFO, format=fmt,
                            filename=str(user_data_dir() / "liedmanager.log"), encoding="utf-8")
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)


def main() -> int:
    if not getattr(sys, "frozen", False):
        import bootstrap  # nur im Quellcode: installiert fehlende Pakete (die gebaute App bringt alles mit)
        bootstrap.ensure_dependencies()
    _setup_logging()

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from paths import custom_db_path, user_data_dir
    from services import permissions
    from ui.main_window import MainWindow
    from ui.theme import apply_theme
    from ui.tooltip import install_tooltips

    app = QApplication(sys.argv)
    apply_theme(app)
    install_tooltips(app)  # abgerundete Hover-Erklärungen
    permissions.ensure_at_start()  # Kamera/Mikrofon anfragen, bevor die Kameras starten
    window = MainWindow()
    window.show()
    window.updates.check_on_start()   # Update-Suche im Hintergrund, nur wenn eingerichtet und nicht abgeschaltet
    window.sync.configure()           # Datenbank-Abgleich (nur wenn eine Server-Adresse eingetragen ist)
    window.remote.configure()         # Steuerung über die eigene Website (nur wenn in den Einstellungen eingeschaltet)
    QTimer.singleShot(3000, window.sync.run_now)
    if not window.db.available:
        chosen = custom_db_path()
        if chosen:
            QMessageBox.information(
                window, "Datenbank fehlt",
                f"Die in den Einstellungen gewählte Datenbank wurde nicht gefunden:\n{chosen}\n\n"
                "Bitte wähle unter Einstellungen → Datenbank eine andere Datenbank aus.",
            )
        else:
            QMessageBox.information(
                window, "Datenbank fehlt",
                "Die Datenbank „LiedManager.db“ wurde nicht gefunden.\n\n"
                f"Bitte kopiere sie in diesen Ordner und starte das Programm neu:\n{user_data_dir()}\n\n"
                "Oder wähle sie unter Einstellungen → Datenbank aus.",
            )
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
