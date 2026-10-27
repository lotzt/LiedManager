import sys


def _setup_logging():
    import logging

    from paths import FROZEN, user_data_dir
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    if FROZEN:  # gebaute App hat keine Konsole -> Log-Datei im Datenordner, höchstens 1 MB, die letzten 3 bleiben
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(user_data_dir() / "liedmanager.log", maxBytes=1_000_000, backupCount=3,
                                      encoding="utf-8")
        logging.basicConfig(level=logging.INFO, format=fmt, handlers=[handler])
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)


def _windows_app_id() -> None:
    """Windows gruppiert das Fenster sonst unter „Python“ und zeigt dessen Symbol in der Taskleiste."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LiedManager.App")
        except (AttributeError, OSError):
            pass


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

    _windows_app_id()
    app = QApplication(sys.argv)
    from PyQt6.QtGui import QImageReader
    QImageReader.setAllocationLimit(2048)   # MB; Qt-Standard 256 MB verwirft sehr große Bilder (z. B. über 10 000 Pixel)
    app.setApplicationDisplayName("LiedManager")
    from services import songlog
    from services.settings import app_settings
    app_settings().setValue(songlog.KEY_TEST_MODE, False)       # den Testmodus gibt es in den Einstellungen nicht mehr
    from services import ccli
    ccli.remove_legacy_files()        # Ergebnisliste/Archiv früherer Versionen: Gemeldetes wird nicht aufbewahrt
    from services import autostart
    if autostart.is_enabled():
        autostart.set_enabled(True)   # Pfad aktuell halten (z. B. wenn die App verschoben oder aktualisiert wurde)
    apply_theme(app)
    from PyQt6.QtGui import QIcon
    from paths import ASSETS_DIR
    logo = ASSETS_DIR / "logo.png"                                           # eigenes Logo: Datei „logo.png“ dort ablegen
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))                                  # Fenster-/Programmsymbol (Windows: Titelleiste)
    install_tooltips(app)  # abgerundete Hover-Erklärungen
    permissions.ensure_at_start()  # Kamera/Mikrofon anfragen, bevor die Kameras starten
    window = MainWindow()
    window.show()
    from services import atem
    atem.switch("start")              # Videomischer beim Start auf Schwarz (bzw. den eingestellten Kanal)
    from services import problem_report
    problem_report.install()          # Fehler automatisch an die eigene Website melden (in den Einstellungen abschaltbar)
    from services import xair
    xair.configure()                  # Mischpult (X AIR), falls in den Einstellungen eingeschaltet
    QTimer.singleShot(4000, window.pausentimer.warm_up)   # Windows: PowerShell für den Pausentimer schon vorab starten
    QTimer.singleShot(600, window.db.all_songs)   # Texte aller Lieder schon im Leerlauf laden, nicht erst bei der ersten Suche
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
