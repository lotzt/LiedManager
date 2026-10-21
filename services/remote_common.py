"""Gemeinsame Bausteine der Website-Steuerung (``services/remote_relay.py`` und ``ui/web_remote_ui.py``)."""

UPLOAD_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")   # erlaubte Bilder beim Hochladen vom Handy


class RemoteError(Exception):
    """Fehler mit Meldung und HTTP-Status für die Weboberfläche."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status
