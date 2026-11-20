"""Vorgemerkte Lieder: eine Liste von Liednummern (z. B. aus der Fernsteuerung), die nach und nach in die Suchzeile
kommen. Gespeichert in den Einstellungen, damit sie einen Neustart übersteht.

Ein Lied verlässt die Liste erst, wenn es wirklich auf dem Beamer war – nur Nachschauen in der Suche zählt nicht.
"""
import json
import re

from services.settings import app_settings
from services.settings_keys import KEY_SONG_PLAN

MAX_SONGS = 50
MAX_LENGTH = 20


def clean(songs) -> list:
    """Leere Zeilen weg, Leerzeichen am Rand weg, Länge und Anzahl begrenzt."""
    result = []
    for entry in songs if isinstance(songs, (list, tuple)) else []:
        text = str(entry).strip()[:MAX_LENGTH]
        if text:
            result.append(text)
    return result[:MAX_SONGS]


def get() -> list:
    try:
        return clean(json.loads(app_settings().value(KEY_SONG_PLAN, "[]", type=str) or "[]"))
    except ValueError:
        return []


def set_songs(songs) -> list:
    songs = clean(songs)
    app_settings().setValue(KEY_SONG_PLAN, json.dumps(songs, ensure_ascii=False))
    return songs


def _key(number: str) -> str:
    """„p012“, „P12“ und „p 12“ sind dasselbe Lied: Kleinbuchstaben, ohne Leerzeichen, ohne führende Nullen."""
    text = re.sub(r"\s+", "", str(number or "")).lower()
    match = re.fullmatch(r"([a-zäöü]*)0*(\d+)(.*)", text)
    return f"{match.group(1)}{match.group(2)}{match.group(3)}" if match else text


def shown(number: str) -> bool:
    """Ein Lied war auf dem Beamer: Ist es das erste vorgemerkte, fällt es aus der Liste (True)."""
    songs = get()
    if songs and _key(songs[0]) == _key(number):
        set_songs(songs[1:])
        return True
    return False
