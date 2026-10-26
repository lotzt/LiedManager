"""Liest CCLI-Nummern aus den Liederbüchern von evangeliums.net und trägt sie direkt in die LiedManager-Datenbank ein.

Aufruf (im LiedManager-Ordner, LiedManager vorher beenden):   python3 tools/ccli_aus_liederbuch.py
Die Datenbank wird automatisch gesucht; sonst:   python3 tools/ccli_aus_liederbuch.py --db "/Pfad/zu/LiedManager.db"

Bücher und ihre Liednummern in der Datenbank:
    Glaubenslieder 2015 und 2024   Präfix p   (p012)
    Glaubenslieder 1 und 2         kein Präfix (12)
    Feiert Jesus – Best of         Präfix s   (s012)

So geht das Skript vor:
* Es lädt die Inhaltsseiten der Bücher und sucht zu jedem Lied der Datenbank das passende Lied im Buch:
  über Präfix und Nummer – aber nur, wenn auch der Titel dazu passt – sonst über den gleichen Titel.
  Lieder ohne Titel werden übersprungen (ohne Titel lässt sich nichts prüfen).
* Nur die Liedseiten, die wirklich gebraucht werden, werden geladen (dort steht unter „Informationen zum Lied“ die
  „CCLI-Nr.“). Mehrere Seiten werden gleichzeitig geladen, mit Pause je Anfrage (Standard: 3 Verbindungen, 1 s).
* Die Nummern landen in der Spalte der Datenbank, deren Name „ccli“ enthält (fehlt sie, wird „CCLI“ angelegt).
  Bereits eingetragene Nummern werden nie überschrieben. Vor der ersten Änderung entsteht eine Sicherungskopie
  („…db.vor-ccli.bak“). Zwischenstände werden gespeichert; bei Abbruch einfach erneut starten.
* Ergebnisse im LiedManager-Datenordner: „Buecher-CCLI.csv“ (was gefunden wurde) und „CCLI-Nummern-offen.txt“
  (Lieder ohne Nummer samt Grund).
Nur die Standardbibliothek. Bitte freundlich bleiben: Pause nicht auf unter 0,5 s stellen.
"""
import argparse
import csv
import html
import json
import re
import shutil
import sqlite3
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

BASE = "https://www.evangeliums.net/lieder/"
BOOKS = (
    # Name, Inhaltsseite, Präfixe der Liednummer in der Datenbank
    ("Glaubenslieder 2015", BASE + "liederbuch_glaubenslieder_2015.html", ("p",)),
    ("Glaubenslieder 2024", BASE + "liederbuch_glaubenslieder_2024.html", ("p",)),
    ("Glaubenslieder 1", BASE + "liederbuch_glaubenslieder.html", ("",)),
    ("Glaubenslieder 2", BASE + "liederbuch_glaubenslieder_2.html", ("",)),
    ("Feiert Jesus – Best of", BASE + "liederbuch_feiert_jesus_best_of.html", ("s",)),
)
HEADERS = {"User-Agent": "LiedManager-CCLI-Helfer (privat, wenige Anfragen pro Sekunde)"}
LINK = re.compile(r'<a\s[^>]*href="(?P<href>(?:https?://www\.evangeliums\.net/lieder/|/lieder/)?lied_[^"#?]+\.html)"[^>]*>(?P<text>.*?)</a>',
                  re.I | re.S)
CCLI = re.compile(r"CCLI-?\s*(?:Nr|Nummer|Liednummer)\.?\s*:?\s*(\d{4,9})", re.I)
TAG = re.compile(r"<[^>]+>")
ROW_NUMBER = re.compile(r"^([a-z]?)\s*0*(\d+)$", re.I)       # p012 -> ("p", 12), 12 -> ("", 12)
TITLE_RATIO = 0.7


def _ssl_context():
    """Zertifikate aus certifi (falls installiert – wie im Programm), sonst die des Systems."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


CONTEXT = _ssl_context()


def fetch(url: str, retries: int = 3) -> str:
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=30, context=CONTEXT) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
        except (urllib.error.URLError, OSError) as exc:
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                print("\nDie Zertifikate von Python fehlen. Lösung auf dem Mac (einmalig):\n"
                      "  python3 -m pip install certifi        und danach das Skript erneut starten,\n"
                      "oder im Ordner Programme/Python 3.x die Datei „Install Certificates.command“ doppelklicken.")
                raise SystemExit(1)
            if attempt == retries:
                raise
            time.sleep(5 * attempt)
    return ""


def text_of(fragment: str) -> str:
    return " ".join(html.unescape(TAG.sub(" ", fragment)).split())


def parse_toc(page: str):
    """Liste aus (Nummer oder '', Titel, Adresse) in der Reihenfolge der Seite. Die Nummer steht vor dem Link in derselben Zeile."""
    entries, seen = [], set()
    for match in LINK.finditer(page):
        href = match.group("href")
        url = href if href.startswith("http") else "https://www.evangeliums.net" + href if href.startswith("/") else BASE + href
        if url in seen:
            continue
        title = text_of(match.group("text"))
        if not title:
            continue
        seen.add(url)
        before = page[max(0, match.start() - 160):match.start()]
        number = re.search(r"(\d{1,3})\s*(?:</[^>]+>\s*)*(?:<[^>]+>\s*)*$", before)
        entries.append((number.group(1) if number else "", title, url))
    return entries


def parse_ccli(page: str) -> str:
    match = CCLI.search(text_of(page))
    return match.group(1) if match else ""


def normalize(title: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", "", str(title).lower()).split())


def title_score(a: str, b: str) -> float:
    """Ähnlichkeit zweier Titel: 1.0 = gleich (ohne Satzzeichen/Groß-Klein), 0.9 = einer steckt im anderen, sonst Textähnlichkeit."""
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def match_row(number: str, title: str, books: list):
    """Sucht zu einer Zeile (Liednummer, Titel) den Eintrag im Liederbuch. ``books``: [(Name, Präfixe, Einträge)].
    Zuerst gleicher Titel (steht die Nummer im selben Buch, wird dieses bevorzugt), sonst Präfix + Nummer, wenn der Titel
    dazu passt (das beste von mehreren Büchern). Gibt (Buch, Nr, Titel, Adresse) oder None zurück; ohne Titel nie."""
    if not normalize(title):
        return None
    parsed = ROW_NUMBER.match(number.strip())
    prefix, value = (parsed.group(1).lower(), int(parsed.group(2))) if parsed else (None, None)

    def same_number(prefixes, nr):
        return prefix is not None and prefix in prefixes and nr.isdigit() and int(nr) == value

    exact = [(name, nr, entry_title, url, same_number(prefixes, nr))
             for name, prefixes, entries in books for nr, entry_title, url in entries
             if normalize(entry_title) == normalize(title)]
    if exact:
        best = next((e for e in exact if e[4]), exact[0])
        return best[:4]
    best, best_score = None, 0.0
    for name, prefixes, entries in books:
        for nr, entry_title, url in entries:
            if same_number(prefixes, nr):
                score = title_score(title, entry_title)
                if score > best_score:
                    best, best_score = (name, nr, entry_title, url), score
    return best if best_score >= TITLE_RATIO else None


def default_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LiedManager"
    if sys.platform.startswith("win"):
        import os
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "LiedManager"
    return Path.home() / ".local" / "share" / "LiedManager"


def find_db(given: Path = None) -> Path:
    """Die Datenbank: angegebener Pfad, sonst LiedManager.db im aktuellen Ordner, neben dem Skript oder im Datenordner."""
    if given:
        return given
    here = Path(__file__).resolve().parent
    for folder in (Path.cwd(), here.parent, here, default_data_dir()):
        if (folder / "LiedManager.db").exists():
            return folder / "LiedManager.db"
    return None


def read_rows(conn):
    """Liste aus [rowid, Liednummer, Titel, CCLI] und Name der CCLI-Spalte (leer, wenn es noch keine gibt)."""
    column = next((str(r[1]) for r in conn.execute("PRAGMA table_info(Data)") if "ccli" in str(r[1]).lower()), "")
    select = "rowid, nummer, titel" + (f', "{column}"' if column else ", NULL")
    rows = [[rowid, "" if nummer is None else str(nummer), "" if titel in (None, "None") else str(titel),
             clean_ccli(ccli)] for rowid, nummer, titel, ccli in conn.execute(f"SELECT {select} FROM Data ORDER BY rowid")]
    return rows, column


def clean_ccli(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def load_books(selection=None):
    books = []
    for name, toc, prefixes in BOOKS:
        if selection and not any(s.lower() in name.lower() for s in selection):
            continue
        print(f"Lade Inhaltsseite: {name} …")
        entries = parse_toc(fetch(toc))
        print(f"  {len(entries)} Lieder")
        books.append((name, prefixes, entries))
    return books


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=3, help="gleichzeitige Verbindungen (1–6)")
    parser.add_argument("--delay", type=float, default=1.0, help="Pause je Verbindung zwischen zwei Anfragen in Sekunden")
    parser.add_argument("--db", type=Path, default=None, help="Pfad zur Datenbank LiedManager.db (sonst wird gesucht)")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir(), help="Ordner für Zwischenstand und Ergebnisse")
    parser.add_argument("--limit", type=int, default=0, help="nur N Liedseiten laden (zum Ausprobieren)")
    parser.add_argument("--buch", action="append", help="nur Bücher, deren Name dies enthält (mehrfach möglich)")
    args = parser.parse_args()
    workers, delay = max(1, min(6, args.workers)), max(0.5, args.delay)

    db_path = find_db(args.db)
    if db_path is None or not db_path.exists():
        print("Die Datenbank wurde nicht gefunden. Bitte mit --db \"/Pfad/zu/LiedManager.db\" angeben.")
        return 1
    conn = sqlite3.connect(str(db_path), timeout=30)
    rows, ccli_column = read_rows(conn)
    print(f"Datenbank: {db_path} ({len(rows)} Lieder)")
    books = load_books(args.buch)
    if not any(entries for _n, _p, entries in books):
        print("Auf den Inhaltsseiten wurden keine Lieder gefunden – die Seiten haben sich vermutlich geändert.")
        return 1

    # 1) Zuordnung: Zeile der Liste -> Liedseite
    assigned, reasons = {}, {}
    for index, row in enumerate(rows):
        if not row[1].strip() or row[3]:
            continue                                         # ohne Nummer oder schon eine CCLI-Nummer eingetragen
        found = match_row(row[1], row[2], books)
        if found:
            assigned[index] = found
        else:
            reasons[index] = "kein Titel eingetragen" if not normalize(row[2]) else "nicht in den Büchern gefunden"
    urls = sorted({found[3] for found in assigned.values()})
    print(f"\n{len(assigned)} Lieder zugeordnet, {len(urls)} Liedseiten zu laden.")

    # 2) Seiten laden (mehrere gleichzeitig, mit Zwischenstand)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    cache_file = args.data_dir / "ccli_liederbuch_zwischenstand.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    todo = [url for url in urls if url not in cache]
    if args.limit:
        todo = todo[:args.limit]
    lock, counter = threading.Lock(), [0]

    def work(url: str) -> None:
        ccli = parse_ccli(fetch(url))
        with lock:
            cache[url] = ccli
            counter[0] += 1
            cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"[{counter[0]}/{len(todo)}] {url.rsplit('/', 1)[-1]} → {ccli or 'keine Nummer'}")
        time.sleep(delay)

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(work, todo))
    except KeyboardInterrupt:
        print("Abgebrochen – Zwischenstand ist gespeichert, einfach erneut starten.")
        return 130

    # 3) In die Datenbank eintragen und Ergebnisse schreiben
    updates, result_lines = [], []
    for index, (book, nr, title, url) in assigned.items():
        ccli = cache.get(url, "")
        if ccli:
            updates.append((ccli, rows[index][0]))
            result_lines.append((rows[index][1], rows[index][2], book, nr, ccli, url))
        elif url in cache:
            reasons[index] = f"{book}: auf der Website keine CCLI-Nummer"
        else:
            reasons[index] = f"{book}: noch nicht geladen (--limit?)"
    if updates:
        backup = Path(str(db_path) + ".vor-ccli.bak")
        if not backup.exists():
            shutil.copy2(str(db_path), str(backup))
            print(f"Sicherungskopie: {backup}")
        with conn:
            if not ccli_column:
                conn.execute("ALTER TABLE Data ADD COLUMN CCLI TEXT")
                ccli_column = "CCLI"
            conn.executemany(f'UPDATE Data SET "{ccli_column}" = ? WHERE rowid = ?', updates)
    conn.close()
    filled = len(updates)
    with open(args.data_dir / "Buecher-CCLI.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(("Liednummer", "Titel", "Buch", "Nr im Buch", "CCLI-Nr", "Adresse"))
        writer.writerows(result_lines)
    if reasons:
        lines = [f"{rows[i][1]} {rows[i][2]} – {why}".strip() for i, why in sorted(reasons.items())]
        (args.data_dir / "CCLI-Nummern-offen.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nFertig. {filled} CCLI-Nummern in die Datenbank eingetragen, {len(reasons)} Lieder weiter ohne Nummer"
          f" (Liste mit Gründen: {args.data_dir / 'CCLI-Nummern-offen.txt'}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
