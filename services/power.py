"""Hält Rechner, Bildschirm und Programm wach, solange der Pausentimer läuft.

Ohne das darf der Rechner einschlafen, der Beamer dunkel werden, und macOS („App Nap“) bzw. Windows
(Energiesparmodus für Hintergrundprogramme) verlangsamen ein Programm, das gerade nicht im Vordergrund steht.
Dann kämen die Folienwechsel zu spät oder gar nicht. Alle Aufrufe sind ungefährlich: schlägt etwas fehl,
wird nur ein Hinweis ins Protokoll geschrieben.
"""
import logging
import subprocess
import sys

log = logging.getLogger(__name__)

_active = False
_mac_token = None

# Windows: SetThreadExecutionState
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002

# macOS: NSActivityUserInitiated (kein App Nap, kein Ruhezustand) + Bildschirm nicht abdunkeln
_NS_ACTIVITY_OPTIONS = 0x00FFFFFF | (1 << 40)


def _mac_messenger():
    import ctypes
    import ctypes.util

    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    ctypes.cdll.LoadLibrary(ctypes.util.find_library("Foundation"))
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    send = objc.objc_msgSend
    send.restype = ctypes.c_void_p

    def msg(target, selector: bytes, *args, argtypes=()):
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, *argtypes]
        return send(target, objc.sel_registerName(selector), *args)

    return objc, msg


def _mac_begin(reason: str):
    import ctypes

    objc, msg = _mac_messenger()
    info = msg(objc.objc_getClass(b"NSProcessInfo"), b"processInfo")
    text = msg(objc.objc_getClass(b"NSString"), b"stringWithUTF8String:", reason.encode("utf-8"),
               argtypes=(ctypes.c_char_p,))
    token = msg(info, b"beginActivityWithOptions:reason:", _NS_ACTIVITY_OPTIONS, text,
                argtypes=(ctypes.c_uint64, ctypes.c_void_p))
    if not token:
        raise OSError("beginActivityWithOptions lieferte keine Aktivität")
    return msg(token, b"retain")


def _mac_end(token) -> None:
    import ctypes

    objc, msg = _mac_messenger()
    info = msg(objc.objc_getClass(b"NSProcessInfo"), b"processInfo")
    msg(info, b"endActivity:", token, argtypes=(ctypes.c_void_p,))
    msg(token, b"release")


def _win_set(flags: int) -> None:
    import ctypes

    function = ctypes.windll.kernel32.SetThreadExecutionState
    function.argtypes = [ctypes.c_uint32]
    function.restype = ctypes.c_uint32
    if not function(flags):
        raise OSError("SetThreadExecutionState schlug fehl")


def keep_awake(reason: str = "LiedManager: Pausentimer läuft") -> bool:
    """Rechner, Bildschirm und Programm wach halten. ``True``, wenn es geklappt hat (auf anderen Systemen ``False``)."""
    global _active, _mac_token
    if _active:
        return True
    try:
        if sys.platform == "darwin":
            _mac_token = _mac_begin(reason)
        elif sys.platform.startswith("win"):
            _win_set(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED)
        else:
            return False
    except Exception as exc:
        log.warning("Wach-halten nicht möglich: %s", exc)
        return False
    _active = True
    return True


def release() -> None:
    """Normales Energiesparen wieder erlauben (mehrfaches Aufrufen schadet nicht)."""
    global _active, _mac_token
    if not _active:
        return
    _active = False
    try:
        if sys.platform == "darwin" and _mac_token:
            _mac_end(_mac_token)
        elif sys.platform.startswith("win"):
            _win_set(_ES_CONTINUOUS)
    except Exception as exc:
        log.warning("Wach-halten konnte nicht beendet werden: %s", exc)
    _mac_token = None


POWERPOINT_BUNDLE_ID = "com.microsoft.Powerpoint"


def exempt_from_app_nap(bundle_id: str) -> bool:
    """macOS: Ein anderes Programm (hier PowerPoint) im Hintergrund nicht drosseln lassen.

    Läuft die Pausenpräsentation, steht LiedManager im Vordergrund und PowerPoint im Hintergrund. macOS
    verlangsamt solche Programme („App Nap“); PowerPoint antwortet dann zu spät oder gar nicht auf den
    Folienwechsel. Die Einstellung ``NSAppSleepDisabled`` gilt ab dem nächsten Start des Programms – der
    Pausentimer startet PowerPoint beim Öffnen der Präsentation und beendet es wieder beim Schließen.
    Unter Windows gibt es das Problem nicht (Rückgabe ``False``).
    """
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(["defaults", "write", bundle_id, "NSAppSleepDisabled", "-bool", "YES"],
                                capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("App Nap für %s konnte nicht abgeschaltet werden: %s", bundle_id, exc)
        return False
    if result.returncode != 0:
        # PowerPoint liegt in einem geschützten Ordner (Sandbox) – das Schreiben kann scheitern. Der Pausentimer geht auch so.
        log.info("App Nap für %s konnte nicht abgeschaltet werden: %s", bundle_id,
                    result.stderr.decode("utf-8", "replace").strip())
        return False
    return True


def is_active() -> bool:
    return _active
