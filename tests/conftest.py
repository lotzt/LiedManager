"""Gemeinsame Umgebung für die Tests: ohne Bildschirm, mit eigenen (leeren) Einstellungen und Testdatenbank.

Wie ``tools/smoke_test.py`` darf kein Test die echten Einstellungen, die echte Datenbank oder die echte Liederliste
anfassen. Aufruf:  ``pytest``  (im LiedManager-Ordner; die Oberfläche läuft „offscreen“).
"""
import faulthandler
import os
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

SESSION_DIR = Path(tempfile.mkdtemp(prefix="liedmanager_pytest_"))
os.environ["LIEDMANAGER_SETTINGS_DIR"] = str(SESSION_DIR)    # vor dem ersten Zugriff auf die Einstellungen setzen

# Hängt ein Test (z. B. an einem Dialog, den niemand bestätigt), steht im Protokoll wo – und es geht nicht ewig weiter.
faulthandler.dump_traceback_later(int(os.environ.get("SMOKE_TEST_TIMEOUT", "400")), exit=True)

_exit_status = 0


@pytest.fixture(scope="session")
def app():
    """Eine QApplication für alle Tests, mit denselben Schutzmaßnahmen wie der Smoke-Test."""
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication, QDialog

    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(SESSION_DIR))
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(SESSION_DIR))

    from services import songlog
    songlog_dir = SESSION_DIR / "Gespielte Lieder"
    songlog_dir.mkdir(exist_ok=True)
    songlog.songlog_dir = lambda: songlog_dir

    application = QApplication.instance() or QApplication(sys.argv)

    def no_modal_dialog(self, *args, **kwargs):
        raise AssertionError(f"Unerwarteter modaler Dialog im Test: {type(self).__name__}")

    QDialog.exec = no_modal_dialog

    from services.settings import app_settings
    app_settings().setValue(songlog.KEY_TEST_MODE, True)        # wie im Smoke-Test: nichts in die Liederliste schreiben
    app_settings().setValue(songlog.KEY_ENABLED, True)
    return application


@pytest.fixture
def tmp(tmp_path, monkeypatch, app):
    """Eigener Ordner je Test mit Testdatenbank; er ist auch das Arbeitsverzeichnis (dort wird die Datenbank gesucht)."""
    import smoke_test
    smoke_test.make_test_db(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def pytest_sessionfinish(session, exitstatus):
    global _exit_status
    _exit_status = int(exitstatus)


def pytest_unconfigure(config):
    # Wie im Smoke-Test: sofort beenden. Das Aufräumen der Qt-Objekte beim Beenden von Python stürzt sonst ab
    # und würde einen bestandenen Lauf als Fehler melden. Die Zusammenfassung ist zu diesem Zeitpunkt schon ausgegeben.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_status)
