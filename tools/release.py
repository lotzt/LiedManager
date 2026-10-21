"""Neue Version veröffentlichen:   python tools/release.py 2.1.0

Setzt die Versionsnummer in version.py, committet, setzt den Git-Tag v2.1.0 und pusht beides.
Der Push des Tags startet auf GitHub automatisch den Build (Windows-Installer + Mac-DMG) und
legt das Release mit allen Dateien an.

Optionen:  --dry-run   nur anzeigen, was passieren würde
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "version.py"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def git(*args, capture=False):
    result = subprocess.run(["git", *args], cwd=ROOT, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if len(args) != 1 or not SEMVER.match(args[0]):
        print(__doc__)
        print("Fehler: bitte eine Version wie 2.1.0 angeben (GROSS.MITTEL.KLEIN).")
        return 1
    version = args[0]
    tag = f"v{version}"

    if git("status", "--porcelain", capture=True):
        print("Fehler: Es gibt nicht committete Änderungen. Bitte erst committen (git add -A && git commit).")
        return 1
    if git("tag", "--list", tag, capture=True):
        print(f"Fehler: Den Tag {tag} gibt es schon.")
        return 1

    text = VERSION_FILE.read_text(encoding="utf-8")
    new_text, count = re.subn(r'__version__ = "[^"]+"', f'__version__ = "{version}"', text)
    if count != 1:
        print("Fehler: __version__ in version.py nicht gefunden.")
        return 1

    print(f"Neue Version: {version}  (Tag {tag})")
    if dry:
        print("--dry-run: nichts geändert.")
        return 0

    VERSION_FILE.write_text(new_text, encoding="utf-8")
    git("add", "version.py")
    git("commit", "-m", f"Release {tag}")
    git("tag", "-a", tag, "-m", f"LiedManager {version}")
    git("push")
    git("push", "origin", tag)
    print("Fertig. Der Build läuft jetzt auf GitHub (Reiter „Actions“); das Release erscheint unter „Releases“.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
