"""Erzeugt alle Build-Dateien in build/: App-Icon und Windows-Versionsdatei.

Aufruf:  python tools/build_assets.py

Erzeugt:
  build/icon.png, build/icon.ico   (alle Systeme)
  build/icon.icns                  (nur auf dem Mac, benötigt iconutil)
  build/version_info.txt           (Windows-Dateieigenschaften der .exe, aus version.py)
  version.py                       (auf GitHub: GITHUB_REPO für den Auto-Updater)
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from version import APP_NAME, __version__  # noqa: E402

OUT = ROOT / "build"
BG_TOP, BG_BOTTOM = (40, 37, 35), (21, 19, 18)          # Warm-Anthrazit
ACCENT_GLOW, ACCENT_LIGHT, ACCENT, ACCENT_DEEP = (235, 192, 138), (217, 164, 106), (192, 138, 83), (143, 98, 54)  # Bronze
MAC_MARGIN = 0.098                                      # Apple-Raster: ~10 % Rand um das Icon (sonst wirkt es im Dock zu groß)


def bezier(p0, p1, p2, p3, n=40):
    pts = []
    for i in range(n + 1):
        t = i / n; u = 1 - t
        pts.append((u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0],
                    u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]))
    return pts


# Umriss des Gemeindehauses: Mittellinie von Dach und den beiden schrägen Trägern (Bildpunkte aus dem Gemeinde-Logo)
HOUSE_LINE = [(7, 197), (37, 8), (149, 21), (221, 46), (456, 86), (646, 30), (676, 197)]
HOUSE_STROKE = 12         # Strichstärke im Original-Logo (Bildpunkte)
HOUSE_ALPHA = 72          # sehr zurückhaltend: gerade so sichtbar (0-255)


def vgrad(size, top, bottom):
    g = Image.linear_gradient("L").resize(size)
    return Image.composite(Image.new("RGBA", size, bottom + (255,)), Image.new("RGBA", size, top + (255,)), g)


def render(size=1024, margin=0.0, ending="cross"):
    S = 2
    s = size * S
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    m = int(s * margin)
    t = s - 2 * m                       # Kantenlänge des Quadrats
    tile = vgrad((t, t), BG_TOP, BG_BOTTOM)
    mask = Image.new("L", (t, t), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, t - 1, t - 1), radius=int(t * 0.225), fill=255)
    layer = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    layer.paste(tile, (0, 0), mask)

    cx = cy = t / 2
    R = t * 0.335                       # Ring-Radius (Mitte der Linie)
    # weiches Leuchten hinter dem Ring
    glow = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((cx - R, cy - R, cx + R, cy + R), fill=ACCENT_DEEP + (120,))
    glow = glow.filter(ImageFilter.GaussianBlur(t * 0.06))
    layer = Image.alpha_composite(layer, glow)

    # Ring als Maske, mit senkrechtem Bronze-Verlauf gefüllt
    ring = Image.new("L", (t, t), 0)
    w = t * 0.032
    ImageDraw.Draw(ring).ellipse((cx - R - w/2, cy - R - w/2, cx + R + w/2, cy + R + w/2), fill=255)
    ImageDraw.Draw(ring).ellipse((cx - R + w/2, cy - R + w/2, cx + R - w/2, cy + R - w/2), fill=0)
    bronze = vgrad((t, t), ACCENT_GLOW, ACCENT)
    layer.paste(bronze, (0, 0), ring)

    # Gebäude-Umriss: nur Dach und die beiden schrägen Träger, nur im Ring, kaum sichtbar, hinter der Note
    xs = [p[0] for p in HOUSE_LINE]; ys = [p[1] for p in HOUSE_LINE]
    k = 1.62 * R / (max(xs) - min(xs))
    ky = k * 1.35                       # etwas gestreckt, damit das Kreuz unter dem Dach Platz hat und der Umriss im Kleinen lesbar bleibt
    ox = cx - 0.81 * R - min(xs) * k
    base_y = cy + 0.58 * R
    oy = base_y - max(ys) * ky
    house_mask = Image.new("L", (t, t), 0)
    ImageDraw.Draw(house_mask).line([(ox + x * k, oy + y * ky) for x, y in HOUSE_LINE],
                                    fill=HOUSE_ALPHA, width=int(HOUSE_STROKE * k * 2.4), joint="curve")
    inner = Image.new("L", (t, t), 0)
    ri = R - w / 2
    ImageDraw.Draw(inner).ellipse((cx - ri, cy - ri, cx + ri, cy + ri), fill=255)
    house_mask = ImageChops.multiply(house_mask, inner)
    layer.paste(Image.new("RGBA", (t, t), ACCENT_LIGHT + (255,)), (0, 0), house_mask)

    # Note (Achtelnote): gekippter Kopf, Hals, geschwungenes Fähnchen
    u = R
    shift = -0.10 * u                    # optische Mitte: Fähnchen macht die Note rechts schwerer
    lift = 0.07 * u
    hx, hy = cx - 0.20*u - shift, cy + 0.42*u - lift
    rx, ry, ang = 0.335*u, 0.245*u, math.radians(-22)
    head = []
    for i in range(120):
        a = 2 * math.pi * i / 120
        x, y = rx * math.cos(a), ry * math.sin(a)
        head.append((hx + x*math.cos(ang) - y*math.sin(ang), hy + x*math.sin(ang) + y*math.cos(ang)))
    sw = 0.125 * u
    sx = hx + rx * 0.93 * math.cos(ang) + 0.0   # Hals sitzt am rechten Rand des Kopfes
    sx -= sw / 2 - 0.005*u
    sx -= 0.10 * u
    top = cy - 0.58 * u - lift
    d = ImageDraw.Draw(layer)
    d.polygon(head, fill=ACCENT_GLOW + (255,))
    d.rectangle((sx, top, sx + sw, hy - 0.10*u), fill=ACCENT_GLOW + (255,))
    x0 = sx + sw
    if ending == "cross":
        # Kreuz: der Hals ist der senkrechte Balken, oben sitzt der Querbalken
        arm = 0.36 * u                              # Armlänge je Seite
        bar_y = top + 0.21 * u
        mid = sx + sw / 2
        d.rectangle((mid - arm, bar_y, mid + arm, bar_y + sw), fill=ACCENT_GLOW + (255,))
    else:
        outer = bezier((x0, top), (x0 + 0.16*u, top), (x0 + 0.62*u, top + 0.22*u), (x0 + 0.46*u, top + 0.78*u))
        inner = bezier((x0 + 0.46*u, top + 0.78*u), (x0 + 0.46*u, top + 0.46*u), (x0 + 0.18*u, top + 0.36*u), (sx, top + 0.34*u))
        d.polygon(outer + inner, fill=ACCENT_GLOW + (255,))

    img.paste(layer, (m, m), layer)
    return img.resize((size, size), Image.LANCZOS)


def make_icons() -> None:
    base = render(1024)
    base.save(OUT / "icon.png")
    base.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    if sys.platform == "darwin":
        base = render(1024, margin=MAC_MARGIN)
        iconset = OUT / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for size in (16, 32, 128, 256, 512):
            base.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
            base.resize((size * 2, size * 2), Image.LANCZOS).save(iconset / f"icon_{size}x{size}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT / "icon.icns")], check=True)
    print("Icons erzeugt in", OUT)


def make_version_info() -> None:
    parts = [int(p) for p in __version__.split(".")] + [0]
    tup = tuple(parts[:4])
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704B0', [
      StringStruct('CompanyName', '{APP_NAME}'),
      StringStruct('FileDescription', '{APP_NAME} – Lieder, Beamer, Aufnahme und Pausentimer'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{APP_NAME}'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1031, 1200])])
  ]
)
"""
    (OUT / "version_info.txt").write_text(text, encoding="utf-8")
    print("version_info.txt für", __version__)


def inject_repo() -> None:
    """Auf GitHub: Repository der Releases in version.py eintragen, damit der Auto-Updater es kennt.

    Liegen die Installer in einem eigenen öffentlichen Repository (der Code bleibt privat), steht es in
    RELEASES_REPOSITORY (siehe Workflow); sonst gilt das Repository des Builds (GITHUB_REPOSITORY).
    Gilt nur für den laufenden Build (wird nicht committet); lokal bleibt GITHUB_REPO leer und der Updater aus.
    """
    repo = (os.environ.get("RELEASES_REPOSITORY") or os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if not repo:
        print("RELEASES_REPOSITORY/GITHUB_REPOSITORY nicht gesetzt – Auto-Updater bleibt in diesem Build aus.")
        return
    path = ROOT / "version.py"
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(r'GITHUB_REPO = "[^"]*"', f'GITHUB_REPO = "{repo}"', text)
    if count != 1:
        raise SystemExit("GITHUB_REPO in version.py nicht gefunden.")
    path.write_text(new_text, encoding="utf-8")
    print("Auto-Updater nutzt das Repository", repo)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    make_icons()
    make_version_info()
    inject_repo()


if __name__ == "__main__":
    main()
