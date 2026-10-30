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
