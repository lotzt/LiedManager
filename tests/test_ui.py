"""Die Oberfläche als Ganzes: startet ``tools/smoke_test.py`` in einem eigenen Prozess.

Der Ablauf baut aufeinander auf (Hauptfenster, Einstellungen, Kameras, Bilder, Beamer) und braucht eine frische
QApplication – deshalb ein eigener Prozess. Die Abläufe aus ``test_logic.py`` werden dort übersprungen.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_oberflaeche():
    env = dict(os.environ, SMOKE_SKIP_LOGIC="1", QT_QPA_PLATFORM="offscreen", PYTHONUTF8="1")
    env.pop("LIEDMANAGER_SETTINGS_DIR", None)             # der Smoke-Test legt seinen eigenen Ordner an
    result = subprocess.run([sys.executable, "-X", "faulthandler", str(ROOT / "tools" / "smoke_test.py")],
                            cwd=ROOT, env=env, capture_output=True, text=True,
                            timeout=int(os.environ.get("SMOKE_TEST_TIMEOUT", "400")) + 30)
    assert result.returncode == 0, f"Smoke-Test fehlgeschlagen:\n{result.stdout[-4000:]}\n{result.stderr[-6000:]}"
