"""Namen der Einstellungen, die an mehreren Stellen gelesen oder geschrieben werden.

Ein Tippfehler in einem Namen würde nicht auffallen (es käme still der Standardwert zurück) – deshalb stehen die Namen
hier einmal und überall wird die Konstante benutzt. Die Texte selbst bleiben gleich, damit vorhandene Einstellungen
weiter gelten.
"""
KEY_PRESENTATION_SEASON = "presentation_season"     # Jahreszeit der Pausenfolie
KEY_DATABASE_PATH = "database_path"                 # Pfad zur Lieder-Datenbank (leer = automatisch suchen)
KEY_RECORDING_PATH = "recording_path"               # Ordner für Predigt-Aufnahmen
KEY_FULLSCREEN_MODE = "fullscreen_mode"             # Beamer-Bild im Vollbild (sonst normales Fenster)
KEY_PAUSE_TEXT = "pause_text"                       # Ansagen im Pausentimer
KEY_CAMERA_1_NAME = "camera_1_name"                 # Gerätename der oberen Kamera
KEY_CAMERA_2_NAME = "camera_2_name"                 # Gerätename der unteren Kamera
KEY_ATEM_ENABLED = "atem_enabled"                   # ATEM-Mischer automatisch ansteuern
KEY_ATEM_IP = "atem_ip"                             # IP-Adresse des ATEM-Mischers
KEY_ATEM_PRES_CHANNEL = "atem_pres_channel"         # ATEM-Eingang für Präsentation/Pausentimer
KEY_ATEM_CAM_CHANNEL = "atem_cam_channel"           # ATEM-Eingang für die Seitenleisten-Kamera
KEY_ATEM_DEFAULT_CHANNEL = "atem_default_channel"   # ATEM-Eingang nach dem Schließen
KEY_ATEM_START_CHANNEL = "atem_start_channel"       # ATEM-Eingang beim Programmstart (0 = Schwarz)
KEY_AUDIO_1_NAME = "audio_1_name"                  # Anzeigename von Audio 1 (z. B. „Piano“)
KEY_AUDIO_2_NAME = "audio_2_name"                  # Anzeigename von Audio 2 (z. B. „Gesang“)
KEY_MAIN_WINDOW_X = "main_window_x"                 # Position des Hauptfensters
KEY_MAIN_WINDOW_Y = "main_window_y"                 # Position des Hauptfensters
