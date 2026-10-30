<?php
/*
 * LiedManager – Website-Steuerung (All-Inkl: PHP + MySQL)
 *
 * Diese Datei wird aus remote_template.php erzeugt (python tools/build_remote_site.py) und enthält die Webseite
 * der Fernsteuerung gleich mit. NICHT von Hand die Seite ändern – nur die Zugangsdaten unten eintragen.
 *
 * Einrichtung: siehe README.md, Abschnitt „Web-Steuerung über die eigene Website“.
 *   1. KAS -> Datenbanken: MySQL-Datenbank anlegen (es darf dieselbe wie für sync.php sein, die Tabellen heißen anders).
 *   2. Unten TOKEN (langes Zufallspasswort, kommt auch in die Einstellungen von LiedManager), PIN (Passwort für den
 *      Browser, mindestens 8 Zeichen) und die Datenbank-Zugangsdaten eintragen.
 *   3. Datei per WebFTP in einen Ordner der Domain legen, z. B. https://deine-domain.de/steuerung/remote.php
 *      (die Domain braucht SSL). Zum Prüfen:  https://deine-domain.de/steuerung/remote.php?check
 *
 * So funktioniert es: LiedManager ruft diese Seite von sich aus an („poll“), schickt den Zustand und holt Aufträge
 * ab. Der Browser meldet sich hier mit der PIN an; seine Befehle werden zu Aufträgen für das Programm, das Ergebnis
 * geht zurück an den Browser. Das Programm muss dafür laufen und online sein.
 */

const TOKEN   = 'HIER-LANGES-ZUFAELLIGES-TOKEN';
const PIN     = 'HIER-PASSWORT-FUER-DEN-BROWSER';
const DB_HOST = 'localhost';
const DB_NAME = 'dXXXXXXX';
const DB_USER = 'dXXXXXXX';
const DB_PASS = 'HIER-DB-PASSWORT';

const FORMAT         = 1;          // Protokollversion (Programm und Website müssen zusammenpassen)
const APP_TIMEOUT    = 25;         // so lange ohne Lebenszeichen gilt das Programm als nicht erreichbar (Sekunden)
const HOLD           = 15;         // so lange wartet das Programm hier auf neue Aufträge (Sekunden)
const JOB_WAIT       = 12;         // so lange wartet der Browser auf das Programm (Sekunden)
const UPLOAD_WAIT    = 30;         // … bei einem Bild-Upload
const SESSION_SECONDS = 43200;     // eine Anmeldung gilt 12 Stunden
const MAX_SESSIONS   = 20;
const MAX_JSON       = 65536;      // größte Anfrage des Browsers (ohne Bild)
const MAX_UPLOAD     = 8388608;    // größtes Bild vom Handy (8 MB; als Text gespeichert wird es ein Drittel größer)
const MAX_APP_BODY   = 4194304;    // größte Meldung vom Programm
const MAX_FAILURES   = 5;          // falsche PINs je Adresse, dann Sperre (30 s, verdoppelt sich bis 10 min)
const GLOBAL_FAILURES = 50;        // falsche PINs von allen Adressen in 10 Minuten, dann 5 Minuten Pause für alle
const INBOX_MAX_FILES = 40;        // so viele Bilder werden für das Programm vorgemerkt, solange es nicht läuft
const INBOX_MAX_BYTES = 50331648;  // … höchstens 48 MB zusammen
const INBOX_KEEP     = 2592000;    // vorgemerkte Bilder werden nach 30 Tagen verworfen
const REC_DIR        = 'aufnahmen'; // Ordner neben remote.php für die Aufnahmen aus dem Programm
const REC_EXTENSIONS = ['.wav', '.mp3', '.m4a', '.flac', '.ogg'];
const REC_MAX_BYTES  = 2147483648; // größte Aufnahme (2 GB)
const REPORT_KEEP     = 2592000;    // Problemmeldungen werden nach 30 Tagen gelöscht
const REPORT_MAX      = 200;        // … und es bleiben höchstens so viele
const UPLOAD_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'];

@ini_set('memory_limit', '256M');
@ini_set('display_errors', '0');
@set_time_limit(60);

const PAGE_HTML = <<<'LM_PAGE_HTML'
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=420, initial-scale=1, minimum-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="#1A1817">
<title>LiedManager – Fernsteuerung</title>
<meta name="application-name" content="LiedManager">
<meta name="apple-mobile-web-app-title" content="LiedManager">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<link rel="icon" type="image/png" sizes="32x32" href="__SELF__?asset=favicon">
<link rel="apple-touch-icon" sizes="180x180" href="__SELF__?asset=icon180">
<link rel="manifest" href="__SELF__?asset=manifest">
<link rel="stylesheet" href="__SELF__?asset=css">
</head>
<body>

<main id="login" class="screen">
  <section class="card login-card">
    <h1>LiedManager</h1>
    <p class="muted">Fernsteuerung – bitte mit der PIN anmelden, die du in der Datei remote.php festgelegt hast.</p>
    <input id="pin" type="password" autocomplete="current-password" placeholder="PIN" aria-label="PIN">
    <button id="loginBtn" class="primary" title="Anmelden">Anmelden</button>
    <p id="loginMsg" class="msg" role="alert"></p>
  </section>
</main>

<div id="app" class="screen" hidden>
  <header class="top">
    <div class="searchrow">
      <div class="field">
        <span class="field-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg></span>
        <input id="q" type="search" placeholder="Suche" autocomplete="off" aria-label="Lied suchen"
               title="Suche nach Liednummer (z. B. 12 oder p012), Titel oder Textstelle">
      </div>
      <button id="gongBtn" class="round" title="Gong abspielen" aria-label="Gong"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/></svg></button>
      <button id="moreBtn" class="round" title="Mehr: Datenbank-Abgleich, Version, Abmelden" aria-label="Mehr"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg></button>
    </div>
    <nav id="tabs" class="tabs" aria-label="Bereiche">
      <button class="tab on" data-tab="song" title="Lied, Audio, Aufnahme und Pausentimer">Lied</button>
      <button class="tab" data-tab="camera" title="Live-Kameras und ATEM"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8.5a2 2 0 0 1 2-2h2.4l1.4-2h6.4l1.4 2H19a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="12.8" r="3.4"/></svg><span>Kamera</span></button>
      <button class="tab" data-tab="images" title="Bilder auf dem Beamer zeigen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4.5" width="18" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.7"/><path d="M21 16.5l-5-5-8.5 8"/></svg><span>Bilder</span><span id="imgBadge" class="badge" hidden>0</span></button>
      <button id="escBtn" class="tab esc" title="Wie Esc im Programm: schließt zuerst Beamer-Bild, dann Kamera-Vollbild, sonst Audio und Suche">Esc</button>
    </nav>
  </header>
  <div class="status">
    <select id="deviceSel" class="chip" title="Welcher Computer bedient wird" aria-label="Computer" hidden></select>
    <span id="conn" class="chip" title="Verbindung zum Programm">verbunden</span>
    <span id="beamerChip" class="chip" title="Was gerade auf dem Beamer zu sehen ist">Beamer: leer</span>
  </div>

  <section id="tab-song" class="tabpage">
    <ul id="results" class="list" hidden></ul>

    <div id="songArea" class="stack">
      <div id="songHead" hidden>
        <button id="songTitle" class="songtitle" type="button" title="Klicken: Liednummer ins Suchfeld übernehmen"></button>
        <div class="beamerrow">
          <button id="showBtn" class="pill grow" title="Zeigt das Lied auf dem Beamer">Auf dem Beamer zeigen</button>
          <button id="closeBeamerBtn" class="round" title="Schließt alles, was auf dem Beamer zu sehen ist" aria-label="Beamer schließen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
        </div>
      </div>

      <div id="audio" hidden>
        <div id="audioSelect" class="selectrow">
          <button id="a1" class="pill grow" hidden type="button">Piano</button>
          <button id="a2" class="pill grow" hidden type="button">GL3</button>
          <span id="noAudio" class="noaudio" hidden>Keine Audiodatei vorhanden</span>
        </div>
        <div id="player" class="panel" hidden>
          <button id="playBtn" class="round" title="Wiedergabe / Pause" aria-label="Wiedergabe oder Pause"><span class="i-play"><svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><path d="M7 4.5v15l13-7.5z"/></svg></span><span class="i-pause"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4.5" height="14" rx="1"/><rect x="13.5" y="5" width="4.5" height="14" rx="1"/></svg></span></button>
          <div class="grow">
            <div id="trackName" class="track"></div>
            <input id="seek" type="range" min="0" max="100" step="0.1" value="0" title="Vor- und Zurückspulen" aria-label="Position">
          </div>
          <button id="stopBtn" class="icon" title="Wiedergabe beenden" aria-label="Wiedergabe beenden"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2.5"/></svg></button>
        </div>
      </div>

      <div id="recPanel" class="panel">
        <button id="recBtn" class="round" title="Aufnahme starten" aria-label="Aufnahme"><span id="recDot" class="recdot"></span></button>
        <div class="grow recmid">
          <input id="preacher" class="small" type="text" maxlength="80" placeholder="Prediger" aria-label="Prediger"
                 title="Name des Predigers – steht im Dateinamen der Aufnahme (Datum Prediger)">
          <span id="recTime" class="rectime" title="Dauer der laufenden Aufnahme">00:00</span>
        </div>
        <button id="saveBtn" class="icon" title="Aufnahme speichern" aria-label="Aufnahme speichern" disabled><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></button>
      </div>
    </div>

    <section id="pausePanel" class="pause">
      <div class="pauseHead">
        <button id="pauseTitle" class="ptitle" type="button" title="Klicken: Ansagen ein- oder ausklappen">Pausentimer</button>
        <input id="endTime" class="timeedit" type="time" aria-label="Endzeit der Pause" title="Endzeit der Pause (Uhrzeit ändern)">
        <button id="pauseBtn" class="round" title="Pausentimer starten" aria-label="Pausentimer starten oder beenden"><span class="i-play"><svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><path d="M7 4.5v15l13-7.5z"/></svg></span><span class="i-pause"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2.5"/></svg></span></button>
        <button id="pauseChevron" class="chev" type="button" title="Ansagen ein- oder ausklappen" aria-label="Ansagen ein- oder ausklappen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg></button>
      </div>
      <textarea id="lines" rows="11" cols="50" wrap="off" spellcheck="false" hidden placeholder="Ansagen" aria-label="Ansagen"
                title="Ansagen für die Pausenfolie – eine Zeile pro Ansage"></textarea>
    </section>
  </section>

  <section id="tab-camera" class="tabpage" hidden>
    <div id="cams" class="card">
      <div class="caption">Kameras</div>
      <div id="camList"></div>
      <div class="row"><button id="camCloseBtn" class="pill" title="Alle Kamera-Vollbilder schließen">Kamera-Vollbild schließen</button></div>
    </div>
    <div id="atemCard" class="card" hidden>
      <div class="caption">ATEM-Mischer schalten</div>
      <div class="row">
        <button class="pill" data-atem="presentation" title="Auf den Präsentationskanal schalten">Präsentation</button>
        <button class="pill" data-atem="camera" title="Auf den Kamerakanal schalten">Kamera</button>
        <button class="pill" data-atem="default" title="Auf den Standardkanal schalten">Standard</button>
      </div>
    </div>
    <div id="mixerCard" class="card" hidden>
      <div class="caption">Mischpult (X AIR) <span id="mixerState" class="chip" title="Verbindung zum Mischpult">…</span></div>
      <p id="mixerOff" class="muted" hidden>Das Mischpult ist aus. Einschalten: LiedManager → Einstellungen → Audio → „Behringer X AIR“ (IP-Adresse eintragen).</p>
      <div id="mixerList"></div>
      <button id="mixerMuteAll" type="button" class="pill" title="Alle acht Kanäle stummschalten">Alles stumm</button>
    </div>
  </section>

  <section id="tab-images" class="tabpage" hidden>
    <div class="card">
      <div class="caption">Beamer-Galerie</div>
      <div id="galleryInfo" class="muted">Keine Bilder</div>
      <div class="row">
        <button id="prevBtn" class="pill" title="Vorheriges Bild"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg><span>Zurück</span></button>
        <button id="nextBtn" class="pill" title="Nächstes Bild"><span>Weiter</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg></button>
        <button id="galleryCloseBtn" class="pill" title="Galerie auf dem Beamer schließen">Schließen</button>
      </div>
    </div>
    <div class="card">
      <div class="caption">Abgelegte Bilder – antippen zeigt auf dem Beamer</div>
      <div id="thumbs" class="thumbs"></div>
      <p id="noImages" class="muted">Noch keine Bilder. Lade welche vom Handy hoch.</p>
      <p id="queueNote" class="muted" hidden></p>
      <div class="row">
        <label class="pill filebtn" title="Bilder von diesem Gerät hinzufügen">Bilder hochladen
          <input id="upload" type="file" accept="image/*" multiple hidden>
        </label>
        <button id="clearBtn" class="pill" title="Alle abgelegten Bilder entfernen">Alle entfernen</button>
      </div>
      <div class="row" id="queueRow" hidden>
        <button id="queueClearBtn" class="pill" title="Vorgemerkte Bilder auf dem Server verwerfen">Vorgemerkte verwerfen</button>
      </div>
    </div>
  </section>

  <section id="tab-more" class="tabpage" hidden>
    <div id="reportsCard" class="card" hidden>
      <div class="caption">Gemeldete Probleme</div>
      <div id="reportsList"></div>
      <div class="row"><button id="reportsClearBtn" class="pill" title="Alle gemeldeten Probleme löschen">Liste leeren</button></div>
    </div>
    <div class="card">
      <div class="caption">Datenbank-Abgleich</div>
      <p id="syncStatus" class="muted">–</p>
      <div class="row"><button id="syncBtn" class="pill" title="Änderungen mit den anderen Geräten abgleichen">Jetzt abgleichen</button></div>
    </div>
    <div class="card">
      <div class="caption">Programm</div>
      <p id="versionLabel" class="muted"></p>
      <div class="row"><button id="logoutBtn" class="pill" title="Auf diesem Gerät abmelden">Abmelden</button></div>
    </div>
  </section>
</div>

<div id="toast" class="toast" role="status" hidden></div>
<script src="__SELF__?asset=js"></script>
</body>
</html>
LM_PAGE_HTML;

const PAGE_CSS = <<<'LM_PAGE_CSS'
:root {
  --bg: #1A1817; --surface: #232120; --surface-low: #1E1B19;
  --hover-top: #2A2725; --hover-bottom: #221F1D; --pressed: #171413;
  --border: #312D2A; --track: #34302C;
  --text: #F2ECE5; --text-2: #B3AAA2; --label: #D9D1C9; --muted: #857D75;
  --accent: #C08A53; --accent-light: #D9A46A; --accent-glow: #EBC08A; --accent-deep: #8F6236;
  --accent-border: #7A5838; --accent-tint: #2E251C; --pill-text: #E2C9A6;
  --rec: #F0654A; --rec-bg: #2B1F18; --rec-time: #E8BE88; --track-name: #F2D9B8;
  --radius: 12px; --panel-radius: 16px; --fs: 14px; --fs-small: 12px; --btn: 44px;
  --serif: Fraunces, Georgia, "Times New Roman", serif; --body: Arial, "Helvetica Neue", Helvetica, sans-serif;
  --panel: linear-gradient(180deg, var(--surface), var(--surface-low));
  --panel-hover: linear-gradient(180deg, var(--hover-top), var(--hover-bottom));
}
* { box-sizing: border-box; }
html { background: var(--bg); overflow-x: hidden; overscroll-behavior: none; touch-action: pan-y; }
body {
  margin: 0; background: var(--bg); color: var(--text); font-family: var(--body); font-size: var(--fs);
  padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
  -webkit-text-size-adjust: 100%; overflow-x: hidden; overscroll-behavior: none; touch-action: pan-y;
  -webkit-user-select: none; user-select: none;
}
input, textarea { -webkit-user-select: text; user-select: text; }
[hidden] { display: none !important; }
svg { width: 1em; height: 1em; display: block; flex: none; }
.screen { width: 420px; margin: 0 auto; padding: 16px 24px 40px; }
h1 { font-family: var(--serif); font-weight: 600; font-size: 24px; margin: 0; letter-spacing: .2px; }
.muted { color: var(--muted); font-size: var(--fs-small); margin: 6px 0; }
.caption { font-size: var(--fs-small); font-weight: 500; color: var(--text-2); margin: 0 0 8px; display: block; }
.msg { min-height: 1.2em; color: var(--rec); font-size: var(--fs-small); margin: 8px 0 0; }
.grow { flex: 1 1 0; min-width: 0; }

.card, .panel {
  background: var(--panel); border: 1px solid var(--border); border-radius: var(--panel-radius);
}
.card { padding: 16px; margin: 0 0 12px; }
.panel { display: flex; align-items: center; gap: 12px; padding: 8px; min-height: 64px; }
.login-card { margin-top: 12vh; display: grid; gap: 12px; }
.login-card h1 { text-align: center; }

input[type=text], input[type=password], input[type=search], input[type=time], textarea {
  width: 100%; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  color: var(--text); font: inherit; padding: 0 12px; height: var(--btn); margin: 0; outline: none;
}
.login-card input { margin: 0; }
input[type=search] { -webkit-appearance: none; appearance: none; padding-left: 40px; }
input[type=search]::-webkit-search-cancel-button { -webkit-appearance: none; }
input.small { height: 32px; padding: 0 10px; background: var(--bg); }
textarea {
  /* genau 50 Zeichen breit und 11 Zeilen hoch (Schrift mit fester Breite), ohne Bildlauf */
  width: calc(50ch + 26px); height: 238px; padding: 8px 12px; resize: none; overflow: hidden; white-space: pre; overflow-wrap: normal;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, "Courier New", monospace; font-size: 11px; line-height: 20px;
  color: var(--text-2); letter-spacing: 0;
}
input[type=time] { color-scheme: dark; }
input::placeholder, textarea::placeholder { color: var(--muted); }
input:hover, textarea:hover { border-color: var(--accent-border); }
input:focus, textarea:focus { border-color: var(--accent); }
::selection { background: var(--accent-deep); color: var(--text); }

button { font: inherit; cursor: pointer; -webkit-tap-highlight-color: transparent; }
button:disabled { color: var(--muted); border-color: var(--border) !important; cursor: default; }
.row { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 12px 0 0; }
.row:first-child { margin-top: 0; }

.pill {
  color: var(--pill-text); background: var(--panel); border: 1px solid var(--accent-border); border-radius: calc(var(--btn) / 2);
  height: var(--btn); padding: 0 18px; font-weight: 500; display: inline-flex; align-items: center;
  justify-content: center; gap: 8px; flex: none;
}
.pill.grow { flex: 1 1 0; }
.pill:hover { border-color: var(--accent); color: var(--text); background: var(--panel-hover); }
.pill:active { border-color: var(--accent-light); background: var(--pressed); }
.pill.on { border-color: var(--accent); color: var(--text); background: var(--accent-tint); }
.pill svg { width: 16px; height: 16px; }
.pill:focus-visible, .primary:focus-visible, .round:focus-visible, .tab:focus-visible, .icon:focus-visible,
.songtitle:focus-visible, .ptitle:focus-visible, .chev:focus-visible { outline: 2px solid var(--accent-light); outline-offset: 2px; }
.primary {
  color: var(--bg); font-weight: 600; padding: 0 24px; height: var(--btn); border-radius: var(--radius);
  background: linear-gradient(180deg, var(--accent-light), var(--accent)); border: 1px solid var(--accent-light);
}
.primary:hover { background: linear-gradient(180deg, var(--accent-glow), var(--accent-light)); border-color: var(--accent-glow); }
.primary:active { background: var(--accent); }
.round {
  flex: none; width: var(--btn); height: var(--btn); border-radius: calc(var(--btn) / 2); padding: 0;
  display: inline-flex; align-items: center; justify-content: center; color: var(--accent-light); font-size: 18px;
  background: var(--panel); border: 1px solid var(--accent-border);
}
.round:hover { border-color: var(--accent); background: var(--panel-hover); }
.round:active { border-color: var(--accent-light); background: var(--pressed); }
.round.on { border-color: var(--accent); background: var(--accent-tint); }
.icon {
  flex: none; width: 36px; height: 36px; padding: 0; border: 0; background: transparent; color: var(--accent-light);
  border-radius: 18px; display: inline-flex; align-items: center; justify-content: center; font-size: 16px;
}
.icon:hover { background: var(--accent-tint); }
.icon:disabled { opacity: .35; background: transparent; }
.filebtn { cursor: pointer; }

/* Kopf: Suche, Reiter */
.top { position: sticky; top: 0; z-index: 5; background: var(--bg); padding: 0 0 10px; }
.searchrow { display: flex; gap: 12px; align-items: center; }
.field { position: relative; flex: 1 1 0; min-width: 0; }
.field-icon { position: absolute; left: 13px; top: 50%; transform: translateY(-50%); color: var(--muted); font-size: 17px; pointer-events: none; display: flex; }
.tabs { display: flex; gap: 8px; margin-top: 12px; overflow-x: auto; scrollbar-width: none; }
.tabs::-webkit-scrollbar { display: none; }
.tab {
  flex: 0 0 auto; position: relative; display: inline-flex; align-items: center; gap: 7px; height: 36px; padding: 0 14px;
  color: var(--pill-text); background: var(--panel); border: 1px solid var(--accent-border); border-radius: 18px;
  font-size: 13px; font-weight: 500;
}
.tab svg { width: 16px; height: 16px; color: var(--accent-light); }
.tab:hover { border-color: var(--accent); color: var(--text); background: var(--panel-hover); }
.tab.on { color: var(--text); border-color: var(--accent); background: var(--accent-tint); }
.tab.esc { margin-left: auto; padding: 0 14px; }
.badge {
  min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; background: var(--accent); color: #1A1210;
  font-size: 10px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center;
}
.status { display: flex; gap: 8px; align-items: center; margin: 0 0 12px; }
.chip {
  font-size: var(--fs-small); color: var(--text-2); border: 1px solid var(--border); border-radius: 14px;
  padding: 3px 10px; background: var(--surface);
}
select.chip { appearance: none; -webkit-appearance: none; cursor: pointer; font-family: inherit; }
.chip.bad { color: var(--rec); border-color: var(--rec); }
.chip.live { color: var(--accent-light); border-color: var(--accent-border); }

/* Lied */
.stack > * + * { margin-top: 12px; }
.songtitle {
  display: block; width: 100%; text-align: left; padding: 0; margin: 0 0 12px; border: 0; background: none; color: var(--text);
  font-family: var(--serif); font-weight: 700; font-size: 17px; line-height: 24px; height: 24px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.songtitle:hover { color: var(--accent-glow); }
.beamerrow, .selectrow { display: flex; gap: 12px; align-items: center; }
.noaudio { flex: 1; text-align: center; color: var(--muted); font-size: var(--fs); min-height: var(--btn); line-height: var(--btn); }
.list { list-style: none; margin: 0 0 12px; padding: 4px; display: grid; gap: 2px; background: var(--surface);
  border: 1px solid var(--accent); border-radius: var(--radius); }
.list button {
  width: 100%; text-align: left; color: var(--text); background: transparent; border: 1px solid transparent;
  border-radius: 8px; padding: 9px 10px;
}
.list button:hover { background: rgba(255,255,255,.04); border-color: var(--border); }
.list button:active, .list button.on { background: var(--accent-tint); color: var(--accent-light); border-color: var(--accent-border); }
.list .muted { padding: 8px 10px; margin: 0; }
.searching #songArea { display: none; }
.track { color: var(--track-name); font-size: var(--fs-small); font-weight: 500; margin: 0 0 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
input[type=range] {
  -webkit-appearance: none; appearance: none; display: block; width: 100%; height: 20px; margin: 0; padding: 0; border: 0;
  background: transparent; cursor: pointer; --p: 0%;
}
input[type=range]::-webkit-slider-runnable-track {
  height: 4px; border-radius: 2px; background: linear-gradient(90deg, var(--accent) var(--p), var(--track) var(--p));
}
input[type=range]::-moz-range-track { height: 4px; border-radius: 2px; background: var(--track); }
input[type=range]::-moz-range-progress { height: 4px; border-radius: 2px; background: var(--accent); }
input[type=range]::-webkit-slider-thumb {
  -webkit-appearance: none; width: 12px; height: 12px; margin-top: -4px; border-radius: 6px; border: 0;
  background: var(--accent-light); box-shadow: 0 0 6px rgba(217,164,106,.55);
}
input[type=range]::-moz-range-thumb { width: 12px; height: 12px; border-radius: 6px; border: 0; background: var(--accent-light); }

#mixerMuteAll { margin-top: 14px; width: 100%; justify-content: center; border-color: #C0504D; color: #F0B8B6; }
#reportsList details { margin: 8px 0; }
#reportsList pre { white-space: pre-wrap; word-break: break-word; font-size: 12px; }
.mixrow { display: grid; grid-template-columns: 44% 1fr 52px; gap: 10px; align-items: center; margin: 10px 0 0; }
.mixrow .pill { justify-content: flex-start; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mixrow .pill.muted { border-color: #C0504D; color: #F0B8B6; background: rgba(192,80,77,.16); }
.mixdb { text-align: right; font-size: var(--fs-small); color: var(--muted); font-variant-numeric: tabular-nums; }

/* Aufnahme */
.recmid { display: flex; gap: 8px; align-items: center; }
.recmid .small { flex: 1 1 0; }
.rectime { font-variant-numeric: tabular-nums; color: var(--muted); font-size: var(--fs); font-weight: 600; min-width: 44px; text-align: right; }
.rectime.run { color: var(--rec-time); }
.recdot {
  display: block; width: 14px; height: 14px; border-radius: 7px;
  background: radial-gradient(circle at 35% 30%, var(--accent-light), var(--accent-deep));
}
#recBtn.paused .recdot { background: radial-gradient(circle at 35% 30%, var(--accent-glow), var(--accent)); box-shadow: 0 0 9px rgba(192,138,83,.45); }
#recBtn.run { background: var(--rec-bg); border-color: var(--accent); }
#recBtn.run:hover { border-color: var(--rec); }
#recBtn.run .recdot {
  background: radial-gradient(circle at 35% 30%, #FF9078, #E5503A); box-shadow: 0 0 12px rgba(240,101,74,.7);
  animation: pulse 1.6s ease-in-out infinite;
}
@keyframes pulse { 0%, 100% { opacity: .65; } 50% { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { #recBtn.run .recdot { animation: none; } }

/* Pausentimer */
.pause { border-top: 1px solid var(--border); margin-top: 12px; }
.pauseHead { display: flex; align-items: center; gap: 12px; min-height: 64px; }
.ptitle {
  flex: 1 1 0; min-width: 0; text-align: left; padding: 0; border: 0; background: none; color: var(--label);
  font-size: var(--fs); font-weight: 500; height: 64px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ptitle.run { color: var(--rec-time); font-variant-numeric: tabular-nums; }
input.timeedit { width: 84px; flex: none; text-align: center; padding: 0 8px; font-weight: 600; color: var(--accent); font-variant-numeric: tabular-nums; }
.chev { flex: none; border: 0; background: none; color: var(--muted); padding: 6px; font-size: 16px; display: flex; }
.chev:hover { color: var(--text); }
.pause textarea { margin: 0 0 4px; }

/* Bilder, Kamera */
.thumbs { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 10px; }
.thumb {
  position: relative; padding: 0; overflow: hidden; border-radius: var(--radius); background: var(--surface);
  border: 2px solid var(--border); aspect-ratio: 16 / 10;
}
.thumb:hover { border-color: var(--accent-border); }
.thumb.on { border-color: var(--accent); background: var(--accent-tint); }
.thumb img { width: 100%; height: 100%; object-fit: contain; display: block; }
.thumb .no { position: absolute; left: 6px; bottom: 5px; font-size: 11px; color: var(--text); background: rgba(26,24,23,.78); border-radius: 8px; padding: 1px 7px; }
.thumb .del {
  position: absolute; right: 5px; top: 5px; width: 26px; height: 26px; border-radius: 13px; line-height: 22px;
  color: var(--text-2); background: rgba(26,24,23,.82); border: 1px solid var(--accent-border); padding: 0;
}
.thumb .del:hover { color: var(--text); border-color: var(--accent); }
.cam { display: flex; align-items: center; gap: 12px; justify-content: space-between; padding: 8px 0; }
.cam + .cam { border-top: 1px solid var(--border); }
.cam .name { font-weight: 500; }
.toast {
  position: fixed; left: 50%; bottom: calc(18px + env(safe-area-inset-bottom)); transform: translateX(-50%);
  max-width: min(92vw, 520px); background: var(--surface); color: var(--text); border: 1px solid var(--accent-border);
  border-radius: var(--radius); padding: 10px 16px; font-size: var(--fs-small); z-index: 20;
}
.toast.bad { border-color: var(--rec); }
#playBtn .i-pause, #pauseBtn .i-pause { display: none; }
#playBtn.playing .i-play, #pauseBtn.running .i-play { display: none; }
#playBtn.playing .i-pause, #pauseBtn.running .i-pause { display: flex; }
#playBtn span, #pauseBtn span { display: flex; }
#player { margin-top: 12px; }
.chev svg { transition: transform .15s; }
.chev.open svg { transform: rotate(180deg); }
.searching #pausePanel { display: none; }
LM_PAGE_CSS;

const PAGE_JS = <<<'LM_PAGE_JS'
(function () {
  'use strict';
  var TOKEN_KEY = 'lm_token';
  var DEVICE_KEY = 'lm_device';
  var device = '';
  try { device = localStorage.getItem(DEVICE_KEY) || ''; } catch (e) {}
  var RELAY = '__SELF__';      // leer = Programm direkt; sonst Name des PHP-Skripts auf der Website
  var token = '';
  try { token = localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { token = ''; }
  var state = null;
  var thumbKeys = '';
  var thumbUrls = [];
  var searchTimer = null;
  var searchSeq = 0;
  var pollTimer = null;
  var seeking = false;
  var toastTimer = null;
  var beamerNames = { none: 'leer', song: 'Lied', gallery: 'Bilder', camera: 'Kamera', pause: 'Pausenfolie' };

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }
  function mmss(sec) {
    sec = Math.max(0, Math.round(sec));
    var m = Math.floor(sec / 60), s = sec % 60;
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }
  function toast(message, bad) {
    var box = $('toast');
    box.textContent = message;
    box.className = 'toast' + (bad ? ' bad' : '');
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { box.hidden = true; }, bad ? 4500 : 2200);
  }

  function apiUrl(path) {
    if (!RELAY) { return path; }
    var rest = path.replace(/^\/api\//, '');
    var cut = rest.indexOf('?');
    var name = cut < 0 ? rest : rest.slice(0, cut);
    var extra = cut < 0 ? '' : '&' + rest.slice(cut + 1);
    return RELAY + '?api=' + name + extra;
  }

  function request(method, path, body, raw) {
    var headers = {};
    if (token) {
      if (RELAY) { headers['X-LM-Token'] = token; } else { headers['Authorization'] = 'Bearer ' + token; }
    }
    if (device) { headers['X-LM-Device'] = device; }
    var init = { method: method, headers: headers, cache: 'no-store' };
    if (raw) {
      init.body = raw;
    } else if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    return fetch(apiUrl(path), init).then(function (res) {
      if (res.status === 401 && path !== '/api/login') {
        showLogin();
        throw new Error('Bitte anmelden.');
      }
      if (res.ok && path.indexOf('/api/thumb/') === 0) { return res.blob(); }
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var err = new Error(data.error || ('Fehler ' + res.status));
          err.status = res.status;
          throw err;
        }
        return data;
      });
    });
  }

  function act(name, args, quiet) {
    return request('POST', '/api/' + name, args || {}).then(function (data) {
      refresh();
      return data;
    }).catch(function (err) {
      if (!quiet) { toast(err.message, true); }
      throw err;
    });
  }
  function actQuiet(name, args) { act(name, args).catch(function () {}); }

  /* ---------------- Anmeldung ---------------- */
  function showLogin() {
    token = '';
    try { localStorage.removeItem(TOKEN_KEY); } catch (e) {}
    clearInterval(pollTimer);
    pollTimer = null;
    $('app').hidden = true;
    $('login').hidden = false;
    $('pin').value = '';
    $('pin').focus();
  }
  var deviceSig = '';
  function refreshDevices() {
    return request('GET', '/api/devices').then(function (r) {
      var list = r.devices || [];
      var names = list.map(function (d) { return d.name; });
      if (!device || names.indexOf(device) < 0) { device = r.current || names[0] || ''; }
      var sel = $('deviceSel');
      var sig = device + '|' + list.map(function (d) { return d.name + (d.online ? '+' : '-'); }).join(',');
      if (sig === deviceSig) { return; }
      deviceSig = sig;
      sel.textContent = '';
      list.forEach(function (d) {
        var opt = el('option', '', d.name + (d.online ? '' : ' (aus)'));
        opt.value = d.name;
        if (d.name === device) { opt.selected = true; }
        sel.appendChild(opt);
      });
      sel.hidden = list.length < 2;
    }).catch(function () {});
  }
  on('deviceSel', 'change', function () {
    device = $('deviceSel').value;
    try { localStorage.setItem(DEVICE_KEY, device); } catch (e) {}
    location.reload();
  });
  function showApp() {
    $('login').hidden = true;
    $('app').hidden = false;
    refreshDevices();
    setInterval(function () { if (!document.hidden) { refreshDevices(); } }, 15000);   // neue oder ausgeschaltete Computer nachführen
    refresh();
    if (!pollTimer) { pollTimer = setInterval(function () { if (!document.hidden) { refresh(); } }, 1000); }
  }
  function login() {
    var pin = $('pin').value;
    $('loginMsg').textContent = '';
    $('loginBtn').disabled = true;
    request('POST', '/api/login', { pin: pin }).then(function (data) {
      token = data.token;
      try { localStorage.setItem(TOKEN_KEY, token); } catch (e) {}
      showApp();
    }).catch(function (err) {
      $('loginMsg').textContent = err.message;
    }).then(function () { $('loginBtn').disabled = false; });
  }

  /* ---------------- Zustand holen und anzeigen ---------------- */
  var reportsLoaded = false;
  function refresh() {
    return request('GET', '/api/state').then(function (s) {
      state = s;
      setConn(true);
      showQueue(0);
      render(s);
      if (!reportsLoaded) { reportsLoaded = true; refreshReports(); }
    }).catch(function (err) {
      var offline = err.status === undefined || err.status === 503 || err.status === 504;
      if (offline && err.message !== 'Bitte anmelden.') { setConn(false); refreshQueue(); }
    });
  }
  /* Bilder, die hochgeladen wurden, während das Programm nicht lief, warten auf dem Server */
  function showQueue(n) {
    $('queueNote').hidden = !n;
    $('queueRow').hidden = !n;
    if (n) {
      $('queueNote').textContent = n + (n === 1 ? ' Bild ist' : ' Bilder sind') +
        ' vorgemerkt und werden beim nächsten Start des Programms übernommen.';
    }
  }
  function renderReports(list) {
    var box = $('reportsList');
    $('reportsCard').hidden = !(list && list.length);
    box.textContent = '';
    (list || []).forEach(function (r) {
      var item = el('details', '');
      var head = el('summary', '', new Date(r.created * 1000).toLocaleString('de-DE') + ' · ' + r.title +
        (Number(r.n) > 1 ? ' (' + r.n + '×)' : ''));
      item.appendChild(head);
      item.appendChild(el('pre', 'muted', 'Version ' + r.version + ' · ' + r.system + '\n' + (r.detail || '')));
      box.appendChild(item);
    });
  }
  function refreshReports() {
    return request('GET', '/api/reports').then(function (r) { renderReports(r.reports); }).catch(function () {});
  }
  $('reportsClearBtn').addEventListener('click', function () {
    request('POST', '/api/reports_clear', {}).then(function () { renderReports([]); })
      .catch(function (err) { toast(err.message, true); });
  });
  function refreshQueue() {
    return request('GET', '/api/inbox').then(function (r) { showQueue(r.pending || 0); }).catch(function () {});
  }
  function setConn(ok) {
    var chip = $('conn');
    chip.textContent = ok ? 'verbunden' : 'getrennt';
    chip.className = 'chip' + (ok ? '' : ' bad');
  }

  function render(s) {
    var beamer = $('beamerChip');
    beamer.textContent = 'Beamer: ' + (beamerNames[s.beamer] || s.beamer);
    beamer.className = 'chip' + (s.beamer !== 'none' ? ' live' : '');
    renderSong(s);
    renderRecording(s.recording);
    renderImages(s);
    renderCameras(s);
    renderPause(s.pause);
    $('syncStatus').textContent = s.sync.enabled ? s.sync.status : 'Aus – im Programm unter Einstellungen → Lieder einrichten.';
    $('syncBtn').disabled = !s.sync.enabled;
    $('versionLabel').textContent = 'LiedManager ' + s.version;
  }

  function renderSong(s) {
    var song = s.song;
    $('songHead').hidden = !song;
    $('audio').hidden = !song;
    if (!song) { return; }
    $('songTitle').textContent = song.titel ? song.nummer + ' – ' + song.titel : String(song.nummer);
    var any = false;
    [0, 1].forEach(function (i) {
      var btn = $('a' + (i + 1));
      var info = song.audio[i];
      btn.hidden = !info || !info.available;
      if (info) { btn.textContent = info.name; }
      any = any || (!!info && info.available);
      btn.classList.toggle('on', s.audio.active && s.audio.slot === i);
    });
    $('noAudio').hidden = any;
    $('player').hidden = !s.audio.active;
    if (s.audio.active) {
      $('playBtn').classList.toggle('playing', s.audio.playing);
      $('trackName').textContent = s.audio.track || '';
      if (!seeking) { setSeek(Math.round(s.audio.progress * 1000) / 10); }
    }
  }
  function setSeek(percent) {
    $('seek').value = String(percent);
    $('seek').style.setProperty('--p', percent + '%');
  }

  function renderRecording(rec) {
    var running = rec.state === 'rec';
    var btn = $('recBtn');
    btn.classList.toggle('run', running);
    btn.classList.toggle('paused', rec.state === 'paused');
    btn.title = rec.state === 'idle' ? 'Aufnahme starten' : (running ? 'Aufnahme pausieren' : 'Aufnahme fortsetzen');
    $('saveBtn').disabled = rec.state === 'idle';
    $('recTime').textContent = mmss(rec.seconds);
    $('recTime').classList.toggle('run', running);
  }

  function renderImages(s) {
    var items = s.images.items;
    var keys = items.map(function (it) { return it.key; }).join(',');
    $('noImages').hidden = items.length > 0;
    $('imgBadge').hidden = items.length === 0;
    $('imgBadge').textContent = String(items.length);
    $('clearBtn').disabled = items.length === 0;
    var g = s.gallery;
    $('galleryInfo').textContent = g ? ('Bild ' + (g.index + 1) + ' von ' + g.count + ' auf dem Beamer')
      : (items.length ? items.length + (items.length === 1 ? ' Bild' : ' Bilder') + ' abgelegt – Galerie ist nicht offen' : 'Keine Bilder');
    $('prevBtn').disabled = !g || g.index <= 0;
    $('nextBtn').disabled = !g || g.index >= g.count - 1;
    $('galleryCloseBtn').disabled = !g;
    if (keys !== thumbKeys) {
      thumbKeys = keys;
      thumbUrls.forEach(function (u) { URL.revokeObjectURL(u); });
      thumbUrls = [];
      var box = $('thumbs');
      box.textContent = '';
      items.forEach(function (it, i) {
        var tile = el('button', 'thumb');
        tile.type = 'button';
        tile.title = it.name + ' – auf dem Beamer zeigen';
        tile.dataset.index = String(i);
        var img = el('img');
        img.alt = it.name;
        tile.appendChild(img);
        tile.appendChild(el('span', 'no', String(i + 1)));
        var del = el('button', 'del', '×');
        del.type = 'button';
        del.title = 'Dieses Bild entfernen';
        del.dataset.del = String(i);
        tile.appendChild(del);
        box.appendChild(tile);
        request('GET', '/api/thumb/' + i).then(function (blob) {
          var url = URL.createObjectURL(blob);
          thumbUrls.push(url);
          img.src = url;
        }).catch(function () {});
      });
    }
    var current = g ? g.index : -1;
    Array.prototype.forEach.call($('thumbs').children, function (tile, i) { tile.classList.toggle('on', i === current); });
  }

  function renderCameras(s) {
    var list = $('camList');
    var sig = JSON.stringify(s.cameras);
    if (list.dataset.sig !== sig) {
      list.dataset.sig = sig;
      list.textContent = '';
      s.cameras.forEach(function (cam, i) {
        var row = el('div', 'cam');
        var left = el('div');
        left.appendChild(el('div', 'name', cam.name));
        left.appendChild(el('div', 'muted', cam.live ? 'Bild läuft' : 'Keine Kamera'));
        row.appendChild(left);
        var btn = el('button', 'pill' + (cam.fullscreen ? ' on' : ''), cam.fullscreen ? 'Vollbild schließen' : 'Vollbild auf Beamer');
        btn.type = 'button';
        btn.disabled = !cam.live && !cam.fullscreen;
        btn.title = 'Kamerabild im Vollbild auf dem Beamer zeigen oder wieder schließen';
        btn.dataset.cam = String(i);
        row.appendChild(btn);
        list.appendChild(row);
      });
    }
    $('camCloseBtn').disabled = !s.cameras.some(function (c) { return c.fullscreen; });
    $('atemCard').hidden = !s.atem.enabled;
    renderMixer(s.mixer);
    if (s.atem.channels) {
      var names = { presentation: 'Präsentation', camera: 'Kamera', default: 'Standard' };
      Array.prototype.forEach.call(document.querySelectorAll('button[data-atem]'), function (b) {
        var no = s.atem.channels[b.dataset.atem];
        b.textContent = names[b.dataset.atem] + (no ? ' (Eingang ' + no + ')' : '');
      });
    }
  }

  /* ---------------- Mischpult (X AIR) ---------------- */
  var mixDrag = {};                       // Kanal -> Zeitpunkt, bis zu dem der Regler nicht überschrieben wird
  var mixMute = {};
  function faderDb(level) {
    if (level <= 0) { return '−∞'; }
    var db = level >= 0.5 ? level * 40 - 30 : level >= 0.25 ? level * 80 - 50 : level >= 0.0625 ? level * 160 - 70 : level * 480 - 90;
    return (db > 0 ? '+' : db < 0 ? '−' : '') + Math.abs(db).toFixed(1);
  }
  function renderMixer(mx) {
    var card = $('mixerCard');
    card.hidden = !mx;
    if (card.hidden) { return; }
    var chip = $('mixerState');
    var off = !mx.enabled;
    $('mixerOff').hidden = !off;
    $('mixerList').hidden = off;
    $('mixerMuteAll').hidden = off;
    chip.textContent = off ? 'aus' : mx.connected ? 'verbunden' : 'nicht erreichbar';
    if (off) { return; }
    var list = $('mixerList');
    var channels = mx.channels || [];
    if (list.children.length !== channels.length) {
      list.textContent = '';
      channels.forEach(function (ch) {
        var row = el('div', 'mixrow');
        row.dataset.ch = String(ch.n);
        var mute = el('button', 'pill', '');
        mute.type = 'button';
        mute.dataset.mute = String(ch.n);
        mute.title = 'Kanal stummschalten / wieder einschalten';
        var fader = el('input', '');
        fader.type = 'range'; fader.min = '0'; fader.max = '1'; fader.step = '0.005'; fader.value = '0';
        fader.dataset.fader = String(ch.n);
        fader.title = 'Lauter / leiser';
        fader.setAttribute('aria-label', 'Lautstärke Kanal ' + ch.n);
        var db = el('span', 'mixdb', '');
        row.appendChild(mute); row.appendChild(fader); row.appendChild(db);
        list.appendChild(row);
      });
    }
    channels.forEach(function (ch, i) {
      var row = list.children[i];
      var mute = row.children[0], fader = row.children[1], db = row.children[2];
      mixMute[ch.n] = !!ch.mute;
      mute.textContent = ch.n + (ch.name ? ' ' + ch.name : '');
      mute.classList.toggle('muted', !!ch.mute);
      if (ch.level !== null && ch.level !== undefined && !(mixDrag[ch.n] > Date.now())) {
        fader.value = String(ch.level);
        fader.style.setProperty('--p', (ch.level * 100) + '%');
        db.textContent = faderDb(ch.level);
      }
    });
  }
  function bindMixer() {
    var list = $('mixerList');
    list.addEventListener('input', function (e) {
      var f = e.target.closest('input[data-fader]');
      if (!f) { return; }
      mixDrag[f.dataset.fader] = Date.now() + 2500;
      f.style.setProperty('--p', (Number(f.value) * 100) + '%');
      f.parentNode.children[2].textContent = faderDb(Number(f.value));
    });
    list.addEventListener('change', function (e) {
      var f = e.target.closest('input[data-fader]');
      if (!f) { return; }
      mixDrag[f.dataset.fader] = Date.now() + 1500;
      actQuiet('mixer_level', { channel: Number(f.dataset.fader), level: Number(f.value) });
    });
    list.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-mute]');
      if (!b) { return; }
      var n = Number(b.dataset.mute);
      var next = !mixMute[n];
      mixMute[n] = next;
      b.classList.toggle('muted', next);
      actQuiet('mixer_mute', { channel: n, mute: next });
    });
  }
  bindMixer();
  $('mixerMuteAll').addEventListener('click', function () {
    Array.prototype.forEach.call(document.querySelectorAll('#mixerList button[data-mute]'), function (b) {
      mixMute[Number(b.dataset.mute)] = true; b.classList.add('muted');
    });
    actQuiet('mixer_mute_all', {});
  });

  var pauseOpen = false;
  var maxLines = 11, maxChars = 50;
  function clampLines() {
    var box = $('lines');
    var lines = box.value.split('\n').slice(0, maxLines).map(function (l) { return l.slice(0, maxChars); });
    var text = lines.join('\n');
    if (text !== box.value) { box.value = text; }
  }
  function setPauseOpen(open) {
    pauseOpen = open;
    $('lines').hidden = !open;
    $('pauseChevron').classList.toggle('open', open);
  }
  function renderPause(p) {
    $('pauseBtn').classList.toggle('running', p.running);
    $('pauseBtn').title = p.running ? 'Pausentimer beenden' : 'Pausentimer starten';
    var title = $('pauseTitle');
    title.textContent = p.running && p.seconds_left !== null ? 'noch ' + mmss(p.seconds_left) : 'Pausentimer';
    title.classList.toggle('run', p.running);
    maxLines = p.max_lines;
    maxChars = p.max_chars;
    $('lines').title = 'Ansagen für die Pausenfolie – eine Zeile pro Ansage (höchstens ' + p.max_lines + ' Zeilen mit je ' + p.max_chars + ' Zeichen)';
    if (document.activeElement !== $('lines') && !$('lines').dataset.dirty) { $('lines').value = p.lines.join('\n'); }
    if (document.activeElement !== $('endTime') && !$('endTime').dataset.dirty) { $('endTime').value = p.end; }
  }

  /* ---------------- Suche ---------------- */
  function showResults() {
    $('results').hidden = false;
    $('tab-song').classList.add('searching');
  }
  function hideResults() {
    $('results').hidden = true;
    $('results').textContent = '';
    $('tab-song').classList.remove('searching');
  }
  function search() {
    var text = $('q').value.trim();
    var list = $('results');
    if (!text) { hideResults(); return; }
    var seq = ++searchSeq;
    request('POST', '/api/search', { text: text }).then(function (data) {
      if (seq !== searchSeq) { return; }
      list.textContent = '';
      showResults();
      if (!data.songs.length) {
        var none = el('li', 'muted', 'Kein Lied gefunden');
        list.appendChild(none);
        return;
      }
      data.songs.forEach(function (song) {
        var item = el('li');
        var btn = el('button', '', 'Nr. ' + song.nummer + (song.titel ? ' – ' + song.titel : ''));
        btn.type = 'button';
        btn.dataset.rowid = String(song.rowid);
        item.appendChild(btn);
        list.appendChild(item);
      });
      if (data.more) { list.appendChild(el('li', 'muted', 'Weitere Treffer – bitte genauer suchen')); }
    }).catch(function (err) { if (err.message !== 'Bitte anmelden.') { toast(err.message, true); } });
  }

  /* ---------------- Bedienung ---------------- */
  function on(id, type, handler) { $(id).addEventListener(type, handler); }

  on('loginBtn', 'click', login);
  on('pin', 'keydown', function (e) { if (e.key === 'Enter') { login(); } });
  on('logoutBtn', 'click', showLogin);
  on('escBtn', 'click', function () { actQuiet('escape'); });

  function showTab(name) {
    Array.prototype.forEach.call(document.querySelectorAll('.tab[data-tab]'), function (t) { t.classList.toggle('on', t.dataset.tab === name); });
    Array.prototype.forEach.call(document.querySelectorAll('.tabpage'), function (p) { p.hidden = p.id !== 'tab-' + name; });
    $('moreBtn').classList.toggle('on', name === 'more');
  }
  on('tabs', 'click', function (e) {
    var btn = e.target.closest('.tab[data-tab]');
    if (btn) { showTab(btn.dataset.tab); }
  });
  on('moreBtn', 'click', function () { showTab($('tab-more').hidden ? 'more' : 'song'); });
  on('songTitle', 'click', function () {
    if (!state || !state.song) { return; }
    $('q').value = String(state.song.nummer);
    $('q').focus();
    $('q').select();
  });
  on('q', 'focus', function () { showTab('song'); });

  on('q', 'input', function () { clearTimeout(searchTimer); searchTimer = setTimeout(search, 250); });
  on('q', 'keydown', function (e) { if (e.key === 'Enter') { clearTimeout(searchTimer); search(); } });
  on('results', 'click', function (e) {
    var btn = e.target.closest('button[data-rowid]');
    if (!btn) { return; }
    act('select', { rowid: Number(btn.dataset.rowid) }).then(function () {
      hideResults();
      $('q').value = '';
    }).catch(function () {});
  });
  on('gongBtn', 'click', function () { actQuiet('gong'); });
  on('showBtn', 'click', function () { actQuiet('show_song'); });
  on('closeBeamerBtn', 'click', function () { actQuiet('beamer_close'); });
  on('a1', 'click', function () { actQuiet('audio_play', { slot: 0 }); });
  on('a2', 'click', function () { actQuiet('audio_play', { slot: 1 }); });
  on('playBtn', 'click', function () { actQuiet('audio_toggle'); });
  on('stopBtn', 'click', function () { actQuiet('audio_stop'); });
  on('seek', 'pointerdown', function () { seeking = true; });
  on('seek', 'input', function () { $('seek').style.setProperty('--p', $('seek').value + '%'); });
  on('seek', 'change', function () {
    seeking = false;
    actQuiet('audio_seek', { percent: Number($('seek').value) });
  });

  on('recBtn', 'click', function () { actQuiet('record_toggle'); });
  on('saveBtn', 'click', function () {
    act('record_save', { preacher: $('preacher').value }).then(function () {
      $('preacher').value = '';
      toast('Aufnahme gespeichert');
    }).catch(function () {});
  });

  on('prevBtn', 'click', function () { actQuiet('gallery_step', { delta: -1 }); });
  on('nextBtn', 'click', function () { actQuiet('gallery_step', { delta: 1 }); });
  on('galleryCloseBtn', 'click', function () { actQuiet('gallery_close'); });
  on('thumbs', 'click', function (e) {
    var del = e.target.closest('button[data-del]');
    if (del) {
      e.stopPropagation();
      if (window.confirm('Dieses Bild entfernen?')) { actQuiet('images_remove', { index: Number(del.dataset.del) }); }
      return;
    }
    var tile = e.target.closest('.thumb');
    if (tile) { actQuiet('images_open', { index: Number(tile.dataset.index) }); }
  });
  on('clearBtn', 'click', function () {
    if (window.confirm('Alle abgelegten Bilder entfernen?')) { actQuiet('images_clear'); }
  });
  on('queueClearBtn', 'click', function () {
    if (window.confirm('Vorgemerkte Bilder auf dem Server verwerfen?')) {
      request('POST', '/api/inbox_clear', {}).then(function () { showQueue(0); }).catch(function (err) { toast(err.message, true); });
    }
  });
  on('upload', 'change', function () {
    var files = Array.prototype.slice.call($('upload').files);
    $('upload').value = '';
    var done = 0, failed = 0, queued = 0;
    files.reduce(function (chain, file) {
      return chain.then(function () {
        return request('POST', '/api/upload?name=' + encodeURIComponent(file.name), undefined, file).then(function (r) {
          if (r.queued) { queued += 1; refreshQueue(); }
          done += r.added || 0;
          failed += r.failed || 0;
        }).catch(function (err) { failed += 1; toast(err.message, true); });
      });
    }, Promise.resolve()).then(function () {
      if (queued) { toast(queued + (queued === 1 ? ' Bild' : ' Bilder') + ' vorgemerkt – kommen beim nächsten Programmstart'); }
      if (done) { toast(done + (done === 1 ? ' Bild' : ' Bilder') + ' hinzugefügt'); }
      refresh();
    });
  });

  on('camList', 'click', function (e) {
    var btn = e.target.closest('button[data-cam]');
    if (btn) { actQuiet('camera_fullscreen', { index: Number(btn.dataset.cam) }); }
  });
  on('camCloseBtn', 'click', function () { actQuiet('camera_close'); });
  on('atemCard', 'click', function (e) {
    var btn = e.target.closest('button[data-atem]');
    if (btn) { act('atem', { kind: btn.dataset.atem }).then(function () { toast('ATEM umgeschaltet'); }).catch(function () {}); }
  });

  function sendPauseSettings() {
    return act('pause_set', { lines: $('lines').value.split('\n'), end: $('endTime').value }, true).then(function () {
      delete $('lines').dataset.dirty;
      delete $('endTime').dataset.dirty;
    });
  }
  on('lines', 'input', function () { clampLines(); $('lines').dataset.dirty = '1'; });
  on('endTime', 'input', function () { $('endTime').dataset.dirty = '1'; });
  on('lines', 'change', function () { sendPauseSettings().catch(function (err) { toast(err.message, true); }); });
  on('endTime', 'change', function () { sendPauseSettings().catch(function (err) { toast(err.message, true); }); });
  on('pauseTitle', 'click', function () { setPauseOpen(!pauseOpen); });
  on('pauseChevron', 'click', function () { setPauseOpen(!pauseOpen); });
  on('pauseBtn', 'click', function () {
    sendPauseSettings().then(function () { return act('pause_toggle'); }).catch(function (err) { toast(err.message, true); });
  });
  on('syncBtn', 'click', function () { actQuiet('sync_now'); });

  // Kein Zoomen und kein seitliches Verschieben (iOS ignoriert user-scalable=no)
  ['gesturestart', 'gesturechange', 'gestureend'].forEach(function (name) {
    document.addEventListener(name, function (e) { e.preventDefault(); });
  });
  document.addEventListener('touchmove', function (e) { if (e.touches.length > 1) { e.preventDefault(); } }, { passive: false });
  var lastTouch = 0;
  document.addEventListener('touchend', function (e) {
    var now = Date.now();
    if (now - lastTouch < 350) { e.preventDefault(); }
    lastTouch = now;
  }, { passive: false });

  if (token) { showApp(); } else { showLogin(); }
})();
LM_PAGE_JS;

const PAGE_MANIFEST = <<<'LM_PAGE_MANIFEST'
{
 "name": "LiedManager – Fernsteuerung",
 "short_name": "LiedManager",
 "lang": "de",
 "start_url": "__SELF__",
 "scope": "./",
 "display": "standalone",
 "background_color": "#1A1817",
 "theme_color": "#1A1817",
 "icons": [
  {
   "src": "__SELF__?asset=icon192",
   "sizes": "192x192",
   "type": "image/png"
  },
  {
   "src": "__SELF__?asset=icon512",
   "sizes": "512x512",
   "type": "image/png"
  }
 ]
}
LM_PAGE_MANIFEST;

// Logo (PNG, Base64) für Browser-Tab, Lesezeichen und „Zum Home-Bildschirm“
const PAGE_ICONS = [
    'favicon' => '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',
    'icon180' => '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',
    'icon192' => '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',
    'icon512' => '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',
];

// ---------------------------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------------------------
/** Liste der Zugangsdaten, die noch nicht stimmen (leer = alles eingetragen). Es werden nie die Werte selbst genannt. */
function config_problems(): array {
    $problems = [];
    if (strlen(TOKEN) < 16) {
        $problems[] = 'TOKEN ist zu kurz (mindestens 16 Zeichen, eingetragen: ' . strlen(TOKEN) . ')';
    } elseif (strpos(TOKEN, 'HIER-') === 0) {
        $problems[] = 'TOKEN steht noch auf dem Platzhalter';
    }
    if (strlen(PIN) < 8) {
        $problems[] = 'PIN ist zu kurz (mindestens 8 Zeichen, eingetragen: ' . strlen(PIN) . ')';
    } elseif (strpos(PIN, 'HIER-') === 0) {
        $problems[] = 'PIN steht noch auf dem Platzhalter';
    }
    if (DB_NAME === 'dXXXXXXX') {
        $problems[] = 'DB_NAME ist noch nicht eingetragen';
    }
    if (DB_USER === 'dXXXXXXX') {
        $problems[] = 'DB_USER ist noch nicht eingetragen';
    }
    if (strpos(DB_PASS, 'HIER-') === 0) {
        $problems[] = 'DB_PASS steht noch auf dem Platzhalter';
    }
    return $problems;
}

function configured(): bool {
    return count(config_problems()) === 0;
}

function is_https(): bool {
    $https = strtolower((string)($_SERVER['HTTPS'] ?? ''));
    return ($https !== '' && $https !== 'off')
        || (string)($_SERVER['SERVER_PORT'] ?? '') === '443'
        || strtolower((string)($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '')) === 'https';
}

function self_name(): string {
    $name = basename((string)($_SERVER['SCRIPT_NAME'] ?? 'remote.php'));
    return preg_match('/^[A-Za-z0-9._-]+$/', $name) ? $name : 'remote.php';
}

function security_headers(): void {
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    header('X-Frame-Options: DENY');
    header('Referrer-Policy: no-referrer');
    header('Strict-Transport-Security: max-age=31536000');
    header("Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; "
        . "connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'");
}

function send(int $code, string $body, string $type, array $extra = []): void {
    http_response_code($code);
    security_headers();
    header('Content-Type: ' . $type);
    foreach ($extra as $name => $value) {
        header($name . ': ' . $value);
    }
    echo $body;
    exit;
}

function json_out($data, int $code = 200, array $extra = []): void {
    send($code, json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
        'application/json; charset=utf-8', $extra);
}

function fail(int $code, string $message, array $extra = []): void {
    json_out(['error' => $message], $code, $extra);
}

function read_body(int $limit): string {
    $length = (int)($_SERVER['CONTENT_LENGTH'] ?? 0);
    if ($length > $limit) {
        fail(413, 'Die Anfrage ist zu groß.');
    }
    $raw = file_get_contents('php://input', false, null, 0, $limit + 1);
    if ($raw === false) {
        $raw = '';
    }
    if (strlen($raw) > $limit) {
        fail(413, 'Die Anfrage ist zu groß.');
    }
    if ($raw === '' && $length > 0) {
        fail(413, 'Die Anfrage ist größer als der Server erlaubt (post_max_size).');
    }
    return $raw;
}

function client_ip(): string {
    return substr((string)($_SERVER['REMOTE_ADDR'] ?? 'unbekannt'), 0, 45);
}

// ---------------------------------------------------------------------------------------------
// Datenbank
// ---------------------------------------------------------------------------------------------
function db(): PDO {
    static $db = null;
    if ($db !== null) {
        return $db;
    }
    $db = new PDO('mysql:host=' . DB_HOST . ';dbname=' . DB_NAME . ';charset=utf8mb4', DB_USER, DB_PASS, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    try {
        $db->query('SELECT 1 FROM lm_rm_meta LIMIT 1');
    } catch (PDOException $e) {
        create_tables($db);                 // beim allerersten Aufruf
    }
    try {
        $db->query('SELECT 1 FROM lm_rm_inbox LIMIT 1');
    } catch (PDOException $e) {
        create_inbox($db);                  // Update von einer älteren remote.php
    }
    try {
        $db->query('SELECT dev FROM lm_rm_jobs LIMIT 1');
    } catch (PDOException $e) {
        create_devices($db);                // Update: mehrere Computer
    }
    try {
        $db->query('SELECT did FROM lm_rm_devices LIMIT 1');
    } catch (PDOException $e) {
        $db->exec('ALTER TABLE lm_rm_devices ADD COLUMN did VARCHAR(20) NOT NULL DEFAULT ""');
    }
    try {
        $db->query('SELECT 1 FROM lm_rm_reports LIMIT 1');
    } catch (PDOException $e) {
        create_reports($db);                // Update von einer älteren remote.php
    }
    return $db;
}

function create_devices(PDO $db): void {
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_devices (
        name  VARCHAR(40) NOT NULL PRIMARY KEY,
        alive INT NOT NULL DEFAULT 0,
        state MEDIUMTEXT NULL,
        did   VARCHAR(20) NOT NULL DEFAULT ""
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
    $db->exec('ALTER TABLE lm_rm_jobs ADD COLUMN dev VARCHAR(40) NOT NULL DEFAULT ""');
    $db->exec('ALTER TABLE lm_rm_inbox ADD COLUMN dev VARCHAR(40) NOT NULL DEFAULT ""');
}

/** Name des Computers: nur harmlose Zeichen, höchstens 40. */
function dev_clean(string $name): string {
    $name = trim((string)preg_replace('/[^\p{L}\p{N} ._-]/u', '', $name));
    return mb_substr($name, 0, 40);
}

/** Der Computer, um den es in dieser Anfrage geht (Programm: aus der Anfrage; Browser: gewählt, sonst der zuletzt aktive). */
function cur_dev(?string $set = null): string {
    static $dev = null;
    if ($set !== null) {
        $dev = $set;
    }
    return $dev ?? '';
}

function browser_dev(PDO $db): string {
    $dev = dev_clean((string)($_SERVER['HTTP_X_LM_DEVICE'] ?? ''));
    if ($dev === '') {
        $dev = (string)$db->query('SELECT name FROM lm_rm_devices ORDER BY alive DESC LIMIT 1')->fetchColumn();
    }
    return $dev;
}

function create_tables(PDO $db): void {
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_jobs (
        id      BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        created INT NOT NULL,
        kind    VARCHAR(12) NOT NULL,
        name    VARCHAR(80) NOT NULL,
        body    LONGBLOB NULL,
        status  TINYINT NOT NULL DEFAULT 0,
        http    SMALLINT NOT NULL DEFAULT 0,
        ctype   VARCHAR(80) NOT NULL DEFAULT "",
        result  LONGBLOB NULL,
        INDEX idx_status (status, id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_sessions (
        h       CHAR(64) NOT NULL PRIMARY KEY,
        created INT NOT NULL,
        expires INT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_fail (
        ip    VARCHAR(45) NOT NULL PRIMARY KEY,
        n     INT NOT NULL,
        since INT NOT NULL,
        until INT NOT NULL,
        lvl   INT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_meta (
        id    TINYINT NOT NULL PRIMARY KEY,
        alive INT NOT NULL,
        state MEDIUMTEXT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
    $db->exec('INSERT IGNORE INTO lm_rm_meta (id, alive, state) VALUES (1, 0, NULL)');
}

function create_inbox(PDO $db): void {
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_inbox (
        id      BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        created INT NOT NULL,
        name    VARCHAR(80) NOT NULL,
        body    LONGBLOB NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
}

function create_reports(PDO $db): void {
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_reports (
        id      BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        created INT NOT NULL,
        fp      CHAR(16) NOT NULL,
        version VARCHAR(40) NOT NULL,
        system  VARCHAR(80) NOT NULL,
        title   VARCHAR(300) NOT NULL,
        detail  TEXT NULL,
        n       INT NOT NULL DEFAULT 1,
        INDEX idx_fp (fp)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
}

/** Meldung vom Programm speichern; gleiche Probleme (gleicher Fingerabdruck) werden nur hochgezählt. */
function store_report(PDO $db, array $in): void {
    $fp = preg_replace('/[^0-9a-f]/', '', strtolower((string)($in['fp'] ?? '')));
    $fp = substr($fp, 0, 16);
    if (strlen($fp) < 8) {
        fail(400, 'Ungültige Meldung.');
    }
    $db->prepare('DELETE FROM lm_rm_reports WHERE created < ?')->execute([time() - REPORT_KEEP]);
    $update = $db->prepare('UPDATE lm_rm_reports SET n = n + 1, created = ? WHERE fp = ? AND created > ?');
    $update->execute([time(), $fp, time() - 86400]);
    if ($update->rowCount() === 0) {
        $db->prepare('INSERT INTO lm_rm_reports (created, fp, version, system, title, detail) VALUES (?, ?, ?, ?, ?, ?)')
            ->execute([time(), $fp, substr((string)($in['version'] ?? ''), 0, 40), substr((string)($in['system'] ?? ''), 0, 80),
                mb_substr((string)($in['title'] ?? ''), 0, 300), mb_substr((string)($in['detail'] ?? ''), 0, 6000)]);
    }
    $db->exec('DELETE FROM lm_rm_reports WHERE id <= (SELECT m FROM (SELECT MAX(id) - ' . REPORT_MAX . ' AS m FROM lm_rm_reports) x)');
}

function inbox_pending(PDO $db): int {
    $q = $db->prepare('SELECT COUNT(*) FROM lm_rm_inbox WHERE dev = ?');
    $q->execute([cur_dev()]);
    return (int)$q->fetchColumn();
}

/** Bild vormerken, solange das Programm nicht läuft; es wird beim nächsten Verbinden abgeholt. */
function queue_upload(PDO $db, string $name, string $data): void {
    $db->prepare('DELETE FROM lm_rm_inbox WHERE created < ?')->execute([time() - INBOX_KEEP]);
    $row = $db->query('SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(body)), 0) AS bytes FROM lm_rm_inbox')
        ->fetch(PDO::FETCH_ASSOC);
    if ((int)$row['n'] >= INBOX_MAX_FILES || (int)$row['bytes'] + strlen($data) > INBOX_MAX_BYTES) {
        fail(507, 'Der Zwischenspeicher auf dem Server ist voll. Bitte zuerst das Programm starten, '
            . 'damit die vorgemerkten Bilder abgeholt werden.');
    }
    $db->prepare('INSERT INTO lm_rm_inbox (created, name, body, dev) VALUES (?, ?, ?, ?)')->execute([time(), $name, $data, cur_dev()]);
    json_out(['queued' => true, 'added' => 0, 'failed' => 0, 'pending' => inbox_pending($db)], 202);
}

function app_alive(PDO $db): bool {
    $q = $db->prepare('SELECT alive FROM lm_rm_devices WHERE name = ?');
    $q->execute([cur_dev()]);
    $alive = (int)$q->fetchColumn();
    return $alive > 0 && time() - $alive <= APP_TIMEOUT;
}

/** Kennung des Computers aus der Anfrage des Programms (bleibt beim Umbenennen gleich). */
function cur_did(?string $set = null): string {
    static $did = '';
    if ($set !== null) {
        $did = $set;
    }
    return $did;
}

/** Ein umbenannter Computer ersetzt seinen alten Namen; Einträge ohne Kennung (alte Programmversion) verschwinden nach 5 Minuten. */
function device_cleanup(PDO $db): void {
    $did = cur_did();
    if ($did !== '') {
        $q = $db->prepare('SELECT name FROM lm_rm_devices WHERE did = ? AND name <> ?');
        $q->execute([$did, cur_dev()]);
        foreach ($q->fetchAll(PDO::FETCH_COLUMN) as $old) {
            $db->prepare('UPDATE lm_rm_inbox SET dev = ? WHERE dev = ?')->execute([cur_dev(), $old]);
            $db->prepare('DELETE FROM lm_rm_jobs WHERE dev = ?')->execute([$old]);
            $db->prepare('DELETE FROM lm_rm_devices WHERE name = ?')->execute([$old]);
        }
    }
    $db->prepare('DELETE FROM lm_rm_devices WHERE did = "" AND alive < ?')->execute([time() - 300]);
}

function touch_alive(PDO $db): void {
    $q = $db->prepare('INSERT INTO lm_rm_devices (name, alive, did) VALUES (?, ?, ?) ON DUPLICATE KEY UPDATE alive = VALUES(alive), did = VALUES(did)');
    $q->execute([cur_dev(), time(), cur_did()]);
    device_cleanup($db);
}

// ---------------------------------------------------------------------------------------------
// Aufnahmen aus dem Programm (in Stücken, mit Fortsetzen)
// ---------------------------------------------------------------------------------------------
function rec_dir(): string {
    $dir = __DIR__ . '/' . REC_DIR;
    if (!is_dir($dir) && !@mkdir($dir, 0755, true)) {
        fail(500, 'Der Ordner "' . REC_DIR . '" konnte auf dem Server nicht angelegt werden.');
    }
    if (!is_file($dir . '/.htaccess')) {
        @file_put_contents($dir . '/.htaccess', "Options -Indexes\n");   // keine Dateiliste im Browser
    }
    if (!is_file($dir . '/index.html')) {
        @file_put_contents($dir . '/index.html', '');
    }
    return $dir;
}

function rec_name(string $name): string {
    $name = basename(str_replace('\\', '/', $name));
    $name = (string)preg_replace('/[^\p{L}\p{N} ._()\-]/u', '_', $name);
    $name = trim($name, '. ');
    $ok = false;
    foreach (REC_EXTENSIONS as $extension) {
        if (strtolower(substr($name, -strlen($extension))) === $extension) {
            $ok = true;
        }
    }
    if (!$ok || $name === '' || strlen($name) > 120) {
        fail(415, 'Dateiname oder Dateityp nicht erlaubt.');
    }
    return $name;
}

function rec_unique(string $dir, string $name): string {
    $dot = strrpos($name, '.');
    $base = substr($name, 0, $dot);
    $ext = substr($name, $dot);
    $candidate = $name;
    for ($i = 1; is_file($dir . '/' . $candidate); $i++) {
        $candidate = $base . ' (' . $i . ')' . $ext;
    }
    return $candidate;
}

function rec_size(array $in): void {
    $part = rec_dir() . '/' . rec_name((string)($in['name'] ?? '')) . '.part';
    clearstatcache();
    json_out(['size' => is_file($part) ? (int)filesize($part) : 0]);
}

function rec_put(array $in): void {
    $dir = rec_dir();
    $name = rec_name((string)($in['name'] ?? ''));
    $offset = (int)($in['offset'] ?? 0);
    $data = base64_decode((string)($in['data'] ?? ''), true);
    if ($data === false || $offset < 0) {
        fail(400, 'Ungültiges Stück.');
    }
    $part = $dir . '/' . $name . '.part';
    $handle = @fopen($part, 'c+b');
    if (!$handle) {
        fail(500, 'Die Datei konnte auf dem Server nicht angelegt werden.');
    }
    flock($handle, LOCK_EX);
    clearstatcache();
    $have = (int)filesize($part);
    if ($offset !== $have && !($offset === 0)) {
        flock($handle, LOCK_UN);
        fclose($handle);
        fail(409, 'Falsche Position.');
    }
    if ($offset === 0) {
        ftruncate($handle, 0);
    }
    if ($offset + strlen($data) > REC_MAX_BYTES) {
        flock($handle, LOCK_UN);
        fclose($handle);
        @unlink($part);
        fail(413, 'Die Aufnahme ist größer als erlaubt.');
    }
    fseek($handle, $offset);
    $written = fwrite($handle, $data);
    fflush($handle);
    flock($handle, LOCK_UN);
    fclose($handle);
    if ($written === false || $written !== strlen($data)) {
        fail(500, 'Schreiben auf dem Server fehlgeschlagen (Speicherplatz?).');
    }
    $final = $name;
    if (!empty($in['last'])) {
        $final = rec_unique($dir, $name);
        if (!@rename($part, $dir . '/' . $final)) {
            fail(500, 'Die Datei konnte nicht abgeschlossen werden.');
        }
    }
    json_out(['ok' => true, 'size' => $offset + strlen($data), 'name' => $final]);
}

// ---------------------------------------------------------------------------------------------
// Anmeldung im Browser (PIN) und Schutz gegen Raten
// ---------------------------------------------------------------------------------------------
function lock_seconds(PDO $db, string $ip): int {
    $q = $db->prepare('SELECT until FROM lm_rm_fail WHERE ip = ?');
    $q->execute([$ip]);
    $until = (int)$q->fetchColumn();
    return max(0, $until - time());
}

function note_failure(PDO $db, string $ip): void {
    $now = time();
    $q = $db->prepare('SELECT n, since, until, lvl FROM lm_rm_fail WHERE ip = ?');
    $q->execute([$ip]);
    $row = $q->fetch(PDO::FETCH_ASSOC) ?: ['n' => 0, 'since' => $now, 'until' => 0, 'lvl' => 0];
    $n = (int)$row['n'] + 1;
    $since = (int)$row['since'];
    $until = (int)$row['until'];
    $lvl = (int)$row['lvl'];
    if ($ip === '*') {
        if ($now - $since > 600) {
            $n = 1;
            $since = $now;
        }
        if ($n >= GLOBAL_FAILURES) {
            $until = $now + 300;
            $n = 0;
        }
    } elseif ($n >= MAX_FAILURES) {
        $lvl++;
        $until = $now + min(30 * (2 ** ($lvl - 1)), 600);
        $n = 0;
    }
    $up = $db->prepare('INSERT INTO lm_rm_fail (ip, n, since, until, lvl) VALUES (?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE n = VALUES(n), since = VALUES(since), until = VALUES(until), lvl = VALUES(lvl)');
    $up->execute([$ip, $n, $since, $until, $lvl]);
}

function do_login(PDO $db): void {
    $ip = client_ip();
    $wait = max(lock_seconds($db, $ip), lock_seconds($db, '*'));
    if ($wait > 0) {
        fail(429, 'Zu viele Versuche. Bitte in ' . $wait . ' s erneut probieren.', ['Retry-After' => (string)$wait]);
    }
    $body = json_decode(read_body(1024), true);
    $pin = is_array($body) ? (string)($body['pin'] ?? '') : '';
    if ($pin !== '' && hash_equals(PIN, $pin)) {
        $db->prepare('DELETE FROM lm_rm_fail WHERE ip = ?')->execute([$ip]);
        $now = time();
        $db->prepare('DELETE FROM lm_rm_sessions WHERE expires < ?')->execute([$now]);
        $count = (int)$db->query('SELECT COUNT(*) FROM lm_rm_sessions')->fetchColumn();
        if ($count >= MAX_SESSIONS) {
            $surplus = $count - MAX_SESSIONS + 1;
            $db->exec('DELETE FROM lm_rm_sessions ORDER BY created ASC LIMIT ' . (int)$surplus);
        }
        $token = bin2hex(random_bytes(24));
        $db->prepare('INSERT INTO lm_rm_sessions (h, created, expires) VALUES (?, ?, ?)')
            ->execute([hash('sha256', $token), $now, $now + SESSION_SECONDS]);
        json_out(['token' => $token]);
    }
    note_failure($db, $ip);
    note_failure($db, '*');
    usleep(500000);                                   // bremst automatisches Raten zusätzlich
    fail(403, 'Falsche PIN.');
}

function authorized(PDO $db): bool {
    $token = trim((string)($_SERVER['HTTP_X_LM_TOKEN'] ?? ''));
    if ($token === '' || strlen($token) > 200) {
        return false;
    }
    $q = $db->prepare('SELECT expires FROM lm_rm_sessions WHERE h = ?');
    $q->execute([hash('sha256', $token)]);
    $expires = $q->fetchColumn();
    return $expires !== false && (int)$expires >= time();
}

// ---------------------------------------------------------------------------------------------
// Aufträge für das Programm (Browser -> Website -> Programm -> Website -> Browser)
// ---------------------------------------------------------------------------------------------
function run_job(PDO $db, string $kind, string $name, ?string $body, int $wait): void {
    if (!app_alive($db)) {
        fail(503, 'Das Programm ist gerade nicht erreichbar (nicht gestartet oder ohne Internet).');
    }
    $now = time();
    $db->prepare('DELETE FROM lm_rm_jobs WHERE created < ?')->execute([$now - 300]);
    $db->prepare('INSERT INTO lm_rm_jobs (created, kind, name, body, dev) VALUES (?, ?, ?, ?, ?)')
        ->execute([$now, $kind, $name, $body, cur_dev()]);
    $id = (int)$db->lastInsertId();

    $deadline = microtime(true) + $wait;
    $q = $db->prepare('SELECT status, http, ctype, result FROM lm_rm_jobs WHERE id = ?');
    while (microtime(true) < $deadline) {
        $q->execute([$id]);
        $row = $q->fetch(PDO::FETCH_ASSOC);
        if ($row && (int)$row['status'] === 2) {
            $db->prepare('DELETE FROM lm_rm_jobs WHERE id = ?')->execute([$id]);
            $extra = $kind === 'thumb' ? ['Cache-Control' => 'private, max-age=3600'] : [];
            send((int)$row['http'] ?: 200, (string)$row['result'], (string)$row['ctype'] ?: 'application/json', $extra);
        }
        usleep(120000);
    }
    $db->prepare('DELETE FROM lm_rm_jobs WHERE id = ?')->execute([$id]);
    fail(504, 'Das Programm antwortet gerade nicht.');
}

function browser_api(string $api): void {
    $db = db();
    $method = (string)($_SERVER['REQUEST_METHOD'] ?? 'GET');
    if ($api === 'login') {
        if ($method !== 'POST') {
            fail(405, 'Nur POST.');
        }
        do_login($db);
    }
    if (!authorized($db)) {
        fail(401, 'Bitte mit der PIN anmelden.');
    }
    cur_dev(browser_dev($db));
    if ($api === 'devices' && $method === 'GET') {
        $rows = $db->query('SELECT name, alive FROM lm_rm_devices ORDER BY name')->fetchAll(PDO::FETCH_ASSOC);
        $list = [];
        foreach ($rows as $row) {
            $list[] = ['name' => $row['name'], 'online' => (int)$row['alive'] > 0 && time() - (int)$row['alive'] <= APP_TIMEOUT];
        }
        json_out(['devices' => $list, 'current' => cur_dev()]);
    }

    if ($api === 'state' && $method === 'GET') {
        $q = $db->prepare('SELECT alive, state FROM lm_rm_devices WHERE name = ?');
        $q->execute([cur_dev()]);
        $row = $q->fetch(PDO::FETCH_ASSOC);
        if (!$row || $row['state'] === null || (int)$row['alive'] === 0 || time() - (int)$row['alive'] > APP_TIMEOUT) {
            fail(503, 'Das Programm ist gerade nicht erreichbar (nicht gestartet oder ohne Internet).');
        }
        send(200, (string)$row['state'], 'application/json; charset=utf-8');
    }

    if (strpos($api, 'thumb/') === 0 && $method === 'GET') {
        $index = substr($api, 6);
        if (!ctype_digit($index) || strlen($index) > 4) {
            fail(400, 'Ungültige Anfrage.');
        }
        run_job($db, 'thumb', $index, null, JOB_WAIT);
    }

    if ($api === 'upload' && $method === 'POST') {
        $name = (string)($_GET['name'] ?? '');
        $lower = strtolower($name);
        $ok = false;
        foreach (UPLOAD_EXTENSIONS as $extension) {
            if (substr($lower, -strlen($extension)) === $extension) {
                $ok = true;
            }
        }
        if (!$ok || strlen($name) > 80) {
            fail(415, 'Nur Bilder (PNG, JPG, GIF, BMP, WebP) sind erlaubt.');
        }
        $data = read_body(MAX_UPLOAD);
        if ($data === '') {
            fail(400, 'Die Datei ist leer.');
        }
        if (!app_alive($db)) {
            queue_upload($db, $name, $data);      // Programm läuft nicht: vormerken statt ablehnen
        }
        run_job($db, 'upload', $name, base64_encode($data), UPLOAD_WAIT);
    }

    if ($api === 'inbox' && $method === 'GET') {
        json_out(['pending' => inbox_pending($db)]);
    }
    if ($api === 'reports' && $method === 'GET') {
        $rows = $db->query('SELECT id, created, version, system, title, detail, n FROM lm_rm_reports ORDER BY id DESC LIMIT 30')
            ->fetchAll(PDO::FETCH_ASSOC);
        json_out(['reports' => $rows]);
    }
    if ($api === 'reports_clear' && $method === 'POST') {
        $db->exec('DELETE FROM lm_rm_reports');
        json_out(['reports' => []]);
    }
    if ($api === 'inbox_clear' && $method === 'POST') {
        $db->prepare('DELETE FROM lm_rm_inbox WHERE dev = ?')->execute([cur_dev()]);
        json_out(['pending' => 0]);
    }

    if ($method === 'POST' && preg_match('/^[a-z_]{1,40}$/', $api)) {
        if (stripos((string)($_SERVER['CONTENT_TYPE'] ?? ''), 'application/json') === false) {
            fail(415, 'Erwartet JSON.');
        }
        $raw = read_body(MAX_JSON);
        $args = json_decode($raw === '' ? '{}' : $raw, true);
        if (!is_array($args)) {
            fail(400, 'Erwartet ein JSON-Objekt.');
        }
        run_job($db, 'action', $api, $raw === '' ? '{}' : $raw, JOB_WAIT);
    }

    fail(404, 'Nicht gefunden.');
}

// ---------------------------------------------------------------------------------------------
// Schnittstelle für das Programm (LiedManager ruft von sich aus an)
// ---------------------------------------------------------------------------------------------
function app_api(): void {
    $in = json_decode(read_body(MAX_APP_BODY), true);
    if (!is_array($in)) {
        fail(400, 'Ungültige Anfrage.');
    }
    if (!hash_equals(TOKEN, (string)($in['token'] ?? ''))) {
        http_response_code(401);
        exit;
    }
    $db = db();
    $dev = dev_clean((string)($in['dev'] ?? ''));
    cur_dev($dev === '' ? 'Computer' : $dev);
    cur_did(substr((string)preg_replace('/[^a-z0-9]/', '', strtolower((string)($in['did'] ?? ''))), 0, 20));
    $action = (string)($in['action'] ?? '');

    if ($action === 'poll') {
        touch_alive($db);
        $db->prepare('DELETE FROM lm_rm_jobs WHERE created < ?')->execute([time() - 300]);
        $hold = max(0, min(HOLD, (int)($in['hold'] ?? HOLD)));
        $deadline = microtime(true) + $hold;
        $select = $db->prepare('SELECT id, kind, name, body FROM lm_rm_jobs WHERE status = 0 AND dev = ? ORDER BY id LIMIT 5');
        $claim = $db->prepare('UPDATE lm_rm_jobs SET status = 1 WHERE id = ? AND status = 0');
        $lastTouch = time();
        $pending = inbox_pending($db);               // vorgemerkte Bilder: Programm soll sie gleich abholen
        while (true) {
            $select->execute([cur_dev()]);
            $jobs = [];
            foreach ($select->fetchAll(PDO::FETCH_ASSOC) as $job) {
                $claim->execute([(int)$job['id']]);
                if ($claim->rowCount() === 1) {          // nur wer den Auftrag wirklich bekommen hat, führt ihn aus
                    $jobs[] = ['id' => (int)$job['id'], 'kind' => $job['kind'], 'name' => $job['name'],
                        'body' => $job['body'] === null ? '' : (string)$job['body']];
                }
            }
            if ($jobs || $pending > 0 || microtime(true) >= $deadline) {
                json_out(['format' => FORMAT, 'jobs' => $jobs, 'inbox' => $pending]);
            }
            if (time() - $lastTouch >= 5) {
                touch_alive($db);
                $lastTouch = time();
            }
            usleep(250000);
        }
    }

    if ($action === 'state') {
        $data = (string)($in['data'] ?? '');
        if ($data === '' || strlen($data) > 1048576 || !is_array(json_decode($data, true))) {
            fail(400, 'Ungültiger Zustand.');
        }
        $db->prepare('INSERT INTO lm_rm_devices (name, alive, state, did) VALUES (?, ?, ?, ?) ON DUPLICATE KEY UPDATE alive = VALUES(alive), state = VALUES(state), did = VALUES(did)')
            ->execute([cur_dev(), time(), $data, cur_did()]);
        device_cleanup($db);
        json_out(['ok' => true]);
    }

    if ($action === 'result') {
        $body = base64_decode((string)($in['body'] ?? ''), true);
        if ($body === false) {
            fail(400, 'Ungültiges Ergebnis.');
        }
        $http = (int)($in['http'] ?? 200);
        if ($http < 100 || $http > 599) {
            $http = 500;
        }
        $ctype = substr((string)($in['ctype'] ?? 'application/json'), 0, 80);
        $db->prepare('UPDATE lm_rm_jobs SET status = 2, http = ?, ctype = ?, result = ? WHERE id = ? AND status = 1')
            ->execute([$http, $ctype, $body, (int)($in['id'] ?? 0)]);
        json_out(['ok' => true]);
    }

    if ($action === 'rec_size') {
        rec_size($in);
    }

    if ($action === 'rec_put') {
        rec_put($in);
    }

    if ($action === 'inbox_get') {
        $q = $db->prepare('SELECT id, name, body FROM lm_rm_inbox WHERE dev = ? ORDER BY id LIMIT 1');
        $q->execute([cur_dev()]);
        $row = $q->fetch(PDO::FETCH_ASSOC);
        json_out(['item' => $row ? ['id' => (int)$row['id'], 'name' => $row['name'],
            'body' => base64_encode((string)$row['body'])] : null]);
    }

    if ($action === 'inbox_done') {
        $db->prepare('DELETE FROM lm_rm_inbox WHERE id = ?')->execute([(int)($in['id'] ?? 0)]);
        json_out(['ok' => true]);
    }

    if ($action === 'rename') {
        // Computer wurde umbenannt: alten Namen entfernen, vorgemerkte Bilder gehen an den neuen Namen
        $old = dev_clean((string)($in['old'] ?? ''));
        if ($old !== '' && $old !== cur_dev()) {
            $db->prepare('UPDATE lm_rm_inbox SET dev = ? WHERE dev = ?')->execute([cur_dev(), $old]);
            $db->prepare('DELETE FROM lm_rm_jobs WHERE dev = ?')->execute([$old]);
            $db->prepare('DELETE FROM lm_rm_devices WHERE name = ?')->execute([$old]);
        }
        json_out(['ok' => true]);
    }

    if ($action === 'report') {
        store_report($db, $in);
        json_out(['ok' => true]);
    }

    if ($action === 'bye') {
        $db->prepare('UPDATE lm_rm_devices SET alive = 0 WHERE name = ?')->execute([cur_dev()]);
        json_out(['ok' => true]);
    }

    fail(400, 'Unbekannte Aktion.');
}

// ---------------------------------------------------------------------------------------------
// Prüfseite (?check) und Webseite
// ---------------------------------------------------------------------------------------------
function check_page(): void {
    $lines = ['LiedManager – Website-Steuerung', ''];
    $lines[] = 'PHP 7.4 oder neuer: ' . (version_compare(PHP_VERSION, '7.4.0', '>=') ? 'OK' : 'zu alt');
    $lines[] = 'Verbindung per HTTPS: ' . (is_https() ? 'OK' : 'NEIN – ohne HTTPS verweigert die Seite den Betrieb');
    $problems = config_problems();
    $lines[] = 'Zugangsdaten eingetragen (TOKEN, PIN, Datenbank): ' . ($problems ? 'NEIN – oben in der Datei eintragen' : 'OK');
    foreach ($problems as $problem) {
        $lines[] = '  – ' . $problem;
    }
    $lines[] = 'Diese Datei: ' . basename(__FILE__) . ' (auf dem Server geändert: ' . date('d.m.Y H:i:s', (int)@filemtime(__FILE__)) . ')';
    if (configured()) {
        try {
            db();
            $lines[] = 'Datenbank: OK';
        } catch (Throwable $e) {
            error_log('LiedManager-Remote: ' . $e->getMessage());
            $lines[] = 'Datenbank: FEHLER – Name, Benutzer und Passwort prüfen';
        }
    }
    send(200, implode("\n", $lines) . "\n", 'text/plain; charset=utf-8');
}

function page(): void {
    $self = self_name();
    $asset = (string)($_GET['asset'] ?? '');
    if ($asset === 'css') {
        send(200, PAGE_CSS, 'text/css; charset=utf-8');
    }
    if ($asset === 'js') {
        send(200, str_replace('__SELF__', $self, PAGE_JS), 'application/javascript; charset=utf-8');
    }
    if ($asset === 'manifest') {
        send(200, str_replace('__SELF__', $self, PAGE_MANIFEST), 'application/manifest+json; charset=utf-8');
    }
    if (isset(PAGE_ICONS[$asset])) {
        send(200, base64_decode(PAGE_ICONS[$asset]), 'image/png', ['Cache-Control' => 'public, max-age=604800']);
    }
    send(200, str_replace('__SELF__', $self, PAGE_HTML), 'text/html; charset=utf-8');
}

// ---------------------------------------------------------------------------------------------
// Verteiler
// ---------------------------------------------------------------------------------------------
try {
    if (isset($_GET['check'])) {
        check_page();
    }
    if (!is_https()) {
        fail(400, 'Nur über HTTPS erreichbar.');
    }
    if (!configured()) {
        fail(503, 'Noch nicht eingerichtet: ' . implode('; ', config_problems()) . '. Bitte in remote.php eintragen und die Datei neu hochladen.');
    }
    if (isset($_GET['api'])) {
        browser_api((string)$_GET['api']);
    }
    if (($_SERVER['REQUEST_METHOD'] ?? '') === 'POST') {
        app_api();
    }
    page();
} catch (Throwable $e) {
    error_log('LiedManager-Remote: ' . $e->getMessage());
    fail(500, 'Serverfehler (Datenbank-Zugang oder Speichergrenze prüfen).');
}
