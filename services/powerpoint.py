"""Pausentimer: steuert eine PowerPoint-Vorlage (macOS: AppleScript, Windows: PowerShell/COM).

Alle Skript-Aufrufe laufen asynchron (QProcess), die Oberfläche bleibt dabei bedienbar.
Die Folie wechselt automatisch: Start -> 5 Minuten vor Ende -> 1 Minute vor Ende.
"""
import base64
import datetime
import logging
import math
import os
import shutil
import sys
import tempfile

from PyQt6.QtCore import QObject, QProcess, QTime, QTimer, pyqtSignal

from paths import custom_pausentimer_dir
from services import atem, power
from services.settings import app_settings

log = logging.getLogger(__name__)

SLIDE_START, SLIDE_5MIN, SLIDE_1MIN = 1, 2, 3
SLIDE_END = 63                 # „Ende!“; die Folien 3 bis 62 zeigen 60 bis 1 (eine Folie pro Sekunde)

SCRIPT_TIMEOUT_MS = 20_000     # Folienwechsel/Schließen: länger darf ein Skript nicht hängen
OPEN_TIMEOUT_MS = 90_000       # PowerPoint starten (große Datei, erste Rückfrage zur Automatisierung am Mac)


def slide_for_seconds_left(seconds_left: float) -> int:
    """Folie zur Restzeit. In der letzten Minute zählt die Vorlage sekundenweise herunter (Folie 3 = „60“ …
    Folie 62 = „1“, Folie 63 = „Ende!“). Den Takt gibt LiedManager vor, nicht PowerPoint: dessen eigene
    Zeitschaltung der Folien bleibt stehen, sobald PowerPoint nicht das aktive Programm ist."""
    if seconds_left <= 0:
        return SLIDE_END
    if seconds_left <= 60:
        return min(SLIDE_END - 1, max(SLIDE_1MIN, SLIDE_END - math.ceil(seconds_left)))
    if seconds_left <= 300:
        return SLIDE_5MIN
    return SLIDE_START


def template_path(season: str):
    """Die Vorlage „pausentimer_<Jahreszeit>.pptx“ im Datenordner (…/LiedManager/pausentimer). Mitgeliefert wird keine."""
    return custom_pausentimer_dir() / f"pausentimer_{season}.pptx"


def write_announcements(pptx_path: str, lines) -> None:
    """Schreibt die Ansagen in die erste Folie und behält dabei Schrift, Größe, Farbe und Stil der Vorlage."""
    try:
        from pptx import Presentation
    except ImportError:
        log.info("python-pptx nicht installiert – Ansagen werden nicht in die Folie geschrieben.")
        return

    prs = Presentation(pptx_path)
    if len(prs.slides) == 0:
        return
    shapes = list(prs.slides[0].shapes)
    target = (next((s for s in shapes if s.name == "AnsagenTextfeld"), None)
              or next((s for s in shapes if s.has_text_frame), None))
    if target is None or not target.has_text_frame:
        return

    tf = target.text_frame
    paragraphs = list(tf.paragraphs)

    sample = None  # (name, size, color, bold, italic) der ersten Textzeile
    if paragraphs:
        source = paragraphs[0].runs[0].font if paragraphs[0].runs else paragraphs[0].font
        sample = (source.name, source.size, source.color,
                  getattr(source, "bold", None), getattr(source, "italic", None))

    for i, line in enumerate(lines):
        paragraph = paragraphs[i] if i < len(paragraphs) else tf.add_paragraph()
        paragraph.text = line
        if sample is None:
            continue
        name, size, color, bold, italic = sample
        for run in paragraph.runs:
            if name:
                run.font.name = name
            if size:
                run.font.size = size
            if color:
                try:
                    run.font.color.rgb = color.rgb
                except Exception:
                    pass
            if bold is not None:
                run.font.bold = bold
            if italic is not None:
                run.font.italic = italic

    for paragraph in paragraphs[len(lines):]:
        paragraph.text = ""

    prs.save(pptx_path)


_OPEN_SCRIPT = '''
tell application "Microsoft PowerPoint"
    open POSIX file "{path}"
    run slide show slide show settings of active presentation
end tell
'''

_CLOSE_SCRIPT = '''
tell application "Microsoft PowerPoint"
    if (count of presentations) > 0 then
        close active presentation saving no
    end if
    quit
end tell
'''

_GOTO_SCRIPT = '''
tell application "Microsoft PowerPoint"
    if (count of slide show windows) is 0 then return "wait"
    set theView to slide show view of slide show window 1
    try
        go to slide theView number {slide}
        return "ok"
    on error errMsg1
        try
            go to first slide theView
            repeat {steps} times
                go to next slide theView
            end repeat
            return "ok"
        on error errMsg2
            return "error: " & errMsg1 & " | " & errMsg2
        end try
    end try
end tell
'''


# --- Windows: PowerShell + PowerPoint-COM (ohne zusätzliche Pakete) ---
_PS_OPEN = """
$ErrorActionPreference = 'Stop'
try {{
  $ppt = New-Object -ComObject PowerPoint.Application
  $pres = $ppt.Presentations.Open('{path}', 0, 0, -1)
  $pres.SlideShowSettings.Run() | Out-Null
  exit 0
}} catch {{ Write-Output $_.Exception.Message; exit 1 }}
"""

_PS_CLOSE = """
try {
  $ppt = [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application')
  foreach ($p in @($ppt.Presentations)) { $p.Saved = -1; $p.Close() }
  $ppt.Quit()
} catch {}
exit 0
"""

_PS_GOTO = """
$ErrorActionPreference = 'Stop'
try {{
  $ppt = [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application')
  if ($ppt.SlideShowWindows.Count -eq 0) {{ Write-Output 'wait'; exit 0 }}
  $ppt.SlideShowWindows.Item(1).View.GotoSlide({slide})
  Write-Output 'ok'
}} catch {{ Write-Output ('error: ' + $_.Exception.Message); exit 1 }}
"""


def supported() -> bool:
    return sys.platform == "darwin" or sys.platform.startswith("win")


def _command(mac_script: str, ps_script: str):
    """(Programm, Argumente) für das jeweilige Betriebssystem."""
    if sys.platform == "darwin":
        return "osascript", ["-e", mac_script]
    encoded = base64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")
    return "powershell.exe", ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                              "-EncodedCommand", encoded]


def open_command(path: str):
    ps_path = path.replace("'", "''")
    return _command(_OPEN_SCRIPT.format(path=path), _PS_OPEN.format(path=ps_path))


def close_command():
    return _command(_CLOSE_SCRIPT, _PS_CLOSE)


def goto_command(slide: int):
    return _command(_GOTO_SCRIPT.format(slide=slide, steps=slide - 1), _PS_GOTO.format(slide=slide))


class PausentimerController(QObject):
    """Startet/stoppt die Pausenpräsentation und wechselt die Folien passend zur Restzeit.

    Signale:
        running_changed(bool)   True, sobald der Start angefordert wurde; False nach Stopp oder Fehler
        error(str)              Meldung für den Benutzer
    """
    running_changed = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._end_time = QTime(11, 30)
        self._finish = None
        self._slide = None
        self._script_busy = False
        self._last_problem = ""      # zuletzt protokollierte Störung beim Folienwechsel (nicht jede Sekunde loggen)

        self._timer = QTimer(self)
        self._timer.setInterval(250)   # nur zum Prüfen; ein Skript läuft erst, wenn sich die Folie ändern muss
        self._timer.timeout.connect(self._check_slide)

    @property
    def running(self) -> bool:
        return self._running

    def seconds_left(self):
        """Restzeit der Pause in Sekunden (``None``, wenn der Pausentimer nicht läuft)."""
        if not self._running or self._finish is None:
            return None
        return max(0, int((self._finish - datetime.datetime.now()).total_seconds()))

    # ------------------------------------------------------------------
    # Öffentliche Steuerung
    # ------------------------------------------------------------------
    def start(self, lines, end_time: QTime) -> None:
        if self._running:
            return
        if not supported():
            self.error.emit("Der Pausentimer wird nur unter macOS und Windows unterstützt.")
            return
        season = app_settings().value("presentation_season", "frühling", type=str)
        source = template_path(season)
        if not source.exists():
            self.error.emit(f"Keine Pausenfolie gefunden: „{source.name}“.\n\nLege deine PowerPoint-Vorlage unter diesem Namen in "
                            f"den Ordner\n{source.parent}\n(Einstellungen → Anzeige → „Ordner für Pausenfolien öffnen“).")
            return

        try:
            temp_path = os.path.join(tempfile.gettempdir(), f"pausentimer_temp_{season}.pptx")
            shutil.copy(source, temp_path)
            try:
                write_announcements(temp_path, lines)
            except Exception as exc:  # fehlerhafte Ansagen sollen den Start nicht verhindern
                log.warning("Ansagen konnten nicht in die Vorlage geschrieben werden: %s", exc)
        except OSError as exc:
            self.error.emit(f"Die Vorlage konnte nicht vorbereitet werden:\n{exc}")
            return

        atem.switch("presentation")
        self._end_time = end_time
        self._finish = self._compute_finish()
        self._slide = None
        self._running = True
        power.keep_awake()    # Rechner/Beamer nicht einschlafen lassen, Programm im Hintergrund nicht drosseln
        power.exempt_from_app_nap(power.POWERPOINT_BUNDLE_ID)   # auch PowerPoint im Hintergrund nicht drosseln
        self.running_changed.emit(True)

        self._run_script(open_command(os.path.abspath(temp_path)), self._on_open_finished,
                         timeout_ms=OPEN_TIMEOUT_MS)

    def stop(self) -> None:
        if not self._running:
            return
        self._timer.stop()
        self._running = False
        self._slide = None
        power.release()
        self._run_script(close_command(), lambda ok, out: None)
        self.running_changed.emit(False)
        atem.switch("default")

    def set_end_time(self, end_time: QTime) -> None:
        """Endzeit wurde geändert -> Restzeit neu berechnen, Folie neu bestimmen."""
        self._end_time = end_time
        if self._running:
            self._finish = self._compute_finish()
            self._slide = None

    # ------------------------------------------------------------------
    # Intern
    # ------------------------------------------------------------------
    def _compute_finish(self) -> datetime.datetime:
        now = datetime.datetime.now()
        finish = datetime.datetime.combine(
            now.date(), datetime.time(self._end_time.hour(), self._end_time.minute())
        )
        if finish <= now:
            finish += datetime.timedelta(days=1)
        return finish

    def _on_open_finished(self, ok: bool, output: str) -> None:
        if not self._running:
            return
        if ok:
            self._timer.start()
            return
        log.error("PowerPoint-Präsentation konnte nicht gestartet werden: %s", output)
        self._running = False
        power.release()
        self.running_changed.emit(False)
        atem.switch("default")
        self.error.emit("Die PowerPoint-Präsentation konnte nicht gestartet werden.\n"
                        "Ist Microsoft PowerPoint installiert?")

    def _check_slide(self) -> None:
        if not self._running or self._script_busy:
            return
        seconds_left = (self._finish - datetime.datetime.now()).total_seconds()
        target = slide_for_seconds_left(seconds_left)
        if target == self._slide:
            return
        def done(ok: bool, output: str, target=target):
            if ok and output == "ok":
                self._slide = target
                self._last_problem = ""
                return
            problem = output or "keine Antwort von PowerPoint"
            if problem != self._last_problem:   # Folienwechsel wird laufend neu versucht
                self._last_problem = problem
                log.warning("Folienwechsel auf Folie %d nicht möglich: %s", target, problem)

        self._run_script(goto_command(target), done)

    def _run_script(self, command, callback, timeout_ms: int = SCRIPT_TIMEOUT_MS) -> None:
        """Führt (Programm, Argumente) asynchron aus; ``callback(ok, stdout)`` wird genau einmal aufgerufen.

        Hängt das Skript länger als ``timeout_ms`` (z. B. PowerPoint antwortet nicht), wird es beendet und als
        Fehler gemeldet. Sonst bliebe ``_script_busy`` für immer gesetzt und es gäbe keine Folienwechsel mehr.
        """
        program, args = command
        process = QProcess(self)
        if sys.platform.startswith("win"):  # kein kurz aufblitzendes Konsolenfenster
            try:
                def no_window(arguments):
                    arguments.flags |= 0x08000000  # CREATE_NO_WINDOW
                process.setCreateProcessArgumentsModifier(no_window)
            except Exception:
                pass
        state = {"called": False}
        self._script_busy = True

        watchdog = QTimer(process)
        watchdog.setSingleShot(True)
        watchdog.setInterval(timeout_ms)

        def release():
            try:
                process.deleteLater()
            except RuntimeError:  # Objekt ist schon zerstört (z. B. beim Beenden des Programms)
                pass

        def finish(ok: bool, output: str):
            if state["called"]:
                return
            state["called"] = True
            watchdog.stop()
            self._script_busy = False
            # Ein per kill() beendeter Prozess läuft kurz weiter: erst löschen, wenn er wirklich beendet ist
            # (siehe on_finished), sonst meldet Qt „Destroyed while process is still running“.
            try:
                idle = process.state() == QProcess.ProcessState.NotRunning
            except RuntimeError:
                idle = False
            if idle:
                release()
            callback(ok, output)

        def on_timeout():
            if state["called"]:
                return
            log.warning("Skript für den Pausentimer reagiert nicht (%.1f s) – wird beendet.", timeout_ms / 1000)
            process.kill()
            finish(False, "Zeitüberschreitung")

        def on_finished(code, _status):
            if state["called"]:  # schon per Zeitüberschreitung abgeschlossen: nur noch aufräumen
                release()
                return
            try:
                output = bytes(process.readAllStandardOutput()).decode("utf-8", "replace").strip()
            except RuntimeError:  # Objekt wird gerade zerstört (z. B. beim Beenden des Programms)
                output = ""
                code = -1
            finish(code == 0, output)

        def on_error(err):
            if err == QProcess.ProcessError.FailedToStart:
                finish(False, f"{err}")

        watchdog.timeout.connect(on_timeout)
        watchdog.start()
        process.finished.connect(on_finished)
        process.errorOccurred.connect(on_error)
        process.start(program, args)
