"""Erzeugt ``server/remote.php`` für die Website-Steuerung.

Die Datei besteht aus ``server/remote_template.php`` (Programmlogik des Servers) und der Webseite der Fernsteuerung
(``services/web_remote_page.py`` im Design des Programms). Wer die Seite oder das Design ändert, führt aus:

    python tools/build_remote_site.py            # schreibt server/remote.php neu
    python tools/build_remote_site.py --check    # prüft nur, ob server/remote.php noch aktuell ist (Exit-Code 1 = veraltet)

In ``remote.php`` selbst trägt man nur die Zugangsdaten ein (TOKEN, PIN, Datenbank) – auf dem Server, nicht im Repository.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEMPLATE = ROOT / "server" / "remote_template.php"
TARGET = ROOT / "server" / "remote.php"

# Platzhalter in der Vorlage -> (Ende-Marke des Nowdoc, Pfad der Datei in ``build_assets``)
PARTS = {
    "__PAGE_HTML__": ("LM_PAGE_HTML", "/"),
    "__PAGE_CSS__": ("LM_PAGE_CSS", "/app.css"),
    "__PAGE_JS__": ("LM_PAGE_JS", "/app.js"),
    "__PAGE_MANIFEST__": ("LM_PAGE_MANIFEST", "/manifest.webmanifest"),
}
# Bilder (Logo) -> Platzhalter für Base64 in einer PHP-Zeichenkette
IMAGES = {
    "__ICON_FAVICON__": "/favicon-32.png",
    "__ICON_180__": "/icon-180.png",
    "__ICON_192__": "/icon-192.png",
    "__ICON_512__": "/icon-512.png",
}


def design_values() -> dict:
    """Dieselben Werte wie ``ui.web_remote_ui.design_values`` (der Smoke-Test vergleicht beide)."""
    from services.web_remote_page import REQUIRED_VALUES
    from ui import theme
    values = {name: getattr(theme, name) for name in REQUIRED_VALUES if hasattr(theme, name)}
    values["BODY"] = ", ".join(f'"{name}"' if " " in name else name for name in theme.BODY_FAMILIES)
    return values


def render(values: dict = None) -> str:
    from services.web_remote_page import build_assets
    assets = build_assets(values if values is not None else design_values())
    php = TEMPLATE.read_text(encoding="utf-8")
    for marker, (tag, path) in PARTS.items():
        content = assets[path][1].decode("utf-8")
        if tag in content:
            raise ValueError(f"Die Webseite enthält die Ende-Marke {tag} – bitte in remote_template.php umbenennen.")
        if php.count(marker) != 1:
            raise ValueError(f"Platzhalter {marker} muss genau einmal in remote_template.php stehen.")
        php = php.replace(marker, content.rstrip("\n"))
    import base64
    for marker, path in IMAGES.items():
        if php.count(marker) != 1:
            raise ValueError(f"Platzhalter {marker} muss genau einmal in remote_template.php stehen.")
        php = php.replace(marker, base64.b64encode(assets[path][1]).decode("ascii"))
    return php


def main(argv) -> int:
    php = render()
    if "--check" in argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != php:
            print("server/remote.php ist veraltet – bitte `python tools/build_remote_site.py` ausführen.")
            return 1
        print("server/remote.php ist aktuell.")
        return 0
    TARGET.write_text(php, encoding="utf-8", newline="\n")
    print(f"{TARGET.relative_to(ROOT)} geschrieben ({len(php.encode('utf-8')) // 1024} KB).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
