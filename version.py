"""Einzige Stelle für die Versionsnummer (Semver: GROSS.MITTEL.KLEIN).

Nicht von Hand ändern – `python tools/release.py 2.1.0` setzt sie, committet und startet den Build.
GITHUB_REPO bleibt leer: tools/build_assets.py trägt es beim Bauen auf GitHub automatisch ein
(aus RELEASES_REPOSITORY, sonst GITHUB_REPOSITORY). Der Auto-Updater fragt dort die Releases ab; ohne Eintrag ist er aus.
"""
APP_NAME = "LiedManager"
__version__ = "2.1.7"
GITHUB_REPO = ""   # „besitzer/LiedManager“ – wird beim Build gesetzt
