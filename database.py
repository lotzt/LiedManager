"""SQLite-Zugriff mit schneller Suche.

Die Liedtexte werden einmal in den Speicher geladen (nur Nummer, Titel, Text – keine Bilder/Audios)
und bei jeder Suche wiederverwendet. Ändert ein anderes Programm die Datenbank, wird der Cache
automatisch neu aufgebaut. Die Medien (Audio/Bilder) werden erst beim Auswählen eines Liedes geladen.
"""
import logging
import os
import time
import re
import sqlite3
from collections import namedtuple
from difflib import SequenceMatcher

from paths import resolve_db_path

log = logging.getLogger(__name__)

# Kurzinfo für Trefferlisten (ohne Liedtext)
SongSummary = namedtuple("SongSummary", "rowid nummer alias titel")

_NUMBER_QUERY = re.compile(r"^([a-zA-Z])?(\d{1,3})$")
_LEADING_INT = re.compile(r"^\s*[+-]?\d+")
_NON_WORD = re.compile(r"[^\w\s]")

FUZZY_CUTOFF = 0.8
FUZZY_MAX_SECONDS = 2.0       # unscharfe Suche gibt nach so langer Zeit mit dem auf, was sie bis dahin gefunden hat
RELOAD_MIN_INTERVAL = 3.0     # frühestens alle 3 s die Texte aller Lieder neu aus der Datenbank lesen


def normalize(text) -> str:
    """Kleinschreibung, ohne Satzzeichen, Leerraum zusammengefasst."""
    if not text:
        return ""
    return " ".join(_NON_WORD.sub("", str(text).lower()).split())


class _Song:
    """Zwischengespeicherter Datensatz für die Suche."""
    __slots__ = ("summary", "number_key", "int_number", "norm_title", "norm_lyrics",
                 "raw_lyrics", "_lines")

    def __init__(self, rowid, nummer, alias, titel, lyrics):
        self.summary = SongSummary(rowid, nummer, alias, titel)
        nummer_str = str(nummer)
        self.number_key = nummer_str.lower().replace(" ", "")
        match = _LEADING_INT.match(nummer_str)
        self.int_number = int(match.group()) if match else None
        self.norm_title = normalize(titel)
        self.raw_lyrics = lyrics or ""
        self.norm_lyrics = normalize(lyrics)
        self._lines = None

    @property
    def has_alias(self) -> bool:
        return bool(self.summary.alias)

    @property
    def lines(self):
        """Normalisierte Textzeilen als Wortlisten (lazy, nur für die unscharfe Suche)."""
        if self._lines is None:
            lines = []
            for line in self.raw_lyrics.split("\n"):
                if line.strip():
                    words = normalize(line).split()
                    if words:
                        lines.append(words)
            self._lines = lines
        return self._lines


def _tolerant_text(raw: bytes):
    """Text als str lesen; Bytes, die kein gültiges UTF-8 sind (Bild/Audio im Text-Typ gespeichert), bleiben unverändert.
    Ohne das bricht SQLite mit „Could not decode to UTF-8“ ab."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return bytes(raw)


class DatabaseManager:
    def __init__(self, db_name: str = None):
        self.db_name = db_name or resolve_db_path()
        self._conn = None
        self._songs = None          # Liste[_Song] in Datenbank-Reihenfolge
        self._by_number = {}        # lower(nummer ohne Leerzeichen) -> _Song (erster Treffer)
        self._data_version = None
        self._loaded_at = 0.0
        self._load_seconds = 0.0
        self._connect()

    # ------------------------------------------------------------------
    # Verbindung
    # ------------------------------------------------------------------
    def _connect(self):
        if not os.path.exists(self.db_name):
            log.warning("Datenbank nicht gefunden: %s", self.db_name)
            return
        try:
            self._conn = sqlite3.connect(self.db_name)
            self._conn.text_factory = _tolerant_text
        except sqlite3.Error as exc:
            log.error("Datenbank konnte nicht geöffnet werden: %s", exc)

    @property
    def available(self) -> bool:
        return self._conn is not None

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    def _current_data_version(self):
        try:
            return self._conn.execute("PRAGMA data_version").fetchone()[0]
        except sqlite3.Error:
            return None

    def _ensure_cache(self) -> bool:
        if self._conn is None:
            return False
        version = self._current_data_version()
        if self._songs is not None and version == self._data_version:
            return True
        if (self._songs is not None and self._load_seconds > 0.3
                and time.monotonic() - self._loaded_at < RELOAD_MIN_INTERVAL):
            return True                 # Abgleich schreibt gerade laufend: nicht bei jeder Suche alle Texte neu laden
        started = time.monotonic()
        try:
            rows = self._conn.execute(
                "SELECT rowid, nummer, alias, titel, lyrics FROM Data "
                "WHERE nummer IS NOT NULL AND nummer != 'None' ORDER BY rowid"
            ).fetchall()
        except sqlite3.Error as exc:
            log.error("Tabelle 'Data' konnte nicht gelesen werden: %s", exc)
            return False

        self._songs = [_Song(*row) for row in rows]
        self._by_number = {}
        for song in self._songs:
            self._by_number.setdefault(song.number_key, song)
        self._data_version = version
        self._loaded_at = time.monotonic()
        self._load_seconds = self._loaded_at - started      # nur bei großen Datenbanken (langsames Laden) wird gedrosselt
        log.info("%d Lieder geladen.", len(self._songs))
        return True

    # ------------------------------------------------------------------
    # Suche
    # ------------------------------------------------------------------
    def all_songs(self):
        """Alle Lieder als ``SongSummary``-Liste in Datenbank-Reihenfolge (leer, wenn die Datenbank fehlt)."""
        if not self._ensure_cache():
            return []
        return [song.summary for song in self._songs]

    def search_songs(self, raw_query: str):
        """Nummer ('1', 'p1', 'p001') -> Titel/Text -> unscharfe Passagensuche. Liefert ``SongSummary``-Liste."""
        query = (raw_query or "").strip().lower()
        if not query or not self._ensure_cache():
            return []

        found = self._search_number(query)
        if not found:
            norm_query = normalize(raw_query)
            if not norm_query:
                return []
            found = self._search_text(norm_query)
            if not found:
                found = self._search_fuzzy(norm_query)
        return [song.summary for song in found]

    def _search_number(self, query: str):
        match = _NUMBER_QUERY.match(query)
        if not match:
            return []
        prefix = match.group(1) or "p"  # ohne Buchstabe: 'p' annehmen
        number = int(match.group(2))

        song = (self._by_number.get(f"{prefix}{number:03d}")
                or self._by_number.get(f"{prefix}{number}"))
        if song is None:
            song = next((s for s in self._songs if s.int_number == number), None)
        if song is None:
            return []

        if song.has_alias:  # Verweis auf das eigentliche Lied
            target = self._by_number.get(str(song.summary.alias).lower().replace(" ", ""))
            if target is not None:
                song = target
        return [song]

    def _search_text(self, norm_query: str):
        return [s for s in self._songs
                if not s.has_alias and (norm_query in s.norm_title or norm_query in s.norm_lyrics)]

    def _search_fuzzy(self, norm_query: str):
        """Findet Passagen, die zu mindestens 80 % mit einer Textzeile (oder einem Teilstück) übereinstimmen."""
        query_words = norm_query.split()
        n = len(query_words)
        matcher = SequenceMatcher(None, "", norm_query)  # seq2 wird nur einmal aufbereitet

        def similar(candidate: str) -> bool:
            matcher.set_seq1(candidate)
            return (matcher.real_quick_ratio() >= FUZZY_CUTOFF
                    and matcher.quick_ratio() >= FUZZY_CUTOFF
                    and matcher.ratio() >= FUZZY_CUTOFF)

        results = []
        deadline = time.monotonic() + FUZZY_MAX_SECONDS
        for song in self._songs:
            if song.has_alias:
                continue
            if time.monotonic() > deadline:
                log.info("Unscharfe Suche abgebrochen (Zeitlimit) – %d Treffer bis dahin.", len(results))
                break
            for words in song.lines:
                if len(words) <= n:
                    hit = similar(" ".join(words))
                else:
                    hit = any(similar(" ".join(words[i:i + n])) for i in range(len(words) - n + 1))
                if hit:
                    results.append(song)
                    break
        return results

    # ------------------------------------------------------------------
    # Mediendaten
    # ------------------------------------------------------------------
    _FULL_COLUMNS = "rowid, nummer, alias, titel, lyrics, audio1, audio2, bild1, bild2, bild3, bild4"

    def get_song_full_data(self, rowid):
        """Lädt Text + Medien eines Liedes. Lässt sich ein Medium nicht lesen, wird das Lied ohne Medien geladen –
        die Datenbank wird dabei nie verändert (früher wurden die Medien des Liedes gelöscht)."""
        if self._conn is None:
            return None
        try:
            return self._conn.execute(
                f"SELECT {self._FULL_COLUMNS} FROM Data WHERE rowid = ?", (rowid,)
            ).fetchone()
        except sqlite3.Error as exc:
            log.warning("Mediendaten bei ID %s nicht lesbar (%s) – Lied wird ohne Medien geladen.", rowid, exc)
        try:
            return self._conn.execute(
                "SELECT rowid, nummer, alias, titel, lyrics, NULL, NULL, NULL, NULL, NULL, NULL "
                "FROM Data WHERE rowid = ?", (rowid,)
            ).fetchone()
        except sqlite3.Error as exc:
            log.error("Lied ID %s konnte nicht gelesen werden: %s", rowid, exc)
            return None
