# Drittanbieter-Komponenten

* **PyQt6** (Riverbank Computing) – GPL v3 bzw. kommerzielle Lizenz. Die Installer enthalten PyQt6, daher gilt für das
  fertige Programm die GPL v3; der LiedManager-Quellcode (MIT, siehe `LICENSE`) ist damit kompatibel und liegt offen vor.
* **python-pptx** (MIT), **PyATEMMax** (MIT), **certifi** (MPL-2.0), **keyring** (MIT) – Laufzeit-Bibliotheken.
* **Playwright** (Apache-2.0) – optional, nur für „Bei CCLI melden“ (`requirements-ccli.txt`).
* **PyInstaller** (GPL v2 mit Ausnahme für gebaute Programme) und **Pillow** (MIT-CMU) – nur zum Bauen der Installer
  bzw. der Beispiel-Datenbank, nicht im Programm enthalten.
* **Fraunces** (Schrift, `ui/assets/fonts`) – SIL Open Font License 1.1.
* **Gong** (`ui/assets/gong.wav`) – eigens erzeugt mit `tools/make_gong.py`.
* **Beispiel-Datenbank** (`beispiel/`) – gemeinfreie Liedtexte (entstanden 1529–1862, Verfasser seit über 70 Jahren verstorben), Bilder mit
  `tools/make_example_db.py` erzeugt.
* Pausenfolien und Lieder-Datenbanken werden nicht mitgeliefert; jede Gemeinde verwendet ihre eigenen.
