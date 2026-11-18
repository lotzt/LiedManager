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
