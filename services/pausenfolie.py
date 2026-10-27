"""Pausenfolie ohne PowerPoint: liest eine PowerPoint-Vorlage einmal ein und beschreibt sie als „Design“.

Die Vorlage (z. B. ``pausentimer_winter.pptx``) bleibt das Werkzeug zum Gestalten. ``import_pptx`` holt daraus:

* die vier Ansichten – Ansagen (Folie 1), Bibelvers (Folie 2), Countdown (Folie 3, „60“) und Ende (letzte Folie) –
  mit allen Bild-Ebenen (Lage, Größe, Drehung), dem Hintergrund und den Texten (Schrift, Größe, Farbe, Ausrichtung),
* den Bibelvers und die Stellenangabe, den Puls-Effekt des Countdowns,
* die Musik (Datei, ab welcher Sekunde sie einsetzt, Lautstärke),
* eingebettete Schriften, soweit sie vollständig in der Vorlage stecken.

Alles landet im Datenordner unter ``pausenfolie/<jahreszeit>/`` (``design.json`` + Bilder, Musik, Schriften). Gezeichnet wird
von ``ui/pause_window.py``. Koordinaten sind Pixel einer 1920 × 1080-Fläche, Schriftgrößen ebenfalls in Pixeln.
Dieses Modul kennt Qt nicht (lässt sich ohne Oberfläche testen).
"""
import json
import logging
import posixpath
import re
import shutil
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from paths import user_data_dir

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 1920, 1080
DESIGN_FILE = "design.json"
VERSION = 3                 # 2: Ansagen-Feld zuverlässiger erkannt · 3: Zahlen ohne Puls wie in PowerPoint (ältere Designs werden neu übernommen)

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
}
R_EMBED = "{%s}embed" % NS["r"]
R_LINK = "{%s}link" % NS["r"]
R_ID = "{%s}id" % NS["r"]

SCENES = ("announcements", "verse", "countdown", "end")
SCENE_NAMES = {"announcements": "Ansagen", "verse": "Bibelvers", "countdown": "Countdown", "end": "Ende"}

DEFAULT_TIMING = {"verse_minutes": 5, "countdown_seconds": 60}


class ImportProblem(Exception):
    """Die Vorlage lässt sich nicht einlesen (Meldung für den Benutzer)."""


# ----------------------------------------------------------------------
# Ablage
# ----------------------------------------------------------------------
def designs_dir() -> Path:
    return user_data_dir() / "pausenfolie"


def design_dir(season: str) -> Path:
    return designs_dir() / str(season or "frühling")


def load(season: str):
    """Das Design einer Jahreszeit (dict) oder ``None``, wenn noch keine Vorlage übernommen wurde."""
    path = design_dir(season) / DESIGN_FILE
    try:
        with open(path, encoding="utf-8") as handle:
            design = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(design, dict) or not isinstance(design.get("scenes"), dict):
        return None
    design.setdefault("timing", dict(DEFAULT_TIMING))
    design.setdefault("pulse", False)
    design.setdefault("music", {})
    design["_dir"] = str(design_dir(season))
    return design


def save(season: str, design: dict) -> None:
    folder = design_dir(season)
    folder.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in design.items() if not k.startswith("_")}
    temp = folder / (DESIGN_FILE + ".tmp")
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
    temp.replace(folder / DESIGN_FILE)


def text_layer(design: dict, scene: str, role: str):
    """Die (erste) Text-Ebene einer Rolle in einer Ansicht – zum Ändern von Schrift, Größe und Farbe."""
    for layer in (design.get("scenes", {}).get(scene) or {}).get("layers", []):
        if layer.get("kind") == "text" and layer.get("role") == role:
            return layer
    return None


# ----------------------------------------------------------------------
# Ablauf: welche Ansicht gerade dran ist
# ----------------------------------------------------------------------
def phase(seconds_left: float, design: dict = None):
    """(Ansicht, Zahl) zur Restzeit. Zahl nur beim Countdown (60 … 1), sonst ``None``."""
    import math
    timing = dict(DEFAULT_TIMING)
    timing.update((design or {}).get("timing") or {})
    countdown = max(1, int(timing.get("countdown_seconds", 60)))
    verse = max(0.0, float(timing.get("verse_minutes", 5))) * 60
    if seconds_left <= 0:
        return "end", None
    if seconds_left <= countdown:
        return "countdown", max(1, math.ceil(seconds_left))
    if verse and seconds_left <= verse:
        return "verse", None
    return "announcements", None


# ----------------------------------------------------------------------
# Einlesen der Vorlage
# ----------------------------------------------------------------------
class _Package:
    """Zugriff auf die Teile einer .pptx-Datei (ein ZIP mit XML-Dateien)."""

    def __init__(self, path):
        try:
            self.zip = zipfile.ZipFile(path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise ImportProblem(f"Die Datei ist keine PowerPoint-Datei (.pptx): {exc}") from exc
        self.names = set(self.zip.namelist())

    def xml(self, name):
        return ET.fromstring(self.zip.read(name))

    def rels(self, part: str) -> dict:
        """Id -> Zielpfad (absolut im Paket) für ein Teil, z. B. ppt/slides/slide1.xml."""
        folder, file = posixpath.split(part)
        rel_name = posixpath.join(folder, "_rels", file + ".rels")
        if rel_name not in self.names:
            return {}
        result = {}
        for rel in self.xml(rel_name).findall("rel:Relationship", NS):
            target = rel.get("Target", "")
            if rel.get("TargetMode") == "External":
                continue
            result[rel.get("Id")] = posixpath.normpath(posixpath.join(folder, target))
        return result


def _emu_scale(pkg):
    size = pkg.xml("ppt/presentation.xml").find("p:sldSz", NS)
    cx = int(size.get("cx", 12192000)) if size is not None else 12192000
    cy = int(size.get("cy", 6858000)) if size is not None else 6858000
    return WIDTH / cx, cy * WIDTH / cx


def _slide_parts(pkg) -> list:
    pres = pkg.xml("ppt/presentation.xml")
    rels = pkg.rels("ppt/presentation.xml")
    return [rels[s.get(R_ID)] for s in pres.findall("p:sldIdLst/p:sldId", NS) if s.get(R_ID) in rels]


def _theme_colors(pkg) -> dict:
    """Farbnamen des Designs (dk1, lt1, accent1 …) -> „RRGGBB“."""
    colors = {}
    themes = sorted(n for n in pkg.names if re.match(r"ppt/theme/theme\d+\.xml$", n))
    if not themes:
        return colors
    scheme = pkg.xml(themes[0]).find(".//a:clrScheme", NS)
    if scheme is None:
        return colors
    for child in scheme:
        name = child.tag.split("}")[-1]
        for value in child:
            hexcolor = value.get("val") if value.tag.endswith("srgbClr") else value.get("lastClr")
            if hexcolor:
                colors[name] = hexcolor
    colors.setdefault("tx1", colors.get("dk1", "000000"))
    colors.setdefault("bg1", colors.get("lt1", "FFFFFF"))
    colors.setdefault("tx2", colors.get("dk2", "000000"))
    colors.setdefault("bg2", colors.get("lt2", "FFFFFF"))
    return colors


def _hls(rgb):
    import colorsys
    r, g, b = (int(rgb[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def _from_hls(h, l, s):
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), s)
    return "".join(f"{round(v * 255):02X}" for v in (r, g, b))


def _color(fill, theme) -> tuple:
    """(„#RRGGBB“, Deckkraft 0–1) aus einem <a:solidFill> (srgbClr, schemeClr, sysClr; lumMod/lumOff/alpha)."""
    if fill is None:
        return "#000000", 1.0
    value = next(iter(fill), None)
    if value is None:
        return "#000000", 1.0
    tag = value.tag.split("}")[-1]
    if tag == "srgbClr":
        rgb = value.get("val", "000000")
    elif tag == "schemeClr":
        rgb = theme.get(value.get("val", "tx1"), "000000")
    elif tag == "sysClr":
        rgb = value.get("lastClr", "000000")
    else:
        rgb = "000000"
    alpha = 1.0
    h, l, s = _hls(rgb)
    changed = False
    for mod in value:
        name, amount = mod.tag.split("}")[-1], int(mod.get("val", "100000")) / 100000
        if name == "lumMod":
            l, changed = l * amount, True
        elif name == "lumOff":
            l, changed = l + amount, True
        elif name == "alpha":
            alpha = amount
    if changed:
        rgb = _from_hls(h, l, s)
    return "#" + rgb.upper(), alpha


def _xfrm(sp_pr, scale):
    """[x, y, w, h] in Pixeln, Drehung in Grad, Spiegelung (aus <a:xfrm>)."""
    xfrm = sp_pr.find("a:xfrm", NS) if sp_pr is not None else None
    if xfrm is None:
        return None, 0.0, False, False
    off, ext = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None, 0.0, False, False
    rect = [int(off.get("x", 0)) * scale, int(off.get("y", 0)) * scale,
            int(ext.get("cx", 0)) * scale, int(ext.get("cy", 0)) * scale]
    rot = int(xfrm.get("rot", 0)) / 60000
    return [round(v, 2) for v in rect], rot, xfrm.get("flipH") == "1", xfrm.get("flipV") == "1"


def _insets(element, keys=("l", "t", "r", "b")):
    return [int(element.get(k, 0)) / 100000 for k in keys] if element is not None else [0, 0, 0, 0]


class _Importer:
    def __init__(self, path, target: Path):
        self.pkg = _Package(path)
        self.target = target
        self.scale, self.slide_h = _emu_scale(self.pkg)
        self.theme = _theme_colors(self.pkg)
        self.media = {}            # Pfad im Paket -> Dateiname im Design-Ordner

    # --- Dateien -------------------------------------------------------
    def copy_media(self, part: str) -> str:
        if part in self.media:
            return self.media[part]
        name = posixpath.basename(part)
        (self.target / "media").mkdir(parents=True, exist_ok=True)
        with open(self.target / "media" / name, "wb") as out:
            out.write(self.pkg.zip.read(part))
        self.media[part] = "media/" + name
        return self.media[part]

    # --- Hintergrund ---------------------------------------------------
    def background(self, slide_part: str) -> dict:
        """Hintergrund der Folie, sonst des Layouts, sonst des Masters."""
        part = slide_part
        for _level in range(3):
            root = self.pkg.xml(part)
            rels = self.pkg.rels(part)
            bg = root.find("p:cSld/p:bg/p:bgPr", NS)
            if bg is not None:
                blip = bg.find("a:blipFill/a:blip", NS)
                if blip is not None and blip.get(R_EMBED) in rels:
                    stretch = bg.find("a:blipFill/a:stretch/a:fillRect", NS)
                    return {"file": self.copy_media(rels[blip.get(R_EMBED)]), "fill": _insets(stretch)}
                solid = bg.find("a:solidFill", NS)
                if solid is not None:
                    return {"color": _color(solid, self.theme)[0]}
            ref = root.find("p:cSld/p:bg/p:bgRef", NS)
            if ref is not None and len(ref):
                return {"color": _color(ref, self.theme)[0]}
            parent = next((t for t in rels.values() if "slideLayout" in t or "slideMaster" in t), None)
            if parent is None:
                break
            part = parent
        return {"color": "#000000"}

    # --- Ebenen --------------------------------------------------------
    def layers(self, slide_part: str) -> list:
        root = self.pkg.xml(slide_part)
        rels = self.pkg.rels(slide_part)
        tree = root.find("p:cSld/p:spTree", NS)
        result = []
        for shape in list(tree) if tree is not None else []:
            tag = shape.tag.split("}")[-1]
            if tag not in ("sp", "pic"):
                if tag == "grpSp":
                    log.info("Pausenfolie: Gruppe in %s wird übersprungen", slide_part)
                continue
            name = (shape.find(".//p:cNvPr", NS).get("name", "") if shape.find(".//p:cNvPr", NS) is not None else "")
            sp_pr = shape.find("p:spPr", NS)
            rect, rot, flip_h, flip_v = _xfrm(sp_pr, self.scale)
            if rect is None:
                continue
            blip = (sp_pr.find("a:blipFill/a:blip", NS) if tag == "sp" and sp_pr is not None
                    else shape.find("p:blipFill/a:blip", NS))
            is_media = shape.find(".//a:audioFile", NS) is not None or shape.find(".//a:videoFile", NS) is not None
            if blip is not None and blip.get(R_EMBED) in rels and not is_media:
                fill = sp_pr.find("a:blipFill", NS) if tag == "sp" else shape.find("p:blipFill", NS)
                crop = fill.find("a:srcRect", NS) if fill is not None else None
                result.append({"kind": "image", "name": name, "file": self.copy_media(rels[blip.get(R_EMBED)]),
                               "rect": rect, "rot": rot, "flip_h": flip_h, "flip_v": flip_v,
                               "crop": _insets(crop)})
            body = shape.find("p:txBody", NS)
            if body is not None and "".join(t.text or "" for t in body.iter("{%s}t" % NS["a"])).strip():
                result.append(self.text(name, rect, body))
        return result

    def run_style(self, run_pr, paragraph_pr, body_pr) -> dict:
        size = int(run_pr.get("sz", "1800")) / 100 if run_pr is not None else 18.0
        latin = run_pr.find("a:latin", NS) if run_pr is not None else None
        color, alpha = _color(run_pr.find("a:solidFill", NS) if run_pr is not None else None, self.theme)
        style = {
            "font": latin.get("typeface") if latin is not None else "",
            "size": round(size * WIDTH / 1440, 2),        # pt -> Pixel der 1920er-Fläche
            "bold": run_pr is not None and run_pr.get("b") == "1",
            "italic": run_pr is not None and run_pr.get("i") == "1",
            "color": color,
            "alpha": alpha,
            "align": {"ctr": "center", "r": "right", "just": "left"}.get(
                paragraph_pr.get("algn") if paragraph_pr is not None else "", "left"),
            "line_height": None,
        }
        spacing = paragraph_pr.find("a:lnSpc", NS) if paragraph_pr is not None else None
        if spacing is not None:
            points = spacing.find("a:spcPts", NS)
            percent = spacing.find("a:spcPct", NS)
            if points is not None:
                style["line_height"] = round(int(points.get("val")) / 100 * WIDTH / 1440, 2)
            elif percent is not None:
                style["line_height"] = round(style["size"] * 1.2 * int(percent.get("val")) / 100000, 2)
        return style

    def text(self, name, rect, body) -> dict:
        body_pr = body.find("a:bodyPr", NS)
        insets = [int(body_pr.get(k, d)) * self.scale if body_pr is not None else int(d) * self.scale
                  for k, d in (("lIns", 91440), ("tIns", 45720), ("rIns", 91440), ("bIns", 45720))]
        paragraphs = []
        for para in body.findall("a:p", NS):
            runs = para.findall("a:r", NS)
            text = "".join(r.findtext("a:t", default="", namespaces=NS) for r in runs)
            first = next((r for r in runs if (r.findtext("a:t", default="", namespaces=NS) or "").strip()), None)
            style = self.run_style(first.find("a:rPr", NS) if first is not None else para.find("a:endParaRPr", NS),
                                   para.find("a:pPr", NS), body_pr)
            paragraphs.append((text, style))
        main = next((style for text, style in paragraphs if text.strip()), paragraphs[0][1] if paragraphs else
                    self.run_style(None, None, body_pr))
        layer = {"kind": "text", "name": name, "role": "static", "rect": rect,
                 "insets": [round(v, 2) for v in insets],
                 "anchor": {"ctr": "center", "b": "bottom"}.get(body_pr.get("anchor") if body_pr is not None else "", "top"),
                 "text": "\n".join(text for text, _style in paragraphs).strip("\n")}
        layer.update(main)
        layer["_paragraphs"] = paragraphs
        return layer

    # --- Ansichten -----------------------------------------------------
    def scene(self, slide_part: str, kind: str) -> dict:
        layers = self.layers(slide_part)
        texts = [layer for layer in layers if layer["kind"] == "text"]
        if kind == "announcements":
            target = announcement_box(texts)
            if target is not None:
                target["role"] = "announcements"
        elif kind == "verse":
            target = max(texts, key=lambda t: len(t["text"]), default=None)
            if target is not None:
                target["role"] = "verse"
                verse_lines, reference, ref_style = [], "", None
                for text, style in target["_paragraphs"]:
                    if text.startswith("\t") and text.strip():
                        reference, ref_style = text.strip(), style
                    elif text.strip():
                        verse_lines.append(text.strip())
                target["text"] = " ".join(verse_lines)
                if reference:
                    target["reference"] = reference
                    target["reference_style"] = {k: ref_style[k] for k in
                                                 ("font", "size", "bold", "italic", "color", "alpha")}
                    target["reference_align"] = "right"
        elif kind in ("countdown", "end"):
            target = (next((t for t in texts if re.fullmatch(r"\s*\d+\s*", t["text"])), None) if kind == "countdown"
                      else max(texts, key=lambda t: t["size"], default=None))
            if target is not None:
                target["role"] = "number" if kind == "countdown" else "end"
                # Die Zahl steht mittig im (fast quadratischen) Kreis-Bild, falls es eins gibt
                circles = [layer for layer in layers if layer["kind"] == "image"
                           and 0.8 < layer["rect"][2] / max(1, layer["rect"][3]) < 1.25
                           and layer["rect"][2] < WIDTH * 0.9]
                if circles:
                    target["center_in"] = max(circles, key=lambda c: c["rect"][2])["rect"]
                target["align"] = "center"
        for layer in texts:
            layer.pop("_paragraphs", None)
        return {"background": self.background(slide_part), "layers": layers}

    # --- Musik und Schriften --------------------------------------------
    def music(self, slides: list, countdown_index: int, countdown_seconds: int) -> dict:
        for index, part in enumerate(slides):
            root = self.pkg.xml(part)
            link = root.find(".//a:audioFile", NS)
            media = root.find(".//p14:media", NS)
            rels = self.pkg.rels(part)
            target = None
            for candidate in (media.get(R_EMBED) if media is not None else None,
                              link.get(R_LINK) if link is not None else None):
                if candidate in rels and rels[candidate] in self.pkg.names:
                    target = rels[candidate]
                    break
            if target is None:
                continue
            node = root.find(".//p:cMediaNode", NS)
            volume = int(node.get("vol", "100000")) / 100000 if node is not None else 1.0
            start = countdown_seconds - (index - countdown_index) if index >= countdown_index else countdown_seconds
            return {"file": self.copy_media(target), "start_second": max(0, min(countdown_seconds, start)),
                    "volume": round(volume, 2)}
        return {}

    def fonts(self) -> dict:
        """Eingebettete Schriften herauslösen (nur vollständig enthaltene; Teilmengen fehlen sonst Buchstaben)."""
        found = {}
        pres = self.pkg.xml("ppt/presentation.xml")
        rels = self.pkg.rels("ppt/presentation.xml")
        for entry in pres.findall("p:embeddedFontLst/p:embeddedFont", NS):
            face = entry.find("p:font", NS)
            family = face.get("typeface", "") if face is not None else ""
            for style in ("regular", "bold", "italic", "boldItalic"):
                element = entry.find(f"p:{style}", NS)
                if element is None or element.get(R_ID) not in rels:
                    continue
                data = font_from_eot(self.pkg.zip.read(rels[element.get(R_ID)]))
                if data is None:
                    found.setdefault(family, {})[style] = ""
                    continue
                (self.target / "fonts").mkdir(parents=True, exist_ok=True)
                ext = ".otf" if data[:4] == b"OTTO" else ".ttf"
                file = "fonts/" + re.sub(r"[^\w.-]+", "_", f"{family}-{style}") + ext
                with open(self.target / file, "wb") as out:
                    out.write(data)
                found.setdefault(family, {})[style] = file
        return found


def announcement_box(texts: list):
    """Das Textfeld für die Ansagen: zuerst nach Namen („AnsagenTextfeld“, alles mit „Ansage“ außer der Überschrift),
    sonst das Feld mit der kleinsten Schrift – die Überschrift („Ansagen“) ist immer deutlich größer."""
    if not texts:
        return None
    for test in (lambda t: t["name"].strip().lower() == "ansagentextfeld",
                 lambda t: "ansage" in t["name"].lower() and t["text"].strip().lower() != "ansagen"):
        found = [t for t in texts if test(t)]
        if found:
            return found[0]
    candidates = [t for t in texts if t["text"].strip().lower() not in ("ansagen", "ansage")] or texts
    return min(candidates, key=lambda t: (t.get("size", 0), -t["rect"][2] * t["rect"][3]))


def font_from_eot(blob: bytes):
    """TrueType/OpenType-Daten aus einer eingebetteten PowerPoint-Schrift (.fntdata = EOT). ``None``, wenn die Schrift
    komprimiert (MicroType) oder nur als Teilmenge eingebettet ist – dann muss sie auf dem Rechner installiert sein."""
    if len(blob) < 82:
        return None
    eot_size, data_size, _version, flags = struct.unpack("<IIII", blob[:16])
    if struct.unpack("<H", blob[34:36])[0] != 0x504C or data_size > len(blob):
        return None
    if flags & 0x1 or flags & 0x4:                     # Teilmenge bzw. MicroType-komprimiert
        return None
    data = bytearray(blob[len(blob) - data_size:] if eot_size == len(blob) else blob[-data_size:])
    if flags & 0x10000000:                             # mit 0x50 verschlüsselt
        data = bytearray(b ^ 0x50 for b in data)
    if bytes(data[:4]) not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        return None
    return bytes(data)


def import_pptx(pptx_path, season: str) -> dict:
    """Liest die Vorlage ein und speichert das Design der Jahreszeit (ersetzt ein vorhandenes). Gibt das Design zurück.
    Eigene Einstellungen (Zeiten, Bibelvers) aus einem vorhandenen Design bleiben erhalten, wenn ``keep``-Felder gesetzt sind."""
    target = design_dir(season)
    staging = target.with_name(target.name + ".neu")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        importer = _Importer(pptx_path, staging)
        slides = _slide_parts(importer.pkg)
        if len(slides) < 3:
            raise ImportProblem("Die Vorlage braucht mindestens 3 Folien: Ansagen, Bibelvers und Countdown.")
        countdown_index = 2
        countdown_slide = importer.pkg.xml(slides[countdown_index])
        number = "".join(t.text or "" for t in countdown_slide.iter("{%s}t" % NS["a"])).strip()
        countdown_seconds = int(number) if number.isdigit() and 1 <= int(number) <= 600 else 60
        design = {
            "version": VERSION,
            "source": Path(pptx_path).name,
            "size": [WIDTH, HEIGHT],
            "scenes": {
                "announcements": importer.scene(slides[0], "announcements"),
                "verse": importer.scene(slides[1], "verse"),
                "countdown": importer.scene(slides[countdown_index], "countdown"),
                "end": importer.scene(slides[-1], "end") if len(slides) > 3 else
                       importer.scene(slides[countdown_index], "end"),
            },
            "timing": {"verse_minutes": DEFAULT_TIMING["verse_minutes"], "countdown_seconds": countdown_seconds},
            # Der Puls in der Vorlage ist ein Klick-Effekt – beim Weiterschalten der Folien läuft er nie. 1:1 heißt also:
            # die Zahl wechselt einfach (in den Einstellungen lässt sich ein dezentes Pulsieren einschalten)
            "pulse": False,
            "music": importer.music(slides, countdown_index, countdown_seconds),
            "fonts": importer.fonts(),
        }
        verse = text_layer(design, "verse", "verse")
        if verse is not None:
            design["verse_text"] = verse.get("text", "")
            design["verse_reference"] = verse.get("reference", "")
        old = load(season)
        if old:                                         # eigene Einstellungen behalten
            design["timing"] = old.get("timing", design["timing"])
            if int(old.get("version", 1)) >= 3:
                design["pulse"] = old.get("pulse", design["pulse"])
            for key in ("verse_text", "verse_reference"):
                if old.get(key):
                    design[key] = old[key]
            old_music = old.get("music") or {}
            if design.get("music") and old_music:
                for key in ("start_second", "volume"):
                    if key in old_music:
                        design["music"][key] = old_music[key]
        save_staging = staging / DESIGN_FILE
        with open(save_staging, "w", encoding="utf-8") as handle:
            json.dump(design, handle, ensure_ascii=False, indent=1)
    except ImportProblem:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except (KeyError, ET.ParseError, ValueError, OSError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise ImportProblem(f"Die Vorlage ließ sich nicht einlesen ({exc}).") from exc
    shutil.rmtree(target, ignore_errors=True)
    staging.replace(target)
    return load(season)


def missing_fonts(design: dict) -> list:
    """Schriften, die das Design braucht, aber nicht vollständig mitbringt (müssen installiert sein)."""
    needed = set()
    for scene in (design.get("scenes") or {}).values():
        for layer in scene.get("layers", []):
            if layer.get("kind") == "text" and layer.get("font"):
                needed.add(layer["font"])
                ref = layer.get("reference_style") or {}
                if ref.get("font"):
                    needed.add(ref["font"])
    bundled = {family for family, styles in (design.get("fonts") or {}).items() if any(styles.values())}
    return sorted(needed - bundled)
