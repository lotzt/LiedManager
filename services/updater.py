"""Auto-Updater: fragt die GitHub-Releases-API ab, vergleicht mit ``version.py`` und lädt den passenden Installer.

Reine Python-Logik ohne Qt (Oberfläche: ``ui/updater_ui.py``), damit sie sich ohne Fenster testen lässt.

Der Updater erwartet die Dateinamen, die der Workflow erzeugt (sie bilden einen festen Vertrag):
    Windows       LiedManager-<Version>-Windows-Setup.exe
    Mac (Apple)   LiedManager-<Version>-macOS-arm64.dmg
    Mac (Intel)   LiedManager-<Version>-macOS-x86_64.dmg

Voraussetzung: Das Repository ist öffentlich (die Releases-API ist dann ohne Anmeldung lesbar).
"""
import hashlib
import json
import logging
import os
import platform
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

API_URL = "https://api.github.com/repos/{repo}/releases/latest"
TIMEOUT = 15
CHUNK = 256 * 1024
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


class UpdateError(Exception):
    """Fehler mit einer Meldung, die der Nutzer lesen darf."""


class UpdateCancelled(UpdateError):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    notes: str
    asset_name: str
    url: str
    size: int
    sha256: str
    page_url: str


# ----------------------------------------------------------------------
# Versionen und Dateinamen
# ----------------------------------------------------------------------
def parse_version(text):
    """„v2.1.0“ / „2.1.0“ -> (2, 1, 0); ``None``, wenn es keine Versionsnummer ist."""
    match = _VERSION.match(str(text or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(remote, local) -> bool:
    remote_v, local_v = parse_version(remote), parse_version(local)
    return remote_v is not None and local_v is not None and remote_v > local_v


def asset_suffix(system: str = None, machine: str = None):
    """Endung der Release-Datei für dieses System, ``None`` wenn es dafür keinen Installer gibt."""
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    if system.startswith("win"):
        return "-Windows-Setup.exe"
    if system == "darwin":
        return "-macOS-arm64.dmg" if machine in ("arm64", "aarch64") else "-macOS-x86_64.dmg"
    return None


def pick_asset(release: dict, suffix: str):
    for asset in release.get("assets") or []:
        if str(asset.get("name", "")).endswith(suffix) and asset.get("browser_download_url"):
            return asset
    return None


# ----------------------------------------------------------------------
# Netzwerk
# ----------------------------------------------------------------------
def _ssl_context():
    """Zertifikate aus ``certifi`` (die gebaute Mac-App findet sonst keine); sonst die des Systems."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url: str, accept: str):
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "LiedManager-Updater"})
    return urllib.request.urlopen(request, timeout=TIMEOUT, context=_ssl_context())


def fetch_latest(repo: str) -> dict:
    """Liefert das neueste veröffentlichte Release (ohne Entwürfe und Vorabversionen)."""
    try:
        with _open(API_URL.format(repo=repo), "application/vnd.github+json") as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("Es wurde kein Release gefunden. Ist das Repository öffentlich und gibt es schon eines?") from exc
        if exc.code in (403, 429):
            raise UpdateError("GitHub hat die Anfrage vorübergehend abgelehnt (zu viele Abfragen). Bitte später erneut versuchen.") from exc
        raise UpdateError(f"GitHub antwortet mit Fehler {exc.code}.") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpdateError("Keine Verbindung zu GitHub. Ist der Computer online?") from exc


def check(repo: str, current: str, fetch=fetch_latest, suffix: str = None):
    """``UpdateInfo`` bei neuerer Version, ``None`` wenn das Programm aktuell ist. Wirft ``UpdateError``."""
    if not repo:
        raise UpdateError("Die Update-Suche ist in dieser Version nicht eingerichtet.")
    release = fetch(repo)
    tag = str(release.get("tag_name", ""))
    if parse_version(tag) is None:
        raise UpdateError(f"Unbekannte Versionsnummer im Release: „{tag}“.")
    if not is_newer(tag, current):
        return None
    suffix = suffix if suffix is not None else asset_suffix()
    if suffix is None:
        raise UpdateError(f"Version {tag.lstrip('v')} ist erschienen, für dieses System gibt es aber keinen Installer.")
    asset = pick_asset(release, suffix)
    if asset is None:
        raise UpdateError(f"Version {tag.lstrip('v')} ist erschienen, aber der Installer für dieses System fehlt noch "
                          "(der Build läuft vielleicht noch). Bitte später erneut versuchen.")
    digest = str(asset.get("digest") or "")
    return UpdateInfo(
        version=tag.lstrip("v"),
        notes=str(release.get("body") or "").strip(),
        asset_name=str(asset["name"]),
        url=str(asset["browser_download_url"]),
        size=int(asset.get("size") or 0),
        sha256=digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else "",
        page_url=str(release.get("html_url") or ""),
    )


# ----------------------------------------------------------------------
# Herunterladen und starten
# ----------------------------------------------------------------------
def safe_name(name: str) -> str:
    """Nur den Dateinamen aus dem Release übernehmen (kein Pfad)."""
    cleaned = os.path.basename(name.replace("\\", "/"))
    if not cleaned or cleaned.startswith("."):
        raise UpdateError("Ungültiger Dateiname im Release.")
    return cleaned


def download(info: UpdateInfo, dest_dir, progress=None, cancelled=None) -> Path:
    """Lädt den Installer nach ``dest_dir``. ``progress(gelesen, gesamt)``; ``cancelled()`` bricht ab."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / safe_name(info.asset_name)
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    read = 0
    try:
        with _open(info.url, "application/octet-stream") as response, open(partial, "wb") as out:
            total = int(response.headers.get("Content-Length") or info.size or 0)
            while True:
                if cancelled is not None and cancelled():
                    raise UpdateCancelled("Abgebrochen.")
                block = response.read(CHUNK)
                if not block:
                    break
                out.write(block)
                digest.update(block)
                read += len(block)
                if progress is not None:
                    progress(read, total)
    except UpdateError:
        _remove(partial)
        raise
    except (urllib.error.URLError, OSError) as exc:
        _remove(partial)
        raise UpdateError("Der Download ist fehlgeschlagen. Bitte Internetverbindung prüfen und erneut versuchen.") from exc

    if info.size and read != info.size:
        _remove(partial)
        raise UpdateError("Der Download ist unvollständig. Bitte erneut versuchen.")
    if info.sha256 and digest.hexdigest() != info.sha256:
        _remove(partial)
        raise UpdateError("Die heruntergeladene Datei ist beschädigt (Prüfsumme stimmt nicht). Bitte erneut versuchen.")
    os.replace(partial, target)
    return target


def _remove(path: Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass


def cleanup(folder) -> None:
    """Räumt alte Downloads auf (beim Start läuft kein Download mehr)."""
    try:
        for entry in Path(folder).iterdir():
            if entry.is_file():
                _remove(entry)
    except OSError:
        pass


_MAC_SCRIPT = r'''#!/bin/bash
# Ersetzt die laufende App durch die neue Version aus der DMG und startet sie neu.
DMG="$1"; APP="$2"; PID="$3"; LOG="$4"
exec >>"$LOG" 2>&1
echo "== $(date) Update $DMG -> $APP"
for i in $(seq 1 120); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
MNT="$(mktemp -d /tmp/liedmanager-update.XXXXXX)"
manual() { echo "automatisch nicht möglich: $1"; open "$DMG"; exit 1; }
hdiutil attach "$DMG" -nobrowse -noverify -noautoopen -mountpoint "$MNT" -quiet || manual "DMG lässt sich nicht öffnen"
NEW="$MNT/LiedManager.app"
[ -d "$NEW" ] || { hdiutil detach "$MNT" -quiet -force; manual "App fehlt in der DMG"; }
[ -w "$(dirname "$APP")" ] || { hdiutil detach "$MNT" -quiet -force; manual "kein Schreibrecht für $(dirname "$APP")"; }
rm -rf "$APP.alt"
mv "$APP" "$APP.alt" || { hdiutil detach "$MNT" -quiet -force; manual "alte App lässt sich nicht verschieben"; }
if ditto "$NEW" "$APP"; then
  rm -rf "$APP.alt"
else
  rm -rf "$APP"; mv "$APP.alt" "$APP"
  hdiutil detach "$MNT" -quiet -force
  manual "Kopieren fehlgeschlagen"
fi
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
hdiutil detach "$MNT" -quiet -force
rm -f "$DMG"
open "$APP"
echo "fertig"
'''


def _mac_app_path():
    """Pfad der laufenden .app (nur in der gebauten App), sonst ``None``."""
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def can_update_silently() -> bool:
    """True, wenn das Update ohne weitere Handgriffe eingespielt werden kann."""
    if sys.platform.startswith("win"):
        return True
    return sys.platform == "darwin" and getattr(sys, "frozen", False) and _mac_app_path() is not None


def launch_installer(path) -> bool:
    """Startet die Installation, ohne dass jemand etwas klicken muss. Danach muss sich das Programm beenden.

    Windows: Installer läuft im stillen Modus (zeigt nur den Fortschritt), schließt LiedManager, ersetzt die Dateien
    und startet das Programm neu. Mac: ein Hilfsskript wartet auf das Ende des Programms, ersetzt die App und startet sie.
    Gibt ``False`` zurück, wenn stattdessen nur die DMG geöffnet wurde (Nutzer muss ziehen).
    """
    path = str(path)
    if sys.platform.startswith("win"):
        flags = 0x00000008 | 0x00000200 | 0x08000000     # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
        try:
            subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL", "/CLOSEAPPLICATIONS"],
                             creationflags=flags, close_fds=True)
        except OSError as exc:
            log.warning("Stiller Start des Installers nicht möglich (%s) – normaler Start.", exc)
            os.startfile(path)  # noqa: S606  (wie Doppelklick; zeigt bei Bedarf die Administrator-Abfrage)
            return False
        return True
    if sys.platform == "darwin":
        app = _mac_app_path() if getattr(sys, "frozen", False) else None
        if app is None:
            subprocess.Popen(["open", path])
            return False
        import tempfile
        script = Path(tempfile.gettempdir()) / "liedmanager-update.sh"
        script.write_text(_MAC_SCRIPT, encoding="utf-8")
        script.chmod(0o755)
        log_file = Path.home() / "Library" / "Logs" / "LiedManager-Update.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["/bin/bash", str(script), path, str(app), str(os.getpid()), str(log_file)],
                         start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return True
    raise UpdateError("Auf diesem System kann der Installer nicht gestartet werden.")
