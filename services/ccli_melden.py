"""Meldet die gespielten Lieder bei CCLI („Suchen & Melden“): Nummer eingeben → Suchen → „Lied melden“.

Ablauf: Zuerst startet ein ganz normaler Chrome bzw. Edge (eigenes Profil im Datenordner, die Anmeldung bleibt erhalten).
Dort meldest du dich an – ohne Fernsteuerung. Login-Seiten erkennen einen ferngesteuerten Browser und laden sonst endlos
neu. Erst nach dem Login verbindet sich Playwright mit diesem Browser (Chrome-DevTools-Schnittstelle, nur lokal) und
meldet die Nummern. Zugangsdaten sieht das Programm nicht. Ohne Qt, damit es sich testen lässt.
"""
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from paths import user_data_dir
from services import ccli

log = logging.getLogger(__name__)
START_URL = "https://reporting.ccli.com/search"     # CCLI Reporting „Suchen & Melden“ (ohne Anmeldung leitet CCLI zum Login)
INSTALL_HINT = "pip3 install -r requirements-ccli.txt"
BROWSER_HINT = "Bitte Google Chrome oder Microsoft Edge installieren."


class MeldenError(Exception):
    pass


def pending(report: Path):
    """Die noch zu meldenden Nummern aus der Meldeliste (eine pro Zeile)."""
    return ccli.read_report(report)


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


_SEARCH = re.compile(r"^\s*(Suchen|Search)\s*$", re.IGNORECASE)
_REPORT = re.compile(r"(Lied\s+)?melden|report", re.IGNORECASE)


def report_one(page, ccli: str, timeout: int = 15000) -> None:
    """Nummer eingeben, suchen und beim Treffer mit dieser CCLI-Nummer „Lied melden“ klicken.
    Tolerant gebaut: Suchen per Knopf oder Enter, Treffer als Tabellenzeile oder als Karte."""
    box = page.locator("input[type=search], input[type=text]").first
    box.fill(ccli)
    search = page.get_by_role("button", name=_SEARCH)
    if search.count():
        search.first.click()
    else:
        box.press("Enter")
    report_button = page.get_by_role("button", name=_REPORT)
    row = page.locator("tr, [role=row], li, article, div").filter(has_text=ccli).filter(has=report_button).last
    row.wait_for(timeout=timeout)
    row.get_by_role("button", name=_REPORT).first.click()


def _ensure_search_page(page) -> None:
    """Nach dem Login landet man bei CCLI oft auf einer anderen Seite: dann zurück zu „Suchen & Melden“."""
    if START_URL and not page.url.startswith(START_URL):
        try:
            page.goto(START_URL)
        except Exception as exc:  # noqa: BLE001 – Seite nicht erreichbar: Nutzer öffnet sie selbst
            log.warning("Suchseite nicht erreichbar: %s", exc)


def _browser_candidates() -> list:
    """Installierte Chrome-/Edge-Programme (zuerst Chrome, dann Edge – auf Windows ist Edge immer vorhanden)."""
    if sys.platform == "darwin":
        names = ("Google Chrome.app/Contents/MacOS/Google Chrome", "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                 "Chromium.app/Contents/MacOS/Chromium")
        paths = [Path(base) / name for name in names for base in ("/Applications", Path.home() / "Applications")]
    elif sys.platform.startswith("win"):
        roots = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        names = (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe")
        paths = [Path(root) / name for name in names for root in roots if root]
    else:
        paths = [Path(found) for found in (shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser",
                                                                      "microsoft-edge")) if found]
    return [str(path) for path in paths if path.is_file()]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


_last = None     # (Prozess, Adresse) des zuletzt gestarteten Browsers – ist er noch offen, wird er wiederverwendet


def _alive(endpoint: str) -> bool:
    try:
        with urllib.request.urlopen(endpoint + "/json/version", timeout=2) as reply:     # nur localhost
            json.loads(reply.read().decode("utf-8"))
        return True
    except (OSError, ValueError):
        return False


def _start_plain_browser(profile: Path):
    """Startet Chrome/Edge ganz normal (keine Automatisierungs-Kennung) mit lokaler DevTools-Schnittstelle.
    Gibt (Prozess, Adresse der Schnittstelle) zurück oder ``None``, wenn kein Browser gefunden wurde.
    Ein noch offenes Fenster vom letzten Mal wird weiterbenutzt (ein zweiter Start mit demselben Profil ginge nicht)."""
    global _last
    if _last is not None and _last[0].poll() is None and _alive(_last[1]):
        return _last
    for exe in _browser_candidates():
        port = _free_port()
        args = [exe, f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1",
                f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", START_URL or "about:blank"]
        try:
            process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=0x08000000 if sys.platform.startswith("win") else 0)
        except OSError as exc:
            log.warning("Browser %s startet nicht: %s", exe, exc)
            continue
        endpoint = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if _alive(endpoint):
                _last = (process, endpoint)
                return _last
            if process.poll() is not None:
                break
            time.sleep(0.3)
        log.warning("Browser %s antwortet nicht auf der DevTools-Schnittstelle", exe)
        if process.poll() is None:
            process.terminate()
    return None


def _ccli_page(context):
    """Der Tab mit CCLI (falls du mehrere geöffnet hast), sonst der erste."""
    pages = context.pages
    for page in reversed(pages):
        if "ccli.com" in page.url:
            return page
    return pages[0] if pages else context.new_page()


def run(report: Path, wait_login, after_first, progress, should_stop=lambda: False, pause_each: bool = True) -> dict:
    """Meldet alle Nummern der Meldeliste – eingegeben wird nur die CCLI-Nummer. Jede gemeldete Nummer wird sofort aus der
    Meldeliste entfernt (nichts Gemeldetes wird aufbewahrt); ist alles gemeldet, wird die Datei gelöscht. ``wait_login()`` kehrt zurück, wenn der Nutzer eingeloggt ist (False = Abbruch);
    ``after_first(nummer)`` liefert "next", "auto" oder "stop" (nur solange ``pause_each``); ``progress(i, n, text)``
    für die Anzeige. Gibt {"gemeldet", "fehler", "offen"} zurück."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise MeldenError(f"Playwright fehlt. Installieren mit: {INSTALL_HINT}") from exc
    todo = pending(report)
    counts = {"gemeldet": 0, "fehler": 0, "offen": len(todo)}
    if not todo:
        return counts
    remaining = list(todo)
    profile = user_data_dir() / "ccli_browser"
    started = _start_plain_browser(profile)
    if started is None:
        raise MeldenError(f"Es wurde kein Browser gefunden. {BROWSER_HINT}")
    _process, endpoint = started
    if not wait_login():                                   # Anmeldung im ganz normalen Browser, ohne Fernsteuerung
        return counts
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(endpoint)
        except Exception as exc:                      # z. B. Browserfenster schon geschlossen
            raise MeldenError("Verbindung zum Browser fehlgeschlagen. Bitte das Browserfenster offen lassen und neu starten.") from exc
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = _ccli_page(context)
            page.bring_to_front()
            _ensure_search_page(page)
            pause = pause_each
            for index, number in enumerate(todo, 1):
                if should_stop():
                    break
                progress(index - 1, len(todo), f"Nummer {number} …")
                try:
                    report_one(page, number)
                except Exception as exc:  # noqa: BLE001 – Seite anders als erwartet: bleibt in der Meldeliste
                    counts["fehler"] += 1
                    log.warning("CCLI-Meldung %s: %s", number, exc)
                    continue
                counts["gemeldet"] += 1
                counts["offen"] -= 1
                remaining.remove(number)
                ccli.write_report(remaining, report)
                if pause:
                    answer = after_first(number, "gemeldet")
                    if answer == "stop":
                        break
                    pause = answer != "auto"
            progress(len(todo), len(todo), "")
        finally:
            browser.close()          # trennt nur die Verbindung – das Browserfenster bleibt zum Nachsehen offen
    return counts
