"""Die Webseite der Fernsteuerung (HTML, CSS und JavaScript), im gleichen Design wie das Programm.

Alle Farben, Rundungen und Schriften kommen als ``values`` von außen (``ui/theme.py``) und werden in die Vorlagen
eingesetzt (Platzhalter ``__NAME__``). Es gibt keine fremden Quellen: Schriften sind die des Programms (Georgia/Arial),
Symbole sind eingebettete SVG-Grafiken – die Seite lädt nichts aus dem Internet.

Die Seite wird in ``server/remote.php`` eingebaut (siehe ``tools/build_remote_site.py``). Dort laufen alle Anfragen über
``remote.php?api=…`` und das Anmelde-Token reist im Header ``X-LM-Token`` (manche Hoster reichen ``Authorization`` nicht
an PHP weiter). Der Platzhalter ``__SELF__`` setzt remote.php beim Ausliefern selbst ein.
"""

REQUIRED_VALUES = (
    "CARD_BG", "SURFACE", "SURFACE_LOW", "SURFACE_HOVER_TOP", "SURFACE_HOVER_BOTTOM", "SURFACE_PRESSED", "BORDER",
    "TRACK_BG", "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_LABEL", "TEXT_MUTED", "ACCENT", "ACCENT_LIGHT", "ACCENT_GLOW",
    "ACCENT_DEEP", "ACCENT_BORDER", "ACCENT_TINT", "PILL_TEXT", "REC_RED", "REC_RUNNING_BG", "REC_TIME_RUNNING",
    "RADIUS", "PANEL_RADIUS", "FS", "FS_SMALL", "SERIF", "BODY", "BTN", "TRACK_NAME_COLOR",
)


ICONS = {'SEARCH': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>',
    'GEAR': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
    'PLAY': '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><path d="M7 4.5v15l13-7.5z"/></svg>',
    'PAUSE': '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4.5" height="14" rx="1"/><rect x="13.5" y="5" width="4.5" height="14" rx="1"/></svg>',
    'STOP': '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2.5"/></svg>',
    'CHECK': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    'CLOSE': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    'UP': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg>',
    'DOWN': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>',
    'CAMERA': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8.5a2 2 0 0 1 2-2h2.4l1.4-2h6.4l1.4 2H19a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="12.8" r="3.4"/></svg>',
    'IMAGES': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4.5" width="18" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.7"/><path d="M21 16.5l-5-5-8.5 8"/></svg>',
    'PREV': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>',
    'NEXT': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>'}

HTML = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=420, initial-scale=1, minimum-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="__CARD_BG__">
<title>LiedManager – Fernsteuerung</title>
<link rel="stylesheet" href="/app.css">
</head>
<body>

<main id="login" class="screen">
  <section class="card login-card">
    <h1>LiedManager</h1>
    <p class="muted">Fernsteuerung – bitte mit der PIN anmelden, die im Programm unter Einstellungen → Daten steht.</p>
    <input id="pin" type="password" autocomplete="current-password" placeholder="PIN" aria-label="PIN">
    <button id="loginBtn" class="primary" title="Anmelden">Anmelden</button>
    <p id="loginMsg" class="msg" role="alert"></p>
  </section>
</main>

<div id="app" class="screen" hidden>
  <header class="top">
    <div class="searchrow">
      <div class="field">
        <span class="field-icon">__ICON_SEARCH__</span>
        <input id="q" type="search" placeholder="Suche" autocomplete="off" aria-label="Lied suchen"
               title="Suche nach Liednummer (z. B. 12 oder p012), Titel oder Textstelle">
      </div>
      <button id="moreBtn" class="round" title="Mehr: Datenbank-Abgleich, Version, Abmelden" aria-label="Mehr">__ICON_GEAR__</button>
    </div>
    <nav id="tabs" class="tabs" aria-label="Bereiche">
      <button class="tab on" data-tab="song" title="Lied, Audio, Aufnahme und Pausentimer">Lied</button>
      <button class="tab" data-tab="camera" title="Live-Kameras und ATEM">__ICON_CAMERA__<span>Kamera</span></button>
      <button class="tab" data-tab="images" title="Bilder auf dem Beamer zeigen">__ICON_IMAGES__<span>Bilder</span><span id="imgBadge" class="badge" hidden>0</span></button>
      <button id="escBtn" class="tab esc" title="Wie Esc im Programm: schließt zuerst Beamer-Bild, dann Kamera-Vollbild, sonst Audio und Suche">Esc</button>
    </nav>
  </header>
  <div class="status">
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
          <button id="closeBeamerBtn" class="round" title="Schließt alles, was auf dem Beamer zu sehen ist" aria-label="Beamer schließen">__ICON_CLOSE__</button>
        </div>
      </div>

      <div id="audio" hidden>
        <div id="audioSelect" class="selectrow">
          <button id="a1" class="pill grow" hidden type="button">Piano</button>
          <button id="a2" class="pill grow" hidden type="button">GL3</button>
          <span id="noAudio" class="noaudio" hidden>Keine Audiodatei vorhanden</span>
        </div>
        <div id="player" class="panel" hidden>
          <button id="playBtn" class="round" title="Wiedergabe / Pause" aria-label="Wiedergabe oder Pause"><span class="i-play">__ICON_PLAY__</span><span class="i-pause">__ICON_PAUSE__</span></button>
          <div class="grow">
            <div id="trackName" class="track"></div>
            <input id="seek" type="range" min="0" max="100" step="0.1" value="0" title="Vor- und Zurückspulen" aria-label="Position">
          </div>
          <button id="stopBtn" class="icon" title="Wiedergabe beenden" aria-label="Wiedergabe beenden">__ICON_STOP__</button>
        </div>
      </div>

      <div id="recPanel" class="panel">
        <button id="recBtn" class="round" title="Aufnahme starten" aria-label="Aufnahme"><span id="recDot" class="recdot"></span></button>
        <div class="grow recmid">
          <input id="preacher" class="small" type="text" maxlength="80" placeholder="Prediger" aria-label="Prediger"
                 title="Name des Predigers – steht im Dateinamen der Aufnahme (Datum - Prediger)">
          <span id="recTime" class="rectime" title="Dauer der laufenden Aufnahme">00:00</span>
        </div>
        <button id="saveBtn" class="icon" title="Aufnahme speichern" aria-label="Aufnahme speichern" disabled>__ICON_CHECK__</button>
      </div>
    </div>

    <section id="pausePanel" class="pause">
      <div class="pauseHead">
        <button id="pauseTitle" class="ptitle" type="button" title="Klicken: Ansagen ein- oder ausklappen">Pausentimer</button>
        <input id="endTime" class="timeedit" type="time" aria-label="Endzeit der Pause" title="Endzeit der Pause (Uhrzeit ändern)">
        <button id="pauseBtn" class="round" title="Pausentimer starten" aria-label="Pausentimer starten oder beenden"><span class="i-play">__ICON_PLAY__</span><span class="i-pause">__ICON_STOP__</span></button>
        <button id="pauseChevron" class="chev" type="button" title="Ansagen ein- oder ausklappen" aria-label="Ansagen ein- oder ausklappen">__ICON_DOWN__</button>
      </div>
      <textarea id="lines" rows="10" cols="47" wrap="off" spellcheck="false" hidden placeholder="Ansagen" aria-label="Ansagen"
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
  </section>

  <section id="tab-images" class="tabpage" hidden>
    <div class="card">
      <div class="caption">Beamer-Galerie</div>
      <div id="galleryInfo" class="muted">Keine Bilder</div>
      <div class="row">
        <button id="prevBtn" class="pill" title="Vorheriges Bild">__ICON_PREV__<span>Zurück</span></button>
        <button id="nextBtn" class="pill" title="Nächstes Bild"><span>Weiter</span>__ICON_NEXT__</button>
        <button id="galleryCloseBtn" class="pill" title="Galerie auf dem Beamer schließen">Schließen</button>
      </div>
    </div>
    <div class="card">
      <div class="caption">Abgelegte Bilder – antippen zeigt auf dem Beamer</div>
      <div id="thumbs" class="thumbs"></div>
      <p id="noImages" class="muted">Noch keine Bilder. Lade welche vom Handy hoch.</p>
      <div class="row">
        <label class="pill filebtn" title="Bilder von diesem Gerät hinzufügen">Bilder hochladen
          <input id="upload" type="file" accept="image/*" multiple hidden>
        </label>
        <button id="clearBtn" class="pill" title="Alle abgelegten Bilder entfernen">Alle entfernen</button>
      </div>
    </div>
  </section>

  <section id="tab-more" class="tabpage" hidden>
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
<script src="/app.js"></script>
</body>
</html>
"""

CSS = """:root {
  --bg: __CARD_BG__; --surface: __SURFACE__; --surface-low: __SURFACE_LOW__;
  --hover-top: __SURFACE_HOVER_TOP__; --hover-bottom: __SURFACE_HOVER_BOTTOM__; --pressed: __SURFACE_PRESSED__;
  --border: __BORDER__; --track: __TRACK_BG__;
  --text: __TEXT_PRIMARY__; --text-2: __TEXT_SECONDARY__; --label: __TEXT_LABEL__; --muted: __TEXT_MUTED__;
  --accent: __ACCENT__; --accent-light: __ACCENT_LIGHT__; --accent-glow: __ACCENT_GLOW__; --accent-deep: __ACCENT_DEEP__;
  --accent-border: __ACCENT_BORDER__; --accent-tint: __ACCENT_TINT__; --pill-text: __PILL_TEXT__;
  --rec: __REC_RED__; --rec-bg: __REC_RUNNING_BG__; --rec-time: __REC_TIME_RUNNING__; --track-name: __TRACK_NAME_COLOR__;
  --radius: __RADIUS__px; --panel-radius: __PANEL_RADIUS__px; --fs: __FS__px; --fs-small: __FS_SMALL__px; --btn: __BTN__px;
  --serif: __SERIF__; --body: __BODY__;
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
  /* genau 47 Zeichen breit und 10 Zeilen hoch (Schrift mit fester Breite), ohne Bildlauf */
  width: calc(47ch + 26px); height: 218px; padding: 8px 12px; resize: none; overflow: hidden; white-space: pre; overflow-wrap: normal;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, "Courier New", monospace; font-size: 12px; line-height: 20px;
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
"""

JS = r"""(function () {
  'use strict';
  var TOKEN_KEY = 'lm_token';
  var RELAY = '__RELAY__';      // leer = Programm direkt; sonst Name des PHP-Skripts auf der Website
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
  function showApp() {
    $('login').hidden = true;
    $('app').hidden = false;
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
  function refresh() {
    return request('GET', '/api/state').then(function (s) {
      state = s;
      setConn(true);
      render(s);
    }).catch(function (err) {
      var offline = err.status === undefined || err.status === 503 || err.status === 504;
      if (offline && err.message !== 'Bitte anmelden.') { setConn(false); }
    });
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
  }

  var pauseOpen = false;
  var maxLines = 10, maxChars = 47;
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
  on('upload', 'change', function () {
    var files = Array.prototype.slice.call($('upload').files);
    $('upload').value = '';
    var done = 0, failed = 0;
    files.reduce(function (chain, file) {
      return chain.then(function () {
        return request('POST', '/api/upload?name=' + encodeURIComponent(file.name), undefined, file).then(function (r) {
          done += r.added || 0;
          failed += r.failed || 0;
        }).catch(function (err) { failed += 1; toast(err.message, true); });
      });
    }, Promise.resolve()).then(function () {
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
"""


LOGIN_HINT = "die im Programm unter Einstellungen → Daten steht"
LOGIN_HINT_HOSTED = "die du in der Datei remote.php festgelegt hast"


def build_assets(values: dict) -> dict:
    """Pfad -> (Inhaltstyp, Bytes) für ``server/remote.php``. ``values`` enthält die Einträge aus ``REQUIRED_VALUES``.

    Anfragen gehen an das Skript selbst, dessen Name als ``__SELF__`` stehen bleibt (remote.php setzt ihn beim
    Ausliefern ein).
    """
    missing = [name for name in REQUIRED_VALUES if name not in values]
    if missing:
        raise KeyError(f"Design-Werte fehlen: {', '.join(missing)}")

    def fill(template: str) -> str:
        for name, svg in ICONS.items():
            template = template.replace(f"__ICON_{name}__", svg)
        for name in REQUIRED_VALUES:
            template = template.replace(f"__{name}__", str(values[name]))
        return template

    html, css, js = fill(HTML), fill(CSS), JS.replace("__RELAY__", "__SELF__")
    for old, new in (('href="/app.css"', 'href="__SELF__?asset=css"'), ('src="/app.js"', 'src="__SELF__?asset=js"'),
                     (LOGIN_HINT, LOGIN_HINT_HOSTED)):
        if old not in html:
            raise ValueError(f"Die Webseite hat sich geändert, ‚{old}‘ fehlt: build_assets anpassen.")
        html = html.replace(old, new)
    return {
        "/": ("text/html; charset=utf-8", html.encode("utf-8")),
        "/app.css": ("text/css; charset=utf-8", css.encode("utf-8")),
        "/app.js": ("application/javascript; charset=utf-8", js.encode("utf-8")),
    }
