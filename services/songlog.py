"""Liste der gespielten Lieder: eine einzige Textdatei „Gespielte Lieder.txt“, in die immer weiter eingetragen wird.

Pro Tag steht eine Kopfzeile mit Wochentag und Datum („Sonntag, 18.10.2026“), darunter je Lied „Nummer – Titel“ (sonst nichts).
Aufgenommen wird ein Lied, sobald es auf dem Beamer gezeigt wird. Dasselbe Lied direkt nacheinander steht nur einmal in der
Liste. Im Testmodus (Einstellungen → Anzeige) wird nichts gespeichert.
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


def record(nummer, titel, when: datetime.date = None) -> bool:
    """Trägt das Lied unter dem heutigen Datum ein. Gibt ``True`` zurück, wenn eine Zeile geschrieben wurde."""
    if not is_recording():
        return False
    line = format_entry(nummer, titel)
    if not line:
        return False
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
