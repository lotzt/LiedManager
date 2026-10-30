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
2. *Einstellungen → Lieder*: „Abgleich einschalten“, Adresse (`https://…/sync/sync.php`) und dasselbe Token eintragen (wird sofort gespeichert; beim Ausschalten bleiben beide erhalten).
3. Fertig. Beim ersten Mal gilt der aktuelle Stand als Ausgangspunkt, es wird nichts hochgeladen.

Ändert man die Datenbank mit einem Editor, erkennt LiedManager die Änderung und schickt sie zum Server; die anderen
Geräte holen sie ab. Streiten zwei Geräte um dasselbe Lied, gewinnt die jüngere Änderung. Ein Lied wird über seine
Nummer erkannt. Jedes Lied wird einzeln übertragen, bis zu 4 gleichzeitig. Große Lieder (über 6 MB, viel Audio/Bilder) gehen
in Teilen zu je 6 MB hoch und werden auf dem Server in `lm_parts` abgelegt (bis 400 MB je Lied); dafür muss die neue
`server/sync.php` auf dem Server liegen (Tabellen werden automatisch angelegt). Lehnt der Server ein Lied dennoch ab, meldet
das Programm das im Status und macht mit dem Rest weiter. Ältere Programmversionen können Lieder in Teilen nicht lesen.
**Datenbank austauschen:** Eine Datei am selben Ort gilt als Änderung – fehlende Lieder werden dann auf allen Geräten
gelöscht. Soll die neue Datenbank der verbindliche Stand für alle sein, dient *Einstellungen → Lieder → Alles neu
hochladen* (mit Rückfrage): Alle Lieder gehen zum Server, was in dieser Datenbank fehlt, wird überall gelöscht, die anderen
Geräte übernehmen den Stand. Vorher eine Sicherungskopie anlegen; eine leere Datenbank wird nie hochgeladen.
Ohne HTTPS verweigert das Programm den Abgleich, weil das Token sonst offen übertragen würde.
Logik: `services/server_sync.py`, Oberfläche: `ui/sync_ui.py`, Server: `server/sync.php`.

Eine Spalte für CCLI-Nummern (Name enthält „ccli“) wird mit abgeglichen. Fehlt sie auf einem Gerät, legt der Abgleich sie
dort an („CCLI“). Lieder ohne CCLI-Nummer werden dadurch nicht neu gesendet; nur Lieder mit Nummer gehen einmal erneut hoch.

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

### Behringer X AIR 18: Lautstärke und Mute über die Webseite

Einstellungen → Audio → „Behringer X AIR“: Adresse des Pults eintragen (im X AIR Edit unter Setup → Network, am besten feste
IP). LiedManager spricht das Pult per OSC/UDP (Port 10024) an und muss im selben Netzwerk stehen; das Pult selbst braucht keinen Internetzugang.
Die Web-Fernsteuerung zeigt dann im Reiter „Kamera“ die Kanäle 1–8 mit Namen, Regler (lauter/leiser, Anzeige in dB) und Mute-Knopf.
Neue `remote.php` hochladen (Zugangsdaten oben erneut eintragen). Logik: `services/xair.py`. Nicht an einem echten Pult getestet –
erste Versuche bitte bei leiser Anlage.

Der Knopf „Alles stumm“ unter den acht Reglern schaltet alle Kanäle auf einmal stumm.

### Mehrere Computer

Jeder Computer bekommt unter Einstellungen → Remote einen Namen (sonst der Rechnername). Laufen mehrere, erscheint im Browser oben eine Auswahl;
Steuerung und Bilder gehen nur an den gewählten Computer. Dazu muss die neue `remote.php` auf den Server.

### Probleme automatisch melden

Bei einem unerwarteten Fehler schickt das Programm (wenn die Remote-Steuerung eingerichtet ist) Version, Betriebssystem und
Fehlertext an `remote.php`. Du siehst es im Browser unter „Mehr“ → „Gemeldete Probleme“. Gleiche Fehler werden nur gezählt,
höchstens 10 Meldungen pro Stunde, ohne Internet wartet die Meldung bis zum nächsten Start. Pfade im Benutzerordner werden gekürzt,
es gehen keine Liedtexte, Dateien oder Zugangsdaten raus. Abschalten: Einstellungen → Remote → „Programmfehler automatisch melden“.
**Wichtig:** dazu muss die neue `remote.php` auf den Server (mit deinen Zugangsdaten).

### Bilder von zu Hause hochladen (auch wenn das Programm nicht läuft)

In der Web-Steuerung unter „Bilder“ lassen sich jederzeit Bilder hochladen. Läuft LiedManager nicht, merkt sich die
Website sie vor (bis zu 40 Bilder, 48 MB, 30 Tage) und das Programm holt sie beim nächsten Verbinden ab und legt sie in
der Bilder-Ablage ab. „Vorgemerkte verwerfen“ löscht sie auf dem Server. „Alle entfernen“ (im Programm und im Browser)
leert die Ablage und löscht die hochgeladenen Dateien auch von der Platte.

### Aufnahmen auf die Website laden

Einstellungen → Audio → Aufnahmen (Adresse und Token wie bei der Remote-Steuerung,
die selbst nicht eingeschaltet sein muss). Jede gespeicherte Aufnahme wird in Stücken in den Ordner `aufnahmen` neben
`remote.php` geladen; bricht die Verbindung ab, wird sie später fortgesetzt (Liste: `aufnahmen_hochladen.json` im
Datenordner). Der Ordner ist nicht als Dateiliste einsehbar, die Dateien sind aber über ihre Adresse erreichbar –
wer das nicht möchte, sollte den Ordner per KAS mit einem Passwort schützen. Nach dem Aktualisieren der Programmdatei
`remote.php` neu hochladen (Zugangsdaten oben erneut eintragen).

**Direkt in die WordPress-Mediathek:** Einstellungen → Audio → Aufnahmen → „Automatisch in die WordPress-Mediathek hochladen“. Eintragen: Adresse der
WordPress-Seite, Benutzername und ein *Anwendungspasswort* (WordPress → Benutzer → Profil → Anwendungspasswörter, Benutzerrolle
mindestens „Autor“). Die Aufnahme geht dann über die REST-Schnittstelle (`/wp-json/wp/v2/media`) in die Mediathek; `remote.php` wird dafür nicht
gebraucht. WordPress nimmt die Datei in einem Stück an, die Größe begrenzen `upload_max_filesize` und `post_max_size` des Servers. Ist `ffmpeg`
installiert, wird die WAV-Aufnahme vorher in eine MP3 (Mono, 64 kbit/s) umgewandelt – etwa 28 MB pro Stunde statt etwa 160 MB. Logik:
`services/wordpress_upload.py`.

## Prüfen

Bei jedem Push läuft `.github/workflows/tests.yml` auf macOS und Windows (Smoke-Test). Die Zugangsdaten (Token, Passwörter) liegen im Schlüsselbund des Systems (`pip install keyring`). Die Datenbank wird vor dem Abgleich gesichert (Ordner „Datenbank-Sicherungen“, letzte 5).

```
python tools/smoke_test.py
```

Startet die Oberfläche ohne Bildschirm, prüft die wichtigsten Abläufe und legt Screenshots in
`build/screenshots` ab.

## Installer bauen und neue Version veröffentlichen

Siehe [RELEASE.md](RELEASE.md).

## Pausenfolie

Der Pausentimer zeigt in der Pause eine Pausenfolie auf dem Beamer: erst die Ansagen, ab 5 Minuten vor Ende einen Bibelvers,
in der letzten Minute einen Countdown (mit Musik) und am Ende „Ende!“. Gestaltet wird sie in PowerPoint – eine Vorlage wird
**nicht mitgeliefert**, du legst deine eigene ab: *Einstellungen → Pausentimer → „Vorlagen-Ordner“*, dort eine Datei
`pausentimer_<Jahreszeit>.pptx` (`frühling`, `sommer`, `herbst` oder `winter`; die Jahreszeit wählst du daneben).

**Ohne PowerPoint (Standard):** LiedManager übernimmt die Vorlage einmal („Vorlage übernehmen …“ oder automatisch beim
ersten Start des Pausentimers) und zeigt die Folien dann selbst – sofort, ohne Fremdfenster, auf Mac und Windows gleich.
Übernommen werden Bilder, Texte, Schriften, Farben, Positionen, der Bibelvers, der Puls-Effekt des Countdowns und die Musik
(ab welcher Sekunde, Lautstärke). Alles davon lässt sich danach in den Einstellungen ändern, mit Vorschau. Ansagen erscheinen
beim Tippen sofort auf dem Beamer. Schriften, die nur teilweise in der Vorlage stecken (z. B. Montserrat), müssen auf dem
Rechner installiert sein; sonst nimmt das Programm Arial. Logik: `services/pausenfolie.py`, Anzeige: `ui/pause_window.py`.

**Mit PowerPoint:** In den Einstellungen „PowerPoint (wie bisher)“ wählen. Aufbau der Datei (63 Folien):

* Folie 1: Startfolie, mit einem Textfeld namens `AnsagenTextfeld` (sonst das erste Textfeld) für die Ansagen
* Folie 2: Bibelvers (gilt ab 5 Minuten Restzeit)
* Folie 3 bis 62: der Countdown, eine Folie pro Sekunde von 60 bis 1
* Folie 63: „Ende!“

Für diese Art ist Microsoft PowerPoint auf Mac oder Windows nötig.

## Liste der gespielten Lieder

Einstellungen → Lieder → „Liedhistorie“ zeigt die Lieder nach Tag, mit Suche und den am häufigsten gespielten.

Jedes Lied, das auf dem Beamer gezeigt wird, schreibt das Programm mit **Nummer und Titel** (sonst nichts) in **eine einzige
Textdatei** `Gespielte Lieder.txt`, in die immer weiter eingetragen wird. Pro Tag steht eine Kopfzeile mit Wochentag und Datum,
darunter die Lieder; dasselbe Lied direkt hintereinander nur einmal:

    Sonntag, 18.10.2026
    12 – Großer Gott, wir loben dich
    p004 – Befiehl du deine Wege

Das Speichern lässt sich unter *Einstellungen → Lieder → Gespielte Lieder* abschalten.

### Meldung an CCLI

LiedManager meldet nicht selbst an CCLI (dafür ist eine Partner-Zulassung bei CCLI nötig). Stattdessen bereitet es die Meldung vor:

1. Die CCLI-Nummern stehen in einer Spalte der Datenbank (Name enthält „ccli“, z. B. `CCLI`); sie werden mit dem Datenbank-Abgleich
   geteilt. Zum Füllen aus den Liederbüchern von evangeliums.net gibt es `tools/ccli_aus_liederbuch.py` (siehe dort).
2. Beim Klick auf *„Bei CCLI melden“* kommen neu gespielte Lieder automatisch in die Meldeliste `CCLI-Meldung.csv`: nur die
   CCLI-Nummern, eine pro Zeile (neue hinter noch offene; dasselbe Lied am selben Tag einmal). `Gespielte Lieder.txt` (Liedhistorie)
   bleibt dabei unverändert; das Programm merkt sich, bis wohin schon übernommen wurde. Lieder ohne Nummer fehlen (die Statuszeile
   zählt sie). Lieder von sonntags 9–10 Uhr und mittwochs 18:30–19:30 Uhr stehen mit „[nicht melden]“ in der Liste und werden
   nicht gemeldet. Die Zeiten stellst du unter Einstellungen → Lieder → CCLI-Meldung → „Nicht melden (Zeiten)“ ein (z. B. `So 09:00–10:00; Mi 18:30–19:30`,
   leer = alles melden).
3. Danach öffnet sich CCLI „Suchen & Melden“ (https://reporting.ccli.com/search) in einem Browser (du loggst dich selbst ein, das Programm sieht keine Zugangsdaten),
   gibt jede Nummer ein, sucht und klickt „Lied melden“. Nach dem ersten Lied fragt es, ob alles stimmt (weiter / Rest automatisch /
   aufhören). Eingegeben wird nur die CCLI-Nummer. Gemeldete Nummern verschwinden sofort aus `CCLI-Meldung.csv`, nicht Gemeldete bleiben drin;
   ist alles gemeldet, wird die Datei gelöscht. Gemeldetes wird nirgends aufbewahrt (frühere Dateien `CCLI-Meldung-Ergebnis.csv` und
   `Gespielte Lieder (gemeldet).txt` räumt das Programm beim Start weg).
   Voraussetzung: `pip3 install -r requirements-ccli.txt`. Genutzt wird der installierte Google Chrome bzw. Microsoft Edge (auf Windows
   immer vorhanden). Der Browser startet ganz normal, du meldest dich ohne Fernsteuerung an (Login-Seiten laden sonst endlos
   neu); erst danach verbindet sich das Programm lokal mit diesem Fenster. Playwright kommt über `release.yml` auch in die
   fertige App (`LiedManager.spec` packt es ein, sobald es im Build-Python installiert ist).
   Logik: `services/ccli_melden.py`. Die Seite von CCLI wurde nicht automatisiert getestet – bitte mit wenigen Liedern ausprobieren.
