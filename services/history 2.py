"""Liedhistorie: liest die Datei „Gespielte Lieder.txt“ (siehe songlog) als Liste nach Tagen, neueste zuerst."""
import datetime
import logging
import re

from services import songlog

log = logging.getLogger(__name__)

_ENTRY = re.compile(r"^(?P<nr>\S+?)(?:\s+[–-]\s+(?P<title>.*))?$")
_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})$")


def read(path=None) -> list:
    """[(Kopfzeile, datetime.date | None, [(Nummer, Titel), …]), …], neueste Tage zuerst."""
    path = path or songlog.file_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    days, current = [], None
    for raw in lines:
        row = raw.strip()
        if not row:
            continue
        if songlog._HEADER.match(row):
            m = _DATE.search(row)
            try:
                day = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except (ValueError, AttributeError):
                day = None
            current = (row, day, [])
            days.append(current)
            continue
        m = _ENTRY.match(songlog.strip_mark(row))     # „[nicht melden]“ gehört nicht zum Titel
        if m is None:
            continue
        if current is None:
            current = ("Ohne Datum", None, [])
            days.append(current)
        current[2].append((m.group("nr"), (m.group("title") or "").strip()))
    return list(reversed(days))


def filter_days(days: list, text: str) -> list:
    """Nur Lieder, deren Nummer oder Titel (oder Tag) den Suchtext enthalten."""
    needle = " ".join(text.lower().split())
    if not needle:
        return days
    result = []
    for header, day, entries in days:
        if needle in header.lower():
            result.append((header, day, entries))
            continue
        hits = [e for e in entries if needle in e[0].lower() or needle in e[1].lower()]
        if hits:
            result.append((header, day, hits))
    return result


def top_songs(days: list, limit: int = 10) -> list:
    """Am häufigsten gespielt: [(Nummer, Titel, Anzahl), …]."""
    counts = {}
    for _h, _d, entries in days:
        for nr, title in entries:
            old = counts.get(nr, (title, 0))
            counts[nr] = (title or old[0], old[1] + 1)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1][1], kv[0]))
    return [(nr, title, count) for nr, (title, count) in ranked[:limit]]
