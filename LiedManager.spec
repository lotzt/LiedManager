# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spezifikation für Windows (.exe-Ordner) und macOS (.app).

Aufruf:  pyinstaller --noconfirm LiedManager.spec
Vorher:  python tools/build_assets.py
"""
import importlib.util
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)  # noqa: F821  (von PyInstaller bereitgestellt)
BUILD = ROOT / "build"

version_ns = {}
exec((ROOT / "version.py").read_text(encoding="utf-8"), version_ns)
VERSION = version_ns["__version__"]
APP_NAME = version_ns["APP_NAME"]

datas = [
    (str(ROOT / "ui" / "assets"), "ui/assets"),
]
hiddenimports = []

# optionale Pakete nur einpacken, wenn im Build-Python vorhanden
if importlib.util.find_spec("certifi"):
    datas += collect_data_files("certifi")   # Zertifikate für die Update-Suche (gebaute Mac-App findet sonst keine)
if importlib.util.find_spec("pptx"):
    datas += collect_data_files("pptx")
    hiddenimports += collect_submodules("pptx")
if importlib.util.find_spec("keyring"):
    hiddenimports += collect_submodules("keyring")   # Schlüsselbund (macOS/Windows) für Token und Passwörter
if importlib.util.find_spec("playwright"):          # „Bei CCLI melden“: nur dabei, wenn im Build-Python installiert
    datas += collect_data_files("playwright")        # enthält den Playwright-Treiber; genutzt wird der installierte Chrome/Edge
    hiddenimports += collect_submodules("playwright")
for module in ("PyATEMMax", "ATEM"):
    if importlib.util.find_spec(module):
        hiddenimports += collect_submodules(module)

icon = None
if sys.platform == "darwin" and (BUILD / "icon.icns").exists():
    icon = str(BUILD / "icon.icns")
elif sys.platform.startswith("win") and (BUILD / "icon.ico").exists():
    icon = str(BUILD / "icon.ico")

version_file = None
if sys.platform.startswith("win") and (BUILD / "version_info.txt").exists():
    version_file = str(BUILD / "version_info.txt")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["bootstrap",  # Paket-Nachinstallation läuft nur im Quellcode (main.py importiert sie nur dort)
              "tkinter", "unittest", "pydoc", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
              "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.Qt3DCore", "PyQt6.QtBluetooth"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    icon=icon,
    version=version_file,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F841
        coll,
        name=f"{APP_NAME}.app",
        icon=icon,
        bundle_identifier="de.liedmanager.app",
        version=VERSION,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSMicrophoneUsageDescription": "LiedManager nimmt die Predigt über das Mikrofon auf.",
            "NSCameraUsageDescription": "LiedManager zeigt die Live-Kameras in der Seitenleiste an.",
            "NSCameraUseContinuityCameraDeviceType": True,  # macOS 14+: iPhone-/Continuity-Kameras in der Auswahl
            "NSAppleEventsUsageDescription": "LiedManager steuert PowerPoint für den Pausentimer.",
        },
    )
