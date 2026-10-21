# LiedManager

Programm für den Gottesdienst: Lieder suchen und auf dem Beamer zeigen, Predigt aufnehmen,
Kameras und ATEM-Mischer steuern sowie Pausentimer abspielen. Läuft auf Windows und macOS.

## Aus dem Quellcode starten

```
pip install -r requirements.txt
python main.py
```

Beim ersten Start fragt das Programm nach der Datenbank `LiedManager.db`.

## Schriften

Überschriften setzt das Programm in Fraunces (frei, OFL-Lizenz; liegt in `ui/assets/fonts/` und wird in den
Installer aufgenommen), den Text in Arial. Arial und Georgia sind auf Windows und macOS vorhanden und werden
bewusst **nicht** mitgeliefert (Microsoft-Lizenz); sie dienen nur als Ersatz, falls Fraunces fehlt.

## Datenbank auf mehreren Geräten abgleichen

Jedes Gerät behält seine **eigene, lokale** Datenbank – das Programm bleibt also immer benutzbar, auch ohne Internet.
Geteilt werden nur die **Änderungen** (neue, geänderte und gelöschte Lieder, mit Text, Audio und Bildern) über einen
kleinen Server (`server/sync.php`, z. B. bei All-Inkl mit PHP und MySQL). Das Programm gleicht beim Start, danach jede
Minute und auf Knopfdruck im Hintergrund ab – ist gerade kein Internet da, klappt es beim nächsten Versuch.

**Server einrichten (einmalig):**

1. KAS → *Datenbanken* → neue MySQL-Datenbank anlegen (Name, Benutzer, Passwort notieren).
2. `server/sync.php` öffnen und oben `TOKEN` (selbst ausgedachtes, langes Zufallspasswort), `DB_NAME`, `DB_USER`
   und `DB_PASS` eintragen.
3. Die Datei per WebFTP in einen Ordner der Domain legen, z. B. `technik.deine-domain.de/sync/sync.php`
   (die Domain braucht SSL, also `https://`). Die Tabellen legt das Skript beim ersten Aufruf selbst an.

**Auf jedem Gerät:**

1. Die Datenbank auf alle Geräte kopieren (gleicher Ausgangsstand).
2. *Einstellungen → Datenbank*: „Abgleich einschalten“, Adresse (`https://…/sync/sync.php`) und dasselbe Token eintragen (wird sofort gespeichert; beim Ausschalten bleiben beide erhalten).
3. Fertig. Beim ersten Mal gilt der aktuelle Stand als Ausgangspunkt, es wird nichts hochgeladen.

Ändert man die Datenbank mit einem Editor, erkennt LiedManager die Änderung und schickt sie zum Server; die anderen
Geräte holen sie ab. Streiten zwei Geräte um dasselbe Lied, gewinnt die jüngere Änderung. Ein Lied wird über seine
Nummer erkannt. Jedes Lied wird einzeln übertragen; sehr große Lieder (viel Audio) können an den PHP-Grenzen des
Hosters scheitern (`post_max_size`, `memory_limit`) – das Programm meldet das im Status und macht mit dem Rest weiter.
**Datenbank austauschen:** Eine Datei am selben Ort gilt als Änderung – fehlende Lieder werden dann auf allen Geräten
gelöscht. Soll die neue Datenbank der verbindliche Stand für alle sein, dient *Einstellungen → Datenbank → Alles neu
hochladen* (mit Rückfrage): Alle Lieder gehen zum Server, was in dieser Datenbank fehlt, wird überall gelöscht, die anderen
Geräte übernehmen den Stand. Vorher eine Sicherungskopie anlegen; eine leere Datenbank wird nie hochgeladen.
Ohne HTTPS verweigert das Programm den Abgleich, weil das Token sonst offen übertragen würde.
Logik: `services/server_sync.py`, Oberfläche: `ui/sync_ui.py`, Server: `server/sync.php`.

## Remote: Steuerung per Handy über die eigene Website (von überall)

Mit Handy oder Tablet lässt sich LiedManager von überall bedienen – über die eigene Website, per HTTPS und mit PIN. Die Seite
sieht aus wie das Programm und bietet alle Bedienfunktionen:

* **Lied:** suchen, wählen, auf dem Beamer zeigen/schließen, Audio abspielen/pausieren/spulen, Aufnahme starten,
  pausieren, speichern (Prediger steht im Dateinamen), Pausentimer mit Ansagen und Endzeit (ausklappbar)
* **Bilder:** Vorschau, Bild auf dem Beamer zeigen, vor/zurück/schließen, Bilder vom Handy hochladen, entfernen
* **Kamera:** Kamera-Vollbild auf dem Beamer, ATEM-Mischer schalten
* **Zahnrad (Mehr):** Datenbank-Abgleich anstoßen, abmelden; oben immer **Esc** (wie im Programm)

Einen Webserver im Programm selbst (nur im WLAN) gibt es nicht mehr. So funktioniert die Website-Steuerung: LiedManager steht hinter
dem Router und ruft deshalb **von sich aus** bei der Website an (wie beim Datenbank-Abgleich), holt dort die Befehle
des Browsers ab und schickt Zustand und Ergebnisse zurück. **LiedManager muss dafür laufen und online sein**; ist es das
nicht, zeigt die Seite „getrennt“.

**Server einrichten (einmalig):**

1. KAS → *Datenbanken*: MySQL-Datenbank anlegen oder die vom Abgleich mitbenutzen (die Tabellen heißen anders: `lm_rm_…`).
2. `server/remote.php` öffnen und oben `TOKEN` (langes Zufallspasswort, kommt auch ins Programm), `PIN` (Passwort für den
   Browser, mindestens 8 Zeichen) sowie `DB_NAME`, `DB_USER`, `DB_PASS` eintragen.
3. Per WebFTP in einen Ordner der Domain legen, z. B. `technik.deine-domain.de/steuerung/remote.php` (mit SSL). Zum Prüfen
   `…/remote.php?check` öffnen: Dort steht, ob Zugangsdaten und Datenbank in Ordnung sind – und, falls nicht, welcher Wert
   (z. B. „PIN ist zu kurz“) noch nicht stimmt. Die Seite zeigt auch, wann die Datei auf dem Server zuletzt geändert wurde
   (so erkennst du, ob wirklich die neue Datei hochgeladen wurde). Die Tabellen legt die Datei beim
   ersten Aufruf selbst an.

**Im Programm:** *Einstellungen → Remote*: Haken setzen, Adresse von `remote.php` und
dasselbe Token eintragen. Die Statuszeile zeigt „Verbunden – im Browser öffnen: …“. Diese Adresse öffnest du auf dem Handy
und meldest dich mit der PIN aus `remote.php` an.

Sicherheit: HTTPS ist Pflicht (ohne verweigern Programm und Seite den Dienst). Angemeldet wird auf der Website selbst; nur
angemeldete Browser erreichen das Programm. Falsche PINs sperren die Adresse (nach 5 Versuchen 30 s, verdoppelt bis 10 min), alle
Adressen zusammen nach 50 Fehlversuchen in 10 Minuten für 5 Minuten. Die Anmeldung gilt 12 Stunden. Die Einstellungen lassen sich
auch hier nicht ändern. Ein langes, zufälliges Token und eine PIN mit 10 oder mehr Zeichen sind empfehlenswert.

Grenzen: Es darf immer nur **ein** LiedManager mit der Website verbunden sein (zwei würden sich die Befehle teilen). Bilder
vom Handy dürfen bis 8 MB groß sein. Die Reaktion dauert etwa eine halbe Sekunde.

Wird die Seite oder das Design geändert, muss `server/remote.php` neu erzeugt werden: `python tools/build_remote_site.py`
(der Smoke-Test meldet es, wenn man es vergisst). Zugangsdaten gehören nie ins Repository, nur auf den Server. Logik im
Programm: `services/remote_relay.py` (gemeinsame Bausteine: `services/remote_common.py`), Anbindung: `ui/web_remote_ui.py`,
Server: `server/remote_template.php`.

## Prüfen

```
python tools/smoke_test.py
```

Startet die Oberfläche ohne Bildschirm, prüft die wichtigsten Abläufe und legt Screenshots in
`build/screenshots` ab.

## Installer bauen und neue Version veröffentlichen

Siehe [RELEASE.md](RELEASE.md).

## Eigene Pausenfolie (PowerPoint)

Der Pausentimer öffnet eine PowerPoint-Datei im Vollbild und schaltet die Folien passend zur Restzeit um. Eine Vorlage wird
**nicht mitgeliefert** – du legst deine eigene ab: *Einstellungen → Anzeige → „Ordner für Pausenfolien öffnen“*, dort
eine Datei `pausentimer_<Jahreszeit>.pptx` (`frühling`, `sommer`, `herbst` oder `winter`; die Jahreszeit wählst du in den
Einstellungen). Aufbau der Datei (63 Folien):

* Folie 1: Startfolie, mit einem Textfeld namens `AnsagenTextfeld` (sonst das erste Textfeld) für die Ansagen
* Folie 2: „noch 5 Minuten“ (gilt ab 5 Minuten Restzeit)
* Folie 3 bis 62: der Countdown, eine Folie pro Sekunde von 60 bis 1
* Folie 63: „Ende!“

Voraussetzung ist Microsoft PowerPoint auf Mac oder Windows.

## Liste der gespielten Lieder

Jedes Lied, das auf dem Beamer gezeigt wird, schreibt das Programm mit **Nummer und Titel** (sonst nichts) in **eine einzige
Textdatei** `Gespielte Lieder.txt`, in die immer weiter eingetragen wird. Pro Tag steht eine Kopfzeile mit Wochentag und Datum,
darunter die Lieder; dasselbe Lied direkt hintereinander nur einmal:

    Sonntag, 18.10.2026
    12 – Großer Gott, wir loben dich
    p004 – Befiehl du deine Wege

Die Datei öffnest du unter *Einstellungen → Anzeige → „Liste der gespielten Lieder öffnen“*. Mit *Testmodus – nichts
speichern* (im Fenstertitel steht dann „Testmodus“) läuft alles ohne Eintrag, zum Beispiel bei Proben. Das Speichern lässt sich
dort auch ganz abschalten.
