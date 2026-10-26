"""CCLI-Meldetabelle aus der Liste der gespielten Lieder.

Die CCLI-Nummern stehen in einer Spalte der Datenbank (Name enthält „ccli“) und werden mit dem Datenbank-Abgleich geteilt.
Aus der Liste der gespielten Lieder entsteht „CCLI-Meldung.csv“ – nur die noch offenen CCLI-Nummern, eine pro Zeile, keine
Titel oder Liednummern. Gemeldete Nummern werden sofort daraus entfernt; ist alles gemeldet, wird die Datei gelöscht.
Bereits Gemeldetes wird nirgends aufbewahrt. „Gespielte Lieder.txt“ (Liedhistorie) bleibt unverändert; welche Zeilen schon in
der Meldeliste gelandet sind, merkt sich das Programm (Einstellung ``ccli_log_lines``), damit nichts doppelt gemeldet wird.
"""
import re
import sqlite3
from pathlib import Path

from paths import user_data_dir
from services import songlog

KEY_LOG_LINES = "ccli_log_lines"     # so viele Zeilen von „Gespielte Lieder.txt“ sind schon in der Meldeliste
LEGACY_FILES = ("CCLI-Meldung-Ergebnis.csv", "Gespielte Lieder (gemeldet).txt")   # früher angelegt, nicht mehr nötig

_DAY = re.compile(r"^(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag), (\d{2}\.\d{2}\.\d{4})$")


def report_path() -> Path:
    return user_data_dir() / "CCLI-Meldung.csv"


def _key(nummer) -> str:
    return str(nummer).lower().replace(" ", "")


def _clean_ccli(value) -> str:
    """CCLI-Nummern bestehen nur aus Ziffern; Leerzeichen und Zusätze wie „CCLI“ werden entfernt."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def find_column(conn) -> str:
    """Name der Spalte für die CCLI-Nummer in der Tabelle „Data“ (jede Spalte, deren Name „ccli“ enthält), sonst leer."""
    for row in conn.execute("PRAGMA table_info(Data)"):
        if "ccli" in str(row[1]).lower():
            return str(row[1])
    return ""


def numbers_from_db(db_path) -> dict:
    """Liednummer (klein, ohne Leerzeichen) -> CCLI-Nummer aus der Datenbankspalte. Ohne Spalte oder Datenbank: leer."""
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        try:
            column = find_column(conn)
            if not column:
                return {}
            rows = conn.execute(f'SELECT nummer, "{column}" FROM Data').fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return {}
    return {_key(nummer): _clean_ccli(value) for nummer, value in rows if nummer is not None and _clean_ccli(value)}


def _entries(lines, start: int = 0):
    """(Wochentag, Datum, Nummer, Titel) aller Einträge ab Zeile ``start`` (die Tages-Kopfzeile davor zählt mit)."""
    entries, weekday, date = [], "", ""
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        match = _DAY.match(line)
        if match:
            weekday, date = match.group(1), match.group(2)
            continue
        if index >= start and not songlog.is_no_report(line):      # „[nicht melden]“: Zeitfenster ohne CCLI-Meldung
            number, _, title = line.partition(" – ")
            entries.append((weekday, date, number.strip(), title.strip()))
    return entries


def parse_log(text: str):
    """Liest „Gespielte Lieder.txt“: Liste aus (Wochentag, Datum, Nummer, Titel)."""
    return _entries(text.splitlines())


def remove_legacy_files(folder: Path = None) -> None:
    """Räumt Dateien früherer Versionen weg (Ergebnisliste und Archiv der schon gemeldeten Lieder)."""
    folder = folder or user_data_dir()
    for name in LEGACY_FILES:
        try:
            (folder / name).unlink(missing_ok=True)
        except OSError:
            pass


def read_report(path: Path = None) -> list:
    """Die noch zu meldenden CCLI-Nummern (eine pro Zeile)."""
    path = path or report_path()
    if not path.exists():
        return []
    return [n for n in (_clean_ccli(line) for line in path.read_text(encoding="utf-8-sig").splitlines()) if n]


def write_report(numbers, path: Path = None) -> None:
    """Schreibt die offenen Nummern; ohne offene Nummern wird die Datei gelöscht."""
    path = path or report_path()
    numbers = [n for n in (_clean_ccli(x) for x in numbers) if n]
    if not numbers:
        path.unlink(missing_ok=True)
        return
    path.write_text("".join(f"{n}\r\n" for n in numbers), encoding="utf-8")


def _settings():
    from services.settings import app_settings
    return app_settings()


def export_report(db_path=None, log_path: Path = None, numbers: dict = None, out_path: Path = None, store=None):
    """Übernimmt neu gespielte Lieder als CCLI-Nummern in die Meldeliste (hinter noch offene). „Gespielte Lieder.txt“ bleibt
    unverändert; ``store`` (Standard: Programmeinstellungen) merkt sich, bis zu welcher Zeile schon übernommen wurde.
    Gibt (Pfad, Anzahl offener Nummern, Anzahl neuer Lieder ohne CCLI-Nummer) zurück."""
    log_path = log_path or songlog.file_path()
    out_path = out_path or report_path()
    store = store if store is not None else _settings()
    if numbers is None:
        numbers = numbers_from_db(db_path) if db_path else {}
    lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    try:
        done = int(store.value(KEY_LOG_LINES, 0))
    except (TypeError, ValueError):
        done = 0
    if done > len(lines):                              # Datei wurde geleert/ersetzt: wieder von vorn
        done = 0
    missing, found, seen = 0, [], set()
    for _weekday, date, number, _title in _entries(lines, done):
        ccli = numbers.get(_key(number), "")
        missing += not ccli
        if ccli and (date, ccli) not in seen:          # dasselbe Lied am selben Tag wird nur einmal gemeldet
            seen.add((date, ccli))
            found.append(ccli)
    pending = read_report(out_path) + found
    write_report(pending, out_path)
    store.setValue(KEY_LOG_LINES, len(lines))
    return out_path, len(pending), missing
