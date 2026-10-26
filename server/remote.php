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
                 title="Name des Predigers – steht im Dateinamen der Aufnahme (Datum - Prediger)">
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
      <p id="mixerOff" class="muted" hidden>Das Mischpult ist aus. Einschalten: LiedManager → Einstellungen → Mischpult → „X AIR“ (IP-Adresse eintragen).</p>
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
    $('syncStatus').textContent = s.sync.enabled ? s.sync.status : 'Aus – im Programm unter Einstellungen → Datenbank einrichten.';
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
        . "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'");
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
