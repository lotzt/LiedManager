"""Liste der gespielten Lieder: eine einzige Textdatei „Gespielte Lieder.txt“, in die immer weiter eingetragen wird.

Pro Tag steht eine Kopfzeile mit Wochentag und Datum („Sonntag, 18.10.2026“), darunter je Lied „Nummer – Titel“ (sonst nichts).
Aufgenommen wird ein Lied, sobald es auf dem Beamer gezeigt wird. Dasselbe Lied direkt nacheinander steht nur einmal in der
Liste. Im Testmodus (Einstellungen → Anzeige) wird nichts gespeichert.

Lieder aus Zeiten ohne CCLI-Meldung (Einstellungen → Remote → CCLI-Meldung, Standard: sonntags 9–10 Uhr, mittwochs 18:30–19:30 Uhr)
stehen mit dem Zusatz „[nicht melden]“ in der Liste: Sie bleiben in der Liedhistorie, kommen aber nicht in die CCLI-Meldung.
"""
import datetime
import logging
import re
from pathlib import Path

from paths import user_data_dir
from services.settings import app_settings

log = logging.getLogger(__name__)

KEY_ENABLED = "songlog_enabled"
KEY_TEST_MODE = "songlog_test_mode"

NO_REPORT_MARK = "[nicht melden]"
KEY_NO_REPORT = "ccli_no_report_windows"
# (Wochentag 0 = Montag … 6 = Sonntag, von, bis) – in diesen Zeiten gespielte Lieder werden nicht bei CCLI gemeldet
NO_REPORT_WINDOWS = (
    (6, datetime.time(9, 0), datetime.time(10, 0)),       # Sonntag 9:00–10:00
    (2, datetime.time(18, 30), datetime.time(19, 30)),    # Mittwoch 18:30–19:30
)
_DAY_SHORT = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
_WINDOW = re.compile(r"^\s*([A-Za-zÄÖÜäöü]+)\.?\s+(\d{1,2})[:.](\d{2})\s*[-–]\s*(\d{1,2})[:.](\d{2})\s*(?:uhr)?\s*$", re.IGNORECASE)

WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")   # unabhängig von der Systemsprache
_HEADER = re.compile(r"^(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag), \d{2}\.\d{2}\.\d{4}$")


def songlog_dir() -> Path:
    path = user_data_dir() / "Gespielte Lieder"
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_enabled() -> bool:
    return app_settings().value(KEY_ENABLED, True, type=bool)


def is_test_mode() -> bool:
    return app_settings().value(KEY_TEST_MODE, False, type=bool)


def is_recording() -> bool:
    return is_enabled() and not is_test_mode()


def format_entry(nummer, titel) -> str:
    number = str(nummer).strip()
    title = " ".join(str(titel or "").split())
    return f"{number} – {title}" if title and title != "None" else number


def file_path() -> Path:
    return songlog_dir() / "Gespielte Lieder.txt"


def format_day(day: datetime.date) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m.%Y')}"


def format_windows(windows) -> str:
    """[(6, 9:00, 10:00), …] -> „So 09:00–10:00; Mi 18:30–19:30“."""
    return "; ".join(f"{_DAY_SHORT[d]} {a.strftime('%H:%M')}–{b.strftime('%H:%M')}" for d, a, b in windows)


def parse_windows(text: str) -> list:
    """„So 9:00-10:00; Mi 18:30–19:30“ -> Liste von (Wochentag, von, bis). Leer = keine Zeitfenster.
    Wochentage als Kürzel oder ausgeschrieben (Mo/Montag …). Wirft ``ValueError`` mit verständlicher Meldung."""
    windows = []
    for part in re.split(r"[;\n]+", text or ""):
        if not part.strip():
            continue
        match = _WINDOW.match(part)
        if not match:
            raise ValueError(f"„{part.strip()}“ verstehe ich nicht. Beispiel: So 09:00–10:00")
        name = match.group(1).lower()[:2]
        days = [d.lower() for d in _DAY_SHORT]
        if name not in days:
            raise ValueError(f"Unbekannter Wochentag in „{part.strip()}“ (Mo, Di, Mi, Do, Fr, Sa, So)")
        try:
            start = datetime.time(int(match.group(2)), int(match.group(3)))
            end = datetime.time(int(match.group(4)), int(match.group(5)))
        except ValueError:
            raise ValueError(f"Ungültige Uhrzeit in „{part.strip()}“") from None
        if end < start:
            raise ValueError(f"In „{part.strip()}“ liegt das Ende vor dem Anfang")
        windows.append((days.index(name), start, end))
    return windows


def no_report_windows() -> list:
    """Die eingestellten Zeitfenster (fehlerhafte Einstellung -> Standard)."""
    text = app_settings().value(KEY_NO_REPORT, None)
    if text is None:
        return list(NO_REPORT_WINDOWS)
    try:
        return parse_windows(str(text))
    except ValueError:
        return list(NO_REPORT_WINDOWS)


def is_no_report_time(moment: datetime.datetime, windows=None) -> bool:
    """Liegt der Zeitpunkt in einem Zeitfenster ohne CCLI-Meldung (Grenzen eingeschlossen)?"""
    now = moment.time()
    windows = no_report_windows() if windows is None else windows
    return any(moment.weekday() == day and start <= now <= end for day, start, end in windows)


def is_no_report(line: str) -> bool:
    return line.rstrip().endswith(NO_REPORT_MARK)


def strip_mark(text: str) -> str:
    return text.replace(NO_REPORT_MARK, "").rstrip()


def record(nummer, titel, when: datetime.date = None, at: datetime.datetime = None) -> bool:
    """Trägt das Lied unter dem heutigen Datum ein. Gibt ``True`` zurück, wenn eine Zeile geschrieben wurde.
    ``at``: Zeitpunkt für die Prüfung der Zeitfenster ohne CCLI-Meldung (Standard: jetzt; mit ``when`` ohne ``at`` keine Prüfung)."""
    if not is_recording():
        return False
    line = format_entry(nummer, titel)
    if not line:
        return False
    if at is None and when is None:
        at = datetime.datetime.now()
    if at is not None and is_no_report_time(at):
        line += f"  {NO_REPORT_MARK}"
        when = when or at.date()
    header = format_day(when or datetime.date.today())
    path = file_path()
    try:
        old = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        old = [row for row in old if row.strip()]
        last_header = next((row for row in reversed(old) if _HEADER.match(row)), None)
        if last_header == header and old and old[-1] == line:
            return False                                    # dasselbe Lied direkt nochmal
        text = ""
        if last_header != header:
            text += ("\r\n" if old else "") + header + "\r\n"    # neuer Tag: Leerzeile und Kopfzeile
        text += line + "\r\n"                                 # \r\n: der Windows-Editor zeigt Umbrüche nur so richtig an
        with open(path, "a", encoding="utf-8", newline="") as f:
            f.write(text)
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("Gespieltes Lied konnte nicht gespeichert werden: %s", exc)
        return False
    return True
