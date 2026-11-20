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
    status, _ = http(f"{url}?api=upload&name=bild.png", b"\x89PNG", {**head, "Content-Type": "image/png"})
    assert status == 503, "Bilder werden bei ausgeschaltetem Programm nicht angenommen"

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
    assert reply["pause"] and reply["plan"], reply
    plan = app(server, "plan_get")["item"]
    assert json.loads(plan["body"])["songs"] == ["p012", "s5"]
    app(server, "plan_done", created=plan["created"])
    item = app(server, "pause_get")["item"]
    assert json.loads(item["body"])["end"] == "11:45"
    app(server, "pause_done", created=item["created"])
    reply = app(server, "poll", hold=0)
    assert not reply["pause"] and not reply["plan"], "nach dem Abholen ist nichts mehr vorgemerkt"

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
