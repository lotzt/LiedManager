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


def test_nummernsuche_genau_mit_verweis(tmp):
    """Eine Nummer wird genau so gesucht, wie sie getippt wurde: ohne Buchstabe die reine Nummer, mit Buchstabe genau
    dieses Präfix – nie automatisch ein anderes. Ist ein Verweis hinterlegt (512 -> p102), gilt das Ziel."""
    import os
    import sqlite3

    from database import DatabaseManager
    path = os.path.join(str(tmp), "verweis.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE Data (nummer TEXT, alias TEXT, titel TEXT, lyrics TEXT, audio1 BLOB, audio2 BLOB, "
                "bild1 BLOB, bild2 BLOB, bild3 BLOB, bild4 BLOB)")
    for nummer, alias, titel, lyrics in (
            ("200", None, "Alpha", "a"), ("p200", None, "Bravo", "b"), ("s200", None, "Charlie", "c"),
            ("512", "p102", "Verweis auf p102", None), ("p102", None, "Delta", "d"), ("p512", None, "Echo", "e"),
            ("s201", "s044", "Verweis auf s044", None), ("s044", None, "Foxtrot", "f"),
            ("p077", None, "Nur mit Praefix", "g"),
            ("600", "p12", "Verweis ohne fuehrende Null", None), ("p012", None, "Golf", "h"),
            ("700", "701", "Kette 700", None), ("701", "p102", "Kette 701", None),
            ("900", "p999", "Verweis ins Leere", None)):
        con.execute("INSERT INTO Data (nummer, alias, titel, lyrics) VALUES (?, ?, ?, ?)", (nummer, alias, titel, lyrics))
    con.commit()
    con.close()
    db = DatabaseManager(path)

    def titles(query):
        return [song.titel for song in db.search_songs(query)]

    assert titles("200") == ["Alpha"], "ohne Buchstabe: die reine Nummer, nicht p200"
    assert titles("p200") == ["Bravo"] and titles("s200") == ["Charlie"], "mit Buchstabe: genau dieses Präfix"
    assert titles("512") == ["Delta"], "512 ist ein Verweis auf p102 (auch wenn es p512 gibt)"
    assert titles("p512") == ["Echo"]
    assert titles("s201") == ["Foxtrot"], "Verweise gelten bei jedem Präfix"
    assert titles("77") == [], "nur p077 vorhanden: Eingabe 77 wird nicht zu p077"
    assert titles("p77") == ["Nur mit Praefix"]
    assert titles("600") == ["Golf"], "Verweis p12 findet p012"
    assert titles("700") == ["Delta"], "Verweisketten werden bis zum Ziel verfolgt"
    assert titles("900") == ["Verweis ins Leere"], "Verweis ohne Ziel: das Lied selbst"
