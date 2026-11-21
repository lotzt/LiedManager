<?php
/*
 * LiedManager – Website-Steuerung (All-Inkl: PHP + MySQL)
 *
 * Diese Datei wird aus remote_template.php erzeugt (python tools/build_remote_site.py) und enthält die Webseite
 * der Fernsteuerung gleich mit. NICHT von Hand die Seite ändern – Zugangsdaten gehören in liedmanager-zugang.php.
 *
 * Einrichtung: siehe README.md, Abschnitt „Web-Steuerung über die eigene Website“.
 *   1. KAS -> Datenbanken: MySQL-Datenbank anlegen (es darf dieselbe wie für sync.php sein, die Tabellen heißen anders).
 *   2. TOKEN (langes Zufallspasswort, kommt auch in die Einstellungen von LiedManager), PIN (Passwort für den
 *      Browser, mindestens 8 Zeichen) und die Datenbank-Zugangsdaten in liedmanager-zugang.php eintragen (Vorlage:
 *      liedmanager-zugang.beispiel.php) und diese Datei neben remote.php oder einen Ordner darüber legen.
 *   3. Datei per WebFTP in einen Ordner der Domain legen, z. B. https://deine-domain.de/steuerung/remote.php
 *      (die Domain braucht SSL). Zum Prüfen:  https://deine-domain.de/steuerung/remote.php?check
 *
 * So funktioniert es: LiedManager ruft diese Seite von sich aus an („poll“), schickt den Zustand und holt Aufträge
 * ab. Der Browser meldet sich hier mit der PIN an; seine Befehle werden zu Aufträgen für das Programm, das Ergebnis
 * geht zurück an den Browser. Das Programm muss dafür laufen und online sein.
 */

// Zugangsdaten: am besten in der gemeinsamen Datei „liedmanager-zugang.php“ (Vorlage: liedmanager-zugang.beispiel.php)
// – im selben Ordner oder einen Ordner darüber, dann gilt sie für remote.php und sync.php zugleich. Diese Datei
// kann bei Updates einfach ersetzt werden. (Ältere Einrichtung: remote-zugang.php im selben Ordner geht weiterhin.)
foreach ([__DIR__ . '/remote-zugang.php', __DIR__ . '/liedmanager-zugang.php', dirname(__DIR__) . '/liedmanager-zugang.php'] as $zugang) {
    if (is_file($zugang)) {
        require $zugang;
        break;
    }
}
defined('TOKEN')   || define('TOKEN',   'HIER-LANGES-ZUFAELLIGES-TOKEN');
defined('PIN')     || define('PIN',     'HIER-PASSWORT-FUER-DEN-BROWSER');
defined('DB_HOST') || define('DB_HOST', 'localhost');
defined('DB_NAME') || define('DB_NAME', 'dXXXXXXX');
defined('DB_USER') || define('DB_USER', 'dXXXXXXX');
defined('DB_PASS') || define('DB_PASS', 'HIER-DB-PASSWORT');

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
const SEARCH_MAX     = 60;         // höchstens so viele Treffer (wie im Programm)
const UPLOAD_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'];

@ini_set('memory_limit', '256M');
@ini_set('display_errors', '0');
@set_time_limit(60);

const PAGE_HTML = <<<'LM_PAGE_HTML'
__PAGE_HTML__
LM_PAGE_HTML;

const PAGE_CSS = <<<'LM_PAGE_CSS'
__PAGE_CSS__
LM_PAGE_CSS;

const PAGE_JS = <<<'LM_PAGE_JS'
__PAGE_JS__
LM_PAGE_JS;

const PAGE_MANIFEST = <<<'LM_PAGE_MANIFEST'
__PAGE_MANIFEST__
LM_PAGE_MANIFEST;

// Logo (PNG, Base64) für Browser-Tab, Lesezeichen und „Zum Home-Bildschirm“
const PAGE_ICONS = [
    'favicon' => '__ICON_FAVICON__',
    'icon180' => '__ICON_180__',
    'icon192' => '__ICON_192__',
    'icon512' => '__ICON_512__',
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
    try {
        $db->query('SELECT 1 FROM lm_rm_pause LIMIT 1');
    } catch (PDOException $e) {
        create_pause($db);                  // Update: Ansagen vormerken
    }
    try {
        $db->query('SELECT 1 FROM lm_rm_plan LIMIT 1');
    } catch (PDOException $e) {
        create_plan($db);                   // Update: Lieder vormerken
    }
    try {
        $db->query('SELECT 1 FROM lm_rm_songs_ver LIMIT 1');
    } catch (PDOException $e) {
        create_songs($db);                  // Update: Liedsuche ohne laufendes Programm
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

/** Ansagen, die bearbeitet wurden, während das Programm nicht lief (je Computer die letzte Fassung). */
function create_pause(PDO $db): void {
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_pause (
        dev     VARCHAR(40) NOT NULL PRIMARY KEY,
        created INT NOT NULL,
        body    MEDIUMTEXT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
}

/** Vorgemerkte Lieder (Liednummern), bearbeitet während das Programm nicht lief (je Computer die letzte Fassung). */
function create_plan(PDO $db): void {
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_plan (
        dev     VARCHAR(40) NOT NULL PRIMARY KEY,
        created INT NOT NULL,
        body    MEDIUMTEXT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
}

/** Liederliste für die Suche auf der Website, solange das Programm aus ist (je Computer; nur Nummer, Titel, Text). */
function create_songs(PDO $db): void {
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_songs (
        dev     VARCHAR(40) NOT NULL,
        gen     CHAR(40) NOT NULL,
        pos     INT NOT NULL,
        k       VARCHAR(60) NOT NULL,
        nummer  VARCHAR(60) NOT NULL,
        titel   VARCHAR(300) NOT NULL,
        alias   VARCHAR(60) NOT NULL,
        nt      VARCHAR(300) NOT NULL,
        nl      MEDIUMTEXT NOT NULL,
        PRIMARY KEY (dev, gen, pos)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_songs_ver (
        dev     VARCHAR(40) NOT NULL PRIMARY KEY,
        gen     CHAR(40) NOT NULL,
        updated INT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
}

function plan_pending(PDO $db): bool {
    $q = $db->prepare('SELECT 1 FROM lm_rm_plan WHERE dev = ?');
    $q->execute([cur_dev()]);
    return (bool)$q->fetchColumn();
}

function pause_pending(PDO $db): bool {
    $q = $db->prepare('SELECT 1 FROM lm_rm_pause WHERE dev = ?');
    $q->execute([cur_dev()]);
    return (bool)$q->fetchColumn();
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
    // `system` in Backticks: ab MySQL 8 ist „system“ ein reserviertes Wort
    $db->exec('CREATE TABLE IF NOT EXISTS lm_rm_reports (
        id      BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        created INT NOT NULL,
        fp      CHAR(16) NOT NULL,
        version VARCHAR(40) NOT NULL,
        `system` VARCHAR(80) NOT NULL,
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
        $db->prepare('INSERT INTO lm_rm_reports (created, fp, version, `system`, title, detail) VALUES (?, ?, ?, ?, ?, ?)')
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
            $db->prepare('UPDATE IGNORE lm_rm_pause SET dev = ? WHERE dev = ?')->execute([cur_dev(), $old]);
            $db->prepare('UPDATE IGNORE lm_rm_plan SET dev = ? WHERE dev = ?')->execute([cur_dev(), $old]);
            songs_move($db, $old);
            $db->prepare('DELETE FROM lm_rm_jobs WHERE dev = ?')->execute([$old]);
            $db->prepare('DELETE FROM lm_rm_devices WHERE name = ?')->execute([$old]);
        }
    }
    $db->prepare('DELETE FROM lm_rm_devices WHERE did = "" AND alive < ?')->execute([time() - 300]);
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

/** Liederliste vom Programm in Stücken annehmen; erst wenn sie vollständig ist, gilt sie (die alte bleibt bis dahin). */
function songs_put(PDO $db, array $in): void {
    $gen = (string)($in['hash'] ?? '');
    $start = (int)($in['start'] ?? -1);
    $total = (int)($in['total'] ?? -1);
    $songs = $in['songs'] ?? null;
    if (!preg_match('/^[0-9a-f]{40}$/', $gen) || $start < 0 || $total < 1 || $total > 100000 || !is_array($songs)
        || $start + count($songs) > $total) {
        fail(400, 'Ungültige Liederliste.');
    }
    if ($start === 0) {
        $db->prepare('DELETE FROM lm_rm_songs WHERE dev = ? AND gen = ?')->execute([cur_dev(), $gen]);
    }
    $insert = $db->prepare('REPLACE INTO lm_rm_songs (dev, gen, pos, k, nummer, titel, alias, nt, nl) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)');
    $db->beginTransaction();
    foreach (array_values($songs) as $i => $row) {
        if (!is_array($row) || count($row) < 6) {
            $db->rollBack();
            fail(400, 'Ungültiges Lied in der Liederliste.');
        }
        $insert->execute([cur_dev(), $gen, $start + $i, lm_cut($row[0], 60), lm_cut($row[1], 60), lm_cut($row[2], 300),
            lm_cut($row[3], 60), lm_cut($row[4], 300), lm_cut($row[5], 4000000)]);
    }
    $db->commit();
    if ($start + count($songs) === $total) {
        $q = $db->prepare('SELECT COUNT(*) FROM lm_rm_songs WHERE dev = ? AND gen = ?');
        $q->execute([cur_dev(), $gen]);
        if ((int)$q->fetchColumn() === $total) {
            $db->prepare('REPLACE INTO lm_rm_songs_ver (dev, gen, updated) VALUES (?, ?, ?)')->execute([cur_dev(), $gen, time()]);
            $db->prepare('DELETE FROM lm_rm_songs WHERE dev = ? AND gen <> ?')->execute([cur_dev(), $gen]);
        }
    }
    json_out(['ok' => true]);
}

function lm_cut($value, int $length): string {
    $text = is_scalar($value) ? (string)$value : '';
    return function_exists('mb_substr') ? mb_substr($text, 0, $length, 'UTF-8') : substr($text, 0, $length);
}

function lm_lower(string $text): string {
    return function_exists('mb_strtolower') ? mb_strtolower($text, 'UTF-8') : strtolower($text);
}

/** Wie normalize() im Programm: Kleinschreibung, ohne Satzzeichen, Leerraum zusammengefasst. */
function lm_norm(string $text): string {
    $text = (string)preg_replace('/[^\p{L}\p{N}_\s]+/u', '', lm_lower($text));
    return trim((string)preg_replace('/\s+/u', ' ', $text));
}

/** Ähnlichkeit 0…1 (0, sobald sie unter 80 % liegt) – wie die unscharfe Suche im Programm. */
function lm_similar(string $candidate, string $query): float {
    $sum = strlen($candidate) + strlen($query);
    if ($sum === 0 || 2 * min(strlen($candidate), strlen($query)) / $sum < 0.8) {
        return 0.0;
    }
    similar_text($candidate, $query, $percent);
    return $percent >= 80 ? $percent / 100 : 0.0;
}

/**
 * Liedsuche ohne laufendes Programm – dieselbe Reihenfolge wie im Programm (database.py, search_songs):
 * Buchstabe → alle Nummern damit; Nummer (12, p012) → das Lied (Verweise aufgelöst); sonst Titel/Text, sonst unscharf.
 */
function offline_search(PDO $db, string $raw): array {
    $q = $db->prepare('SELECT dev, gen FROM lm_rm_songs_ver ORDER BY dev = ? DESC, updated DESC LIMIT 1');
    $q->execute([cur_dev()]);
    $ver = $q->fetch(PDO::FETCH_ASSOC);
    if (!$ver) {
        fail(503, 'Das Programm läuft nicht, und auf der Website liegt noch keine Liederliste. Sie wird übertragen, '
            . 'sobald LiedManager einmal mit der Website verbunden war.');
    }
    $reply = function (array $rows): array {
        $songs = [];
        foreach (array_slice($rows, 0, SEARCH_MAX) as $row) {
            $songs[] = ['rowid' => 0, 'nummer' => $row['nummer'], 'titel' => $row['titel']];
        }
        return ['songs' => $songs, 'more' => count($rows) > SEARCH_MAX, 'offline' => true];
    };
    $query = trim(lm_lower($raw));
    if ($query === '') {
        return $reply([]);
    }
    $light = $db->prepare('SELECT k, nummer, titel, alias FROM lm_rm_songs WHERE dev = ? AND gen = ? ORDER BY pos');

    if (preg_match('/^[a-z]$/', $query)) {
        $light->execute([$ver['dev'], $ver['gen']]);
        $hits = [];
        foreach ($light->fetchAll(PDO::FETCH_ASSOC) as $row) {
            $key = (string)$row['k'];
            if ($row['alias'] !== '' || strlen($key) < 2 || $key[0] !== $query || !ctype_digit($key[1])) {
                continue;
            }
            preg_match('/^\d+/', substr($key, 1), $digits);
            $hits[] = [(int)$digits[0], $key, count($hits), $row];
        }
        usort($hits, function ($a, $b) { return [$a[0], $a[1], $a[2]] <=> [$b[0], $b[1], $b[2]]; });
        return $reply(array_column($hits, 3));
    }

    if (preg_match('/^([a-z])?(\d{1,3})$/', $query, $m)) {
        $light->execute([$ver['dev'], $ver['gen']]);
        $rows = $light->fetchAll(PDO::FETCH_ASSOC);
        $byKey = [];
        foreach ($rows as $row) {
            if (!isset($byKey[$row['k']])) {
                $byKey[$row['k']] = $row;
            }
        }
        $prefix = $m[1] !== '' ? $m[1] : 'p';
        $number = (int)$m[2];
        $song = null;
        if ($m[1] === '') {
            // Ohne Buchstabe zuerst die reine Nummer ansehen: Ist sie ein Verweis (z. B. 512 -> p102), gilt das Ziel.
            $plain = $byKey[sprintf('%03d', $number)] ?? $byKey[(string)$number] ?? null;
            if ($plain !== null && $plain['alias'] !== '' && isset($byKey[$plain['alias']])) {
                $song = $byKey[$plain['alias']];
            }
        }
        if ($song === null) {
            $song = $byKey[$prefix . sprintf('%03d', $number)] ?? $byKey[$prefix . $number] ?? null;
        }
        if ($song === null) {
            foreach ($rows as $row) {
                if (preg_match('/^\s*[+-]?\d+/', (string)$row['nummer'], $lead) && (int)$lead[0] === $number) {
                    $song = $row;
                    break;
                }
            }
        }
        if ($song !== null) {
            if ($song['alias'] !== '' && isset($byKey[$song['alias']])) {
                $song = $byKey[$song['alias']];
            }
            return $reply([$song]);
        }
    }

    $norm = lm_norm($raw);
    if ($norm === '') {
        return $reply([]);
    }
    // Titel/Text: die Datenbank sucht grob vor (ohne Groß/Klein), hier wird genau geprüft und sortiert
    $like = '%' . addcslashes($norm, '%_\\') . '%';
    $q = $db->prepare("SELECT k, nummer, titel, alias, nt, nl FROM lm_rm_songs WHERE dev = ? AND gen = ? AND alias = ''
        AND (nt LIKE ? OR REPLACE(nl, CHAR(10 USING utf8mb4), ' ') LIKE ?) ORDER BY pos");
    $q->execute([$ver['dev'], $ver['gen'], $like, $like]);
    $padded = ' ' . $norm . ' ';
    $hits = [];
    foreach ($q->fetchAll(PDO::FETCH_ASSOC) as $row) {
        $title = (string)$row['nt'];
        $text = str_replace("\n", ' ', (string)$row['nl']);
        if (strpos($title, $norm) === false && strpos($text, $norm) === false) {
            continue;
        }
        if ($title === $norm) {
            $rank = 0;
        } elseif (strpos($title, $norm) === 0) {
            $rank = 1;
        } elseif (strpos(' ' . $title . ' ', $padded) !== false) {
            $rank = 2;
        } elseif (strpos($title, $norm) !== false) {
            $rank = 3;
        } elseif (in_array($norm, explode("\n", (string)$row['nl']), true)) {
            $rank = 4;
        } elseif (strpos(' ' . $text . ' ', $padded) !== false) {
            $rank = 5;
        } else {
            $rank = 6;
        }
        $hits[] = [$rank, count($hits), $row];
    }
    if ($hits) {
        usort($hits, function ($a, $b) { return [$a[0], $a[1]] <=> [$b[0], $b[1]]; });
        return $reply(array_column($hits, 2));
    }

    // unscharf: Textzeilen (oder Stücke davon) mit mindestens 80 % Übereinstimmung
    $words = count(explode(' ', $norm));
    $deadline = microtime(true) + 1.5;
    $q = $db->prepare("SELECT k, nummer, titel, alias, nl FROM lm_rm_songs WHERE dev = ? AND gen = ? AND alias = '' ORDER BY pos");
    $q->execute([$ver['dev'], $ver['gen']]);
    $found = [];
    foreach ($q->fetchAll(PDO::FETCH_ASSOC) as $row) {
        if (microtime(true) > $deadline) {
            break;
        }
        $best = 0.0;
        foreach (explode("\n", (string)$row['nl']) as $line) {
            $parts = $line === '' ? [] : explode(' ', $line);
            if (count($parts) <= $words) {
                $best = max($best, lm_similar($line, $norm));
            } else {
                for ($i = 0; $i + $words <= count($parts); $i++) {
                    $best = max($best, lm_similar(implode(' ', array_slice($parts, $i, $words)), $norm));
                }
            }
            if ($best >= 1.0) {
                break;
            }
        }
        if ($best > 0) {
            $found[] = [-$best, count($found), $row];
        }
    }
    usort($found, function ($a, $b) { return [$a[0], $a[1]] <=> [$b[0], $b[1]]; });
    return $reply(array_column($found, 2));
}

/** Nummer → Lied (wie die Nummernsuche im Programm, Verweise aufgelöst); null, wenn es keine solche Nummer gibt. */
function plan_titles(PDO $db, array $numbers): array {
    $q = $db->prepare('SELECT dev, gen FROM lm_rm_songs_ver ORDER BY dev = ? DESC, updated DESC LIMIT 1');
    $q->execute([cur_dev()]);
    $ver = $q->fetch(PDO::FETCH_ASSOC);
    if (!$ver) {
        return ['index' => false, 'titles' => []];
    }
    $q = $db->prepare('SELECT k, nummer, titel, alias FROM lm_rm_songs WHERE dev = ? AND gen = ? ORDER BY pos');
    $q->execute([$ver['dev'], $ver['gen']]);
    $rows = $q->fetchAll(PDO::FETCH_ASSOC);
    $byKey = [];
    foreach ($rows as $row) {
        if (!isset($byKey[$row['k']])) {
            $byKey[$row['k']] = $row;
        }
    }
    $titles = [];
    foreach ($numbers as $raw) {
        $key = (string)preg_replace('/\s+/u', '', lm_lower(trim($raw)));
        $song = $key !== '' ? ($byKey[$key] ?? null) : null;
        if ($song === null && preg_match('/^([a-z])?(\d{1,3})$/', $key, $m)) {
            $prefix = $m[1] !== '' ? $m[1] : 'p';
            $song = $byKey[$prefix . sprintf('%03d', (int)$m[2])] ?? $byKey[$prefix . (int)$m[2]] ?? null;
            if ($song === null) {
                foreach ($rows as $row) {
                    if (preg_match('/^\s*[+-]?\d+/', (string)$row['nummer'], $lead) && (int)$lead[0] === (int)$m[2]) {
                        $song = $row;
                        break;
                    }
                }
            }
        }
        if ($song !== null && $song['alias'] !== '' && isset($byKey[$song['alias']])) {
            $song = $byKey[$song['alias']];
        }
        $titles[] = $song === null ? null : ['nummer' => (string)$song['nummer'], 'titel' => (string)$song['titel']];
    }
    return ['index' => true, 'titles' => $titles];
}

/** Liederliste eines umbenannten Computers übernehmen (nur wenn der neue Name noch keine hat). */
function songs_move(PDO $db, string $old): void {
    $q = $db->prepare('SELECT 1 FROM lm_rm_songs_ver WHERE dev = ?');
    $q->execute([cur_dev()]);
    if ($q->fetchColumn()) {
        $db->prepare('DELETE FROM lm_rm_songs WHERE dev = ?')->execute([$old]);
        $db->prepare('DELETE FROM lm_rm_songs_ver WHERE dev = ?')->execute([$old]);
        return;
    }
    $db->prepare('UPDATE lm_rm_songs SET dev = ? WHERE dev = ?')->execute([cur_dev(), $old]);
    $db->prepare('UPDATE lm_rm_songs_ver SET dev = ? WHERE dev = ?')->execute([cur_dev(), $old]);
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
            queue_upload($db, $name, $data);      // Programm läuft nicht: vormerken, beim nächsten Start abgeholt
        }
        run_job($db, 'upload', $name, base64_encode($data), UPLOAD_WAIT);
    }

    if ($api === 'inbox' && $method === 'GET') {
        // vorgemerkte Bilder (Programm war aus): Anzahl und Liste für die Vorschau auf der Website
        $q = $db->prepare('SELECT id, name FROM lm_rm_inbox WHERE dev = ? ORDER BY id');
        $q->execute([cur_dev()]);
        $items = array_map(function ($row) { return ['id' => (int)$row['id'], 'name' => (string)$row['name']]; },
            $q->fetchAll(PDO::FETCH_ASSOC));
        json_out(['pending' => count($items), 'items' => $items]);
    }
    if (strpos($api, 'inbox_img/') === 0 && $method === 'GET') {
        $id = substr($api, 10);
        if (!ctype_digit($id) || strlen($id) > 18) {
            fail(400, 'Ungültige Anfrage.');
        }
        $q = $db->prepare('SELECT name, body FROM lm_rm_inbox WHERE id = ? AND dev = ?');
        $q->execute([(int)$id, cur_dev()]);
        $row = $q->fetch(PDO::FETCH_ASSOC);
        if (!$row) {
            fail(404, 'Das Bild ist nicht mehr vorgemerkt.');
        }
        $types = ['.png' => 'image/png', '.jpg' => 'image/jpeg', '.jpeg' => 'image/jpeg', '.gif' => 'image/gif',
            '.bmp' => 'image/bmp', '.webp' => 'image/webp'];
        $type = 'application/octet-stream';
        foreach ($types as $extension => $mime) {
            if (substr(strtolower((string)$row['name']), -strlen($extension)) === $extension) {
                $type = $mime;
            }
        }
        send(200, (string)$row['body'], $type, ['Cache-Control' => 'private, max-age=3600']);
    }
    if ($api === 'inbox_remove' && $method === 'POST') {
        $args = json_decode(read_body(MAX_JSON), true);
        $db->prepare('DELETE FROM lm_rm_inbox WHERE id = ? AND dev = ?')
            ->execute([(int)(is_array($args) ? ($args['id'] ?? 0) : 0), cur_dev()]);
        json_out(['pending' => inbox_pending($db)]);
    }
    if ($api === 'pause' && $method === 'GET') {
        // Für die Bearbeitung ohne laufendes Programm: vorgemerkte Ansagen, sonst die zuletzt gemeldeten
        $q = $db->prepare('SELECT body FROM lm_rm_pause WHERE dev = ?');
        $q->execute([cur_dev()]);
        $pending = $q->fetchColumn();
        $q = $db->prepare('SELECT state FROM lm_rm_devices WHERE name = ?');
        $q->execute([cur_dev()]);
        $state = json_decode((string)$q->fetchColumn(), true);
        $last = is_array($state) && is_array($state['pause'] ?? null) ? $state['pause'] : null;
        json_out(['pending' => $pending === false ? null : json_decode((string)$pending, true), 'last' => $last]);
    }
    if ($api === 'plan' && $method === 'GET') {
        // Vorgemerkte Lieder ohne laufendes Programm: vorgemerkte Fassung, sonst die zuletzt gemeldete
        $q = $db->prepare('SELECT body FROM lm_rm_plan WHERE dev = ?');
        $q->execute([cur_dev()]);
        $pending = $q->fetchColumn();
        $q = $db->prepare('SELECT state FROM lm_rm_devices WHERE name = ?');
        $q->execute([cur_dev()]);
        $state = json_decode((string)$q->fetchColumn(), true);
        $last = is_array($state) && is_array($state['plan'] ?? null) ? $state['plan'] : null;
        json_out(['pending' => $pending === false ? null : json_decode((string)$pending, true), 'last' => $last]);
    }
    if ($api === 'plan_set' && $method === 'POST' && !app_alive($db)) {
        // Programm läuft nicht: Liste vormerken, beim nächsten Start übernimmt das Programm sie
        $raw = read_body(MAX_JSON);
        $args = json_decode($raw, true);
        if (!is_array($args) || !is_array($args['songs'] ?? null)) {
            fail(400, 'Ungültige Liederliste.');
        }
        $db->prepare('REPLACE INTO lm_rm_plan (dev, created, body) VALUES (?, ?, ?)')->execute([cur_dev(), time(), $raw]);
        json_out(['ok' => true, 'queued' => true], 202);
    }
    if ($api === 'pause_set' && $method === 'POST' && !app_alive($db)) {
        // Programm läuft nicht: Ansagen vormerken, beim nächsten Start übernimmt das Programm sie
        $raw = read_body(MAX_JSON);
        $args = json_decode($raw, true);
        if (!is_array($args) || !is_array($args['lines'] ?? null)) {
            fail(400, 'Ungültige Ansagen.');
        }
        // nur die Ansagen – die Endzeit gilt für die laufende Pause und wird nicht vorgemerkt
        $raw = json_encode(['lines' => array_values(array_map('strval', array_filter($args['lines'], 'is_scalar')))],
            JSON_UNESCAPED_UNICODE);
        $db->prepare('REPLACE INTO lm_rm_pause (dev, created, body) VALUES (?, ?, ?)')->execute([cur_dev(), time(), $raw]);
        json_out(['ok' => true, 'queued' => true], 202);
    }
    if ($api === 'plan_titles' && $method === 'POST') {
        // Titel zu den vorgemerkten Nummern – aus der Liederliste, die das Programm hochgeladen hat
        $args = json_decode(read_body(MAX_JSON), true);
        $songs = is_array($args) && is_array($args['songs'] ?? null) ? array_slice($args['songs'], 0, 100) : [];
        json_out(plan_titles($db, array_map(function ($v) { return is_scalar($v) ? (string)$v : ''; }, $songs)));
    }
    if ($api === 'search' && $method === 'POST' && !app_alive($db)) {
        // Programm läuft nicht: in der zuletzt übertragenen Liederliste suchen (wie die Suche im Programm)
        $args = json_decode(read_body(MAX_JSON), true);
        json_out(offline_search($db, substr((string)(is_array($args) ? ($args['text'] ?? '') : ''), 0, 100)));
    }
    if ($api === 'reports' && $method === 'GET') {
        $rows = $db->query('SELECT id, created, version, `system`, title, detail, n FROM lm_rm_reports ORDER BY id DESC LIMIT 30')
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
        $pausePending = pause_pending($db);          // vorgemerkte Ansagen: ebenso
        $planPending = plan_pending($db);            // vorgemerkte Lieder: ebenso
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
            if ($jobs || $pending > 0 || $pausePending || $planPending || microtime(true) >= $deadline) {
                json_out(['format' => FORMAT, 'jobs' => $jobs, 'inbox' => $pending, 'pause' => $pausePending,
                    'plan' => $planPending]);
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

    if ($action === 'songs_hash') {
        $q = $db->prepare('SELECT gen FROM lm_rm_songs_ver WHERE dev = ?');
        $q->execute([cur_dev()]);
        json_out(['hash' => (string)$q->fetchColumn()]);
    }

    if ($action === 'songs_put') {
        songs_put($db, $in);
    }

    if ($action === 'plan_get') {
        $q = $db->prepare('SELECT created, body FROM lm_rm_plan WHERE dev = ?');
        $q->execute([cur_dev()]);
        $row = $q->fetch(PDO::FETCH_ASSOC);
        json_out(['item' => $row ? ['created' => (int)$row['created'], 'body' => (string)$row['body']] : null]);
    }

    if ($action === 'plan_done') {
        $db->prepare('DELETE FROM lm_rm_plan WHERE dev = ? AND created = ?')->execute([cur_dev(), (int)($in['created'] ?? 0)]);
        json_out(['ok' => true]);
    }

    if ($action === 'pause_get') {
        $q = $db->prepare('SELECT created, body FROM lm_rm_pause WHERE dev = ?');
        $q->execute([cur_dev()]);
        $row = $q->fetch(PDO::FETCH_ASSOC);
        json_out(['item' => $row ? ['created' => (int)$row['created'], 'body' => (string)$row['body']] : null]);
    }

    if ($action === 'pause_done') {
        // nur genau diese Fassung löschen: wurde inzwischen neu vorgemerkt, bleibt die neue stehen
        $db->prepare('DELETE FROM lm_rm_pause WHERE dev = ? AND created = ?')->execute([cur_dev(), (int)($in['created'] ?? 0)]);
        json_out(['ok' => true]);
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
            $db->prepare('UPDATE IGNORE lm_rm_pause SET dev = ? WHERE dev = ?')->execute([cur_dev(), $old]);
            $db->prepare('UPDATE IGNORE lm_rm_plan SET dev = ? WHERE dev = ?')->execute([cur_dev(), $old]);
            songs_move($db, $old);
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
    $lines[] = 'Zugangsdatei: ' . (is_file(__DIR__ . '/remote-zugang.php') ? 'remote-zugang.php' : (is_file(__DIR__ . '/liedmanager-zugang.php') ? 'liedmanager-zugang.php' : (is_file(dirname(__DIR__) . '/liedmanager-zugang.php') ? 'liedmanager-zugang.php (Ordner darüber)' : 'fehlt (Daten stehen dann in remote.php selbst)')));
    $lines[] = 'Zugangsdaten eingetragen (TOKEN, PIN, Datenbank): ' . ($problems ? 'NEIN – in liedmanager-zugang.php eintragen' : 'OK');
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
        fail(503, 'Noch nicht eingerichtet: ' . implode('; ', config_problems()) . '. Bitte in liedmanager-zugang.php eintragen und hochladen.');
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
