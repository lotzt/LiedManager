"""Abläufe ohne Hauptfenster (Updater, Abgleich, Remote, X AIR …) als einzelne Tests.

Die Prüfungen selbst stehen in ``tools/smoke_test.py`` (dort laufen sie auch beim direkten Aufruf mit); hier werden
sie einzeln ausgeführt, damit bei einem Fehler sichtbar ist, *welcher* Ablauf betroffen ist und die anderen trotzdem laufen.
"""
import smoke_test


def test_updater(tmp):
    smoke_test.test_updater_logic(tmp)


def test_server_sync(tmp):
    smoke_test.test_server_sync(tmp)


def test_remote_relay(tmp):
    smoke_test.test_remote_relay(tmp)


def test_remote_site(app):
    smoke_test.test_remote_site()


def test_new_features(tmp):
    smoke_test.test_new_features(tmp)


def test_xair(app):
    smoke_test.test_xair()


def test_history_and_problem_report(tmp):
    smoke_test.test_history_and_problem_report(tmp)


def test_beispiel_datenbank(app):
    """Die mitgelieferte Beispiel-Datenbank lässt sich öffnen, durchsuchen und hat ein Beamer-Bild je Lied."""
    from pathlib import Path

    from database import DatabaseManager
    path = Path(__file__).resolve().parent.parent / "beispiel" / "LiedManager-Beispiel.db"
    db = DatabaseManager(str(path))
    assert db.available, "Beispiel-Datenbank lässt sich nicht öffnen"
    found = db.search_songs("Großer Gott")
    assert found and found[0].titel == "Großer Gott, wir loben dich"
    full = db.get_song_full_data(found[0].rowid)
    assert full[7], "Lied ohne Beamer-Bild (bild1)"
    assert db.search_songs("100"), "Verweis-Nummer 100 muss gefunden werden"


def test_nummer_ohne_praefix_folgt_verweis(tmp):
    """Eingabe ohne Buchstabe: hat die reine Nummer einen Verweis (512 -> p102), gilt das Ziel – auch wenn es p512 gibt.
    Ohne Verweis bleibt es bei 'p' + Nummer."""
    import os
    import sqlite3

    from database import DatabaseManager
    path = os.path.join(str(tmp), "verweis.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE Data (nummer TEXT, alias TEXT, titel TEXT, lyrics TEXT, audio1 BLOB, audio2 BLOB, "
                "bild1 BLOB, bild2 BLOB, bild3 BLOB, bild4 BLOB)")
    for nummer, alias, titel, lyrics in (
            ("p102", None, "Lied 102", "a"), ("512", "p102", "Verweis 512", None), ("p512", None, "Lied p512", "b"),
            ("p012", None, "Lied p012", "c"), ("12", None, "Lied 12", "d"),
            ("700", "p999", "Verweis ins Leere", "e"), ("p700", None, "Lied p700", "f")):
        con.execute("INSERT INTO Data (nummer, alias, titel, lyrics) VALUES (?, ?, ?, ?)", (nummer, alias, titel, lyrics))
    con.commit()
    con.close()
    db = DatabaseManager(path)

    def numbers(query):
        return [song.nummer for song in db.search_songs(query)]

    assert numbers("512") == ["p102"], "512 ist ein Verweis auf p102"
    assert numbers("p512") == ["p512"], "mit Buchstabe gilt genau diese Nummer"
    assert numbers("12") == ["p012"], "ohne Verweis bleibt es bei p + Nummer"
    assert numbers("700") == ["p700"], "Verweis ohne Ziel: weiter wie bisher"
