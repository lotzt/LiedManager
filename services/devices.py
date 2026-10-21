"""Audiogeräte über stabile IDs auswählen (statt über die Listenposition, die sich ändern kann)."""
from PyQt6.QtMultimedia import QMediaDevices

KEY_OUTPUT = "audio_output_id"
KEY_INPUT = "mic_id"


def device_key(device) -> str:
    return bytes(device.id()).hex()


def _find(devices, key: str):
    if not key:
        return None
    for device in devices:
        if device_key(device) == key:
            return device
    return None


def find_output(key: str):
    """Gespeichertes Ausgabegerät oder ``None`` (= Systemstandard)."""
    return _find(QMediaDevices.audioOutputs(), key)


def find_input(key: str):
    """Gespeichertes Eingabegerät oder ``None`` (= Systemstandard)."""
    return _find(QMediaDevices.audioInputs(), key)
