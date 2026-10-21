# LiedManager – Neue Version veröffentlichen (voll automatisch)

## Einmalig einrichten (ca. 5 Minuten)
Code und Releases liegen im **selben** Repository `LiedManager`. Es muss **öffentlich** sein, damit der Auto-Updater im
Programm die Releases ohne Anmeldung lesen kann. Die Datenbank `LiedManager.db` wird durch `.gitignore` nicht hochgeladen;
vor dem Veröffentlichen prüfen, dass im Code und in der Git-Historie keine Zugangsdaten stehen.

1. Repository auf github.com anlegen (`LiedManager`), Code hochladen:
   ```
   git init
   git add -A
   git commit -m "LiedManager 2.0"
   git branch -M main
   git remote add origin https://github.com/DEIN-NAME/LiedManager.git
   git push -u origin main
   ```
2. **Settings → General → ganz unten → Change visibility → Public.**
3. **Settings → Actions → General → Workflow permissions → „Read and write permissions“.**
   Ein eigener Token oder ein zweites Repository ist nicht nötig; der Workflow nutzt den eingebauten Token.

Öffentliche Repositories haben unbegrenzte kostenlose Actions-Minuten.

## Jede neue Version
```
python tools/release.py 2.1.0
```
Das Skript setzt die Versionsnummer (`version.py`), committet, setzt den Tag `v2.1.0` und pusht.
GitHub baut dann von selbst (Reiter **Actions**, dauert ca. 10–15 Minuten) und legt im selben Repository unter **Releases** an:

| Datei | Für |
|---|---|
| `LiedManager-2.1.0-Windows-Setup.exe` | Windows-Installer |
| `LiedManager-2.1.0-Windows-Portable.zip` | Windows ohne Installation |
| `LiedManager-2.1.0-macOS-arm64.dmg` | Mac mit Apple-Chip (M1–M4); Intel-Macs werden nicht mehr gebaut |

Versionsnummern: `GROSS.MITTEL.KLEIN` – Fehlerkorrektur → 2.0.1, neue Funktion → 2.1.0, großer Umbau → 3.0.0.
Die Version steht im Fenstertitel, in den Einstellungen, in den Datei-Eigenschaften der .exe und in der Mac-App.

Nur testen ohne Release: **Actions → Build & Release → Run workflow**. Die Screenshots der Oberfläche
(Artefakte `screenshots-…`) zeigen, wie das Programm auf Windows und Mac aussieht.

## Wo liegen die Daten der installierten App?
Der Datenordner wird bei Updates und beim Deinstallieren **nicht** angefasst:
- Windows: `%APPDATA%\LiedManager`
- Mac: `~/Library/Application Support/LiedManager`

Dort hinein gehören `LiedManager.db` (beim ersten Start fragt das Programm danach) und optional eigene
Pausenfolien im Unterordner `pausentimer` (werden nicht mitgeliefert, jeder legt seine eigenen dort ab). Dort liegt auch `liedmanager.log`.

## Automatische Updates im Programm
Das Programm fragt beim Start (abschaltbar unter Einstellungen → Daten) bei GitHub nach dem neuesten Release und
vergleicht es mit seiner Versionsnummer. Gibt es eine neuere, bietet es an, den Installer herunterzuladen:
- **Windows:** LiedManager beendet sich, der Installer läuft im stillen Modus (nur ein Fortschrittsbalken) und startet das Programm danach neu.
- **Mac:** LiedManager beendet sich, ein Hilfsskript ersetzt die App und startet sie neu (Protokoll: `~/Library/Logs/LiedManager-Update.log`).
  Geht das nicht (z. B. App liegt nicht in einem beschreibbaren Ordner), öffnet sich stattdessen die DMG zum Ziehen auf „Programme“.
Während Aufnahme, Pausentimer oder Beamer-Bild laufen, wird nichts installiert. „Diese Version überspringen“ merkt sich das.

Voraussetzungen:
- **Das Repository muss öffentlich sein.** Bei einem privaten Repository kann das Programm die Releases nicht lesen
  (es meldet dann „Es wurde kein Release gefunden“).
- Die Dateinamen der Release-Dateien sind ein fester Vertrag (siehe Tabelle oben: `…-Windows-Setup.exe`, `…-macOS-arm64.dmg`).
  Der Workflow prüft sie vor dem Veröffentlichen.
- Das Repository trägt der Build selbst ein (`tools/build_assets.py` nimmt `GITHUB_REPOSITORY`). Beim
  Start aus dem Quellcode ist die Update-Suche aus.

## Warnungen beim ersten Öffnen (ohne Signatur)
- **Windows:** SmartScreen → „Weitere Informationen“ → „Trotzdem ausführen“.
- **Mac:** Rechtsklick auf die App → „Öffnen“ → „Öffnen“ (einmalig). Kamera und Mikrofon fragt das Programm
  gleich beim Start an (mit einem Hinweis vorab); die PowerPoint-Steuerung fragt der Mac beim ersten Pausentimer.
  Wurde etwas abgelehnt, zeigt das Programm, wo man es unter Systemeinstellungen → Datenschutz & Sicherheit nachholt.
  Ohne Apple-Signatur setzt jede neu gebaute Version diese Freigaben zurück.

## Optional: ohne Warnungen (Mac-Signatur + Notarisierung)
Benötigt einen Apple-Developer-Account (99 $/Jahr). Auf GitHub unter **Settings → Secrets and variables → Actions**
diese Secrets anlegen – der Workflow signiert und notarisiert dann automatisch:
`MACOS_CERT_P12` (Zertifikat „Developer ID Application“ als Base64), `MACOS_CERT_PASSWORD`, `MACOS_SIGN_IDENTITY`,
`APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD` (app-spezifisches Passwort).
Für Windows ist ein Code-Signing-Zertifikat nötig (kostenpflichtig); ohne bleibt die SmartScreen-Warnung.

## Lokal bauen (ohne GitHub)
```
pip install -r requirements.txt pyinstaller Pillow
python tools/build_assets.py
pyinstaller --noconfirm LiedManager.spec
```
Ergebnis in `dist/` (Windows: Ordner `LiedManager` mit `LiedManager.exe`; Mac: `LiedManager.app`).
Gebaut werden kann nur für das System, auf dem man gerade arbeitet.
