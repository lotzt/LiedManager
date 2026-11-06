"""Erzeugt die Beispiel-Datenbank ``beispiel/LiedManager-Beispiel.db`` mit einigen gemeinfreien Liedern.

Zum Ausprobieren für neue Gemeinden: Suche, Beamer-Bild (je Lied ein Bild mit dem Text), Verweis-Nummer und eine
leere CCLI-Spalte. Audio enthält die Beispiel-Datenbank nicht. Die Texte sind gemeinfrei (vor 1900 entstanden).

Aufruf:  python tools/make_example_db.py        (braucht Pillow:  pip install Pillow)
"""
import io
import sqlite3
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "beispiel" / "LiedManager-Beispiel.db"
FONT = next((ROOT / "ui" / "assets" / "fonts").glob("Fraunces*.ttf"))
SIZE = (1920, 1080)

SONGS = [
    ("1", "Großer Gott, wir loben dich", "Ignaz Franz, 1771", [
        "Großer Gott, wir loben dich;\nHerr, wir preisen deine Stärke.\nVor dir neigt die Erde sich\n"
        "und bewundert deine Werke.\nWie du warst vor aller Zeit,\nso bleibst du in Ewigkeit.",
        "Alles, was dich preisen kann,\nCherubim und Seraphinen,\nstimmen dir ein Loblied an;\n"
        "alle Engel, die dir dienen,\nrufen dir stets ohne Ruh:\n„Heilig, heilig, heilig!“ zu."]),
    ("2", "Lobe den Herren", "Joachim Neander, 1680", [
        "Lobe den Herren, den mächtigen König der Ehren,\nmeine geliebete Seele, das ist mein Begehren.\n"
        "Kommet zuhauf,\nPsalter und Harfe, wacht auf,\nlasset den Lobgesang hören!"]),
    ("3", "Nun danket alle Gott", "Martin Rinckart, 1636", [
        "Nun danket alle Gott\nmit Herzen, Mund und Händen,\nder große Dinge tut\nan uns und allen Enden,\n"
        "der uns von Mutterleib\nund Kindesbeinen an\nunzählig viel zugut\nbis hierher hat getan."]),
    ("4", "Befiehl du deine Wege", "Paul Gerhardt, 1653", [
        "Befiehl du deine Wege\nund was dein Herze kränkt\nder allertreusten Pflege\ndes, der den Himmel lenkt.\n"
        "Der Wolken, Luft und Winden\ngibt Wege, Lauf und Bahn,\nder wird auch Wege finden,\nda dein Fuß gehen kann."]),
    ("5", "So nimm denn meine Hände", "Julie Hausmann, 1862", [
        "So nimm denn meine Hände\nund führe mich\nbis an mein selig Ende\nund ewiglich.\n"
        "Ich mag allein nicht gehen,\nnicht einen Schritt;\nwo du wirst gehn und stehen,\nda nimm mich mit."]),
    ("b1", "Ein feste Burg ist unser Gott", "Martin Luther, 1529", [
        "Ein feste Burg ist unser Gott,\nein gute Wehr und Waffen.\nEr hilft uns frei aus aller Not,\n"
        "die uns jetzt hat betroffen."]),
]
ALIASES = [("100", "1", "Großer Gott, wir loben dich")]   # Verweis: Nummer 100 zeigt Lied 1


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), size)


def render(title: str, stanzas: list) -> bytes:
    """Ein Bild je Lied: Titel oben, darunter die Strophen (weiße Schrift auf Schwarz, wie auf dem Beamer üblich)."""
    image = Image.new("RGB", SIZE, "black")
    draw = ImageDraw.Draw(image)
    text = "\n\n".join(f"{n}. {s}" if len(stanzas) > 1 else s for n, s in enumerate(stanzas, 1))
    size = 64
    while size > 24:                                    # so groß wie möglich, aber alles passt aufs Bild
        box = draw.multiline_textbbox((0, 0), text, font=font(size), spacing=size // 3)
        if box[2] - box[0] <= SIZE[0] - 200 and box[3] - box[1] <= SIZE[1] - 260:
            break
        size -= 2
    draw.text((SIZE[0] / 2, 90), title, font=font(52), fill="#C9A27A", anchor="mm")
    box = draw.multiline_textbbox((0, 0), text, font=font(size), spacing=size // 3)
    x = (SIZE[0] - (box[2] - box[0])) / 2
    y = 170 + (SIZE[1] - 230 - (box[3] - box[1])) / 2
    draw.multiline_text((x, y), text, font=font(size), fill="white", spacing=size // 3)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def main() -> int:
    TARGET.parent.mkdir(exist_ok=True)
    if TARGET.exists():
        TARGET.unlink()
    con = sqlite3.connect(TARGET)
    con.execute("CREATE TABLE Data (nummer TEXT, alias TEXT, titel TEXT, lyrics TEXT, audio1 BLOB, audio2 BLOB, "
                "bild1 BLOB, bild2 BLOB, bild3 BLOB, bild4 BLOB, CCLI TEXT)")
    for number, title, _author, stanzas in SONGS:
        con.execute("INSERT INTO Data (nummer, alias, titel, lyrics, bild1) VALUES (?, NULL, ?, ?, ?)",
                    (number, title, "\n\n".join(stanzas), render(title, stanzas)))
    for number, alias, title in ALIASES:
        con.execute("INSERT INTO Data (nummer, alias, titel) VALUES (?, ?, ?)", (number, alias, title))
    con.commit()
    con.execute("VACUUM")
    con.close()
    print(f"Beispiel-Datenbank geschrieben: {TARGET} ({TARGET.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
