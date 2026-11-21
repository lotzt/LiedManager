"""server/remote.php und server/sync.php mit echtem PHP und echter MySQL-Datenbank.

Läuft nur, wenn eine Test-Datenbank angegeben ist (auf GitHub automatisch, siehe .github/workflows/tests.yml):
    LM_TEST_MYSQL_HOST, LM_TEST_MYSQL_DB, LM_TEST_MYSQL_USER, LM_TEST_MYSQL_PASS
Die Dateien laufen im eingebauten Webserver von PHP; HTTPS wird dabei per Kopfzeile vorgetäuscht.
"""
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "test-token-0123456789-abcdefghij"
PIN = "12345678"
DEVICE = "Testrechner"

pytestmark = pytest.mark.skipif(not os.environ.get("LM_TEST_MYSQL_HOST") or not shutil.which("php"),
                                reason="keine Test-Datenbank (LM_TEST_MYSQL_*) oder kein PHP")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """remote.php in …/steuerung/, sync.php in …/sync/, die gemeinsame Zugangsdatei einen Ordner darüber."""
    root = tmp_path_factory.mktemp("website")
    (root / "steuerung").mkdir()
    (root / "sync").mkdir()
    shutil.copy(ROOT / "server" / "remote.php", root / "steuerung" / "remote.php")
    shutil.copy(ROOT / "server" / "sync.php", root / "sync" / "sync.php")
    (root / "liedmanager-zugang.php").write_text(
        "<?php\n"
        f"define('TOKEN', '{TOKEN}');\ndefine('PIN', '{PIN}');\n"
        f"define('DB_HOST', '{os.environ['LM_TEST_MYSQL_HOST']}');\n"
        f"define('DB_NAME', '{os.environ['LM_TEST_MYSQL_DB']}');\n"
        f"define('DB_USER', '{os.environ['LM_TEST_MYSQL_USER']}');\n"
        f"define('DB_PASS', '{os.environ['LM_TEST_MYSQL_PASS']}');\n", encoding="utf-8")
    port = _free_port()
    log_file = open(root / "php.log", "w")          # PHP-Fehlerprotokoll: erscheint bei fehlgeschlagenen Tests
    proc = subprocess.Popen(["php", "-d", "log_errors=1", "-d", "error_log=" + str(root / "php-errors.log"),
                             "-S", f"127.0.0.1:{port}", "-t", str(root)], stdout=log_file, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield base
    proc.terminate()
    proc.wait(timeout=10)
    log_file.close()
    for name in ("php-errors.log", "php.log"):
        path = root / name
        if path.exists() and path.read_text(errors="replace").strip():
            print(f"===== {name} =====\n" + path.read_text(errors="replace")[-6000:])


def http(url, data=None, headers=None, method=None):
    """(Status, Text) – HTTPS wird für die Seiten vorgetäuscht (X-Forwarded-Proto)."""
    head = {"X-Forwarded-Proto": "https", **(headers or {})}
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        head.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=body, headers=head, method=method or ("POST" if body else "GET"))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def app(server, action, **params):
    """Wie das Programm (services/remote_relay.py): JSON mit Token, Aktion und Computername."""
    status, text = http(f"{server}/steuerung/remote.php",
                        {"token": TOKEN, "action": action, "dev": DEVICE, "did": "test-did", **params})
    assert status == 200, f"{action}: {status} {text}"
    return json.loads(text)


def test_pruefseite(server):
    status, text = http(f"{server}/steuerung/remote.php?check")
    assert status == 200, text
    assert "Datenbank: OK" in text, text
    assert "liedmanager-zugang.php (Ordner darüber)" in text, text


def test_anmeldung_und_ansagen_vormerken(server):
    url = f"{server}/steuerung/remote.php"
    status, _ = http(f"{url}?api=login", {"pin": "falsch"})
    assert status in (401, 403), "falsche PIN muss abgelehnt werden"
    status, text = http(f"{url}?api=login", {"pin": PIN})
    assert status == 200, text
    head = {"X-LM-Token": json.loads(text)["token"], "X-LM-Device": DEVICE}

    status, _ = http(f"{url}?api=state", headers=head)
    assert status == 503, "Programm läuft nicht: kein Zustand"
    status, text = http(f"{url}?api=upload&name=bild.png", b"\x89PNG", {**head, "Content-Type": "image/png"})
    assert status == 202 and json.loads(text)["queued"], "Bilder werden bei ausgeschaltetem Programm vorgemerkt"
    status, text = http(f"{url}?api=upload&name=zwei.jpg", b"\xff\xd8zwei", {**head, "Content-Type": "image/jpeg"})
    assert status == 202, text
    status, text = http(f"{url}?api=inbox", headers=head)
    items = json.loads(text)["items"]
    assert [i["name"] for i in items] == ["bild.png", "zwei.jpg"], text
    request = urllib.request.Request(f"{url}?api=inbox_img/{items[1]['id']}",
                                     headers={"X-Forwarded-Proto": "https", **head})
    with urllib.request.urlopen(request, timeout=30) as response:
        assert response.read() == b"\xff\xd8zwei" and response.headers["Content-Type"] == "image/jpeg"
    status, text = http(f"{url}?api=inbox_remove", {"id": items[1]["id"]}, head)
    assert status == 200 and json.loads(text)["pending"] == 1, text

    status, text = http(f"{url}?api=pause_set", {"lines": ["Erste Ansage", "Zweite"], "end": "11:45"}, head)
    assert status == 202 and json.loads(text)["queued"], text
    status, text = http(f"{url}?api=pause", headers=head)
    assert status == 200 and json.loads(text)["pending"]["lines"] == ["Erste Ansage", "Zweite"], text

    status, text = http(f"{url}?api=plan_set", {"songs": ["p012", "s5"]}, head)
    assert status == 202 and json.loads(text)["queued"], text
    status, text = http(f"{url}?api=plan", headers=head)
    assert status == 200 and json.loads(text)["pending"]["songs"] == ["p012", "s5"], text

    # Programm startet: holt vorgemerkte Ansagen und Lieder ab und meldet sie als erledigt
    reply = app(server, "poll", hold=0)
    assert reply["pause"] and reply["plan"] and reply["inbox"] == 1, reply
    bild = app(server, "inbox_get")["item"]
    assert bild["name"] == "bild.png"
    app(server, "inbox_done", id=bild["id"])
    plan = app(server, "plan_get")["item"]
    assert json.loads(plan["body"])["songs"] == ["p012", "s5"]
    app(server, "plan_done", created=plan["created"])
    item = app(server, "pause_get")["item"]
    assert json.loads(item["body"]) == {"lines": ["Erste Ansage", "Zweite"]}, "Endzeit wird nicht vorgemerkt"
    app(server, "pause_done", created=item["created"])
    reply = app(server, "poll", hold=0)
    assert not reply["pause"] and not reply["plan"] and not reply["inbox"], "nach dem Abholen ist nichts mehr vorgemerkt"

    # Zustand vom Programm kommt im Browser an
    app(server, "state", data=json.dumps({"version": "test", "pause": {"lines": ["Erste Ansage"]}}))
    status, text = http(f"{url}?api=state", headers=head)
    assert status == 200 and json.loads(text)["version"] == "test", text


def test_falsches_token(server):
    status, _ = http(f"{server}/steuerung/remote.php", {"token": "falsch", "action": "poll", "dev": DEVICE})
    assert status in (401, 403)
    status, _ = http(f"{server}/sync/sync.php", {"token": "falsch", "action": "list"})
    assert status in (401, 403)


def test_abgleich(server):
    status, text = http(f"{server}/sync/sync.php", {"token": TOKEN, "action": "list", "since": 0})
    assert status == 200, text
    assert isinstance(json.loads(text).get("items"), list), text


def test_liedsuche_ohne_programm(server):
    """Das Programm lädt seine Liederliste hoch; ist es aus, sucht die Website darin wie das Programm selbst."""
    import sys
    sys.path.insert(0, str(ROOT))
    from database import DatabaseManager
    db = DatabaseManager(str(ROOT / "beispiel" / "LiedManager-Beispiel.db"))
    digest, rows = db.search_index()
    assert rows, "Beispiel-Datenbank ohne Lieder"
    half = len(rows) // 2 or 1
    app(server, "songs_put", hash=digest, start=0, total=len(rows), songs=rows[:half])
    if half < len(rows):
        app(server, "songs_put", hash=digest, start=half, total=len(rows), songs=rows[half:])
    assert app(server, "songs_hash")["hash"] == digest
    app(server, "bye")                                  # Programm aus

    url = f"{server}/steuerung/remote.php"
    status, text = http(f"{url}?api=login", {"pin": PIN})
    head = {"X-LM-Token": json.loads(text)["token"], "X-LM-Device": DEVICE}

    def search(text_):
        status_, body = http(f"{url}?api=search", {"text": text_}, head)
        assert status_ == 200, body
        data = json.loads(body)
        assert data["offline"], data
        return data["songs"]

    for query in ("Großer Gott", "100", "1", "herr wir preisen", "lobe den heren den mächtigen", "", "zzzzqqq"):
        expected = [(s.nummer, s.titel) for s in db.search_songs(query)]
        got = [(s["nummer"], s["titel"]) for s in search(query)]
        assert [str(n) for n, _ in got] == [str(n) for n, _ in expected], (query, got, expected)

    # Titel zu vorgemerkten Nummern (Verweise aufgelöst, Unbekanntes = null)
    status, body = http(f"{url}?api=plan_titles", {"songs": ["1", "100", "B1", "zz9"]}, head)
    assert status == 200, body
    data = json.loads(body)
    assert data["index"], data
    assert [t and t["nummer"] for t in data["titles"]] == ["1", "1", "b1", None], data
    assert data["titles"][0]["titel"] == "Großer Gott, wir loben dich", data
