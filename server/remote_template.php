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
    return $db;
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

function app_alive(PDO $db): bool {
    $alive = (int)$db->query('SELECT alive FROM lm_rm_meta WHERE id = 1')->fetchColumn();
    return $alive > 0 && time() - $alive <= APP_TIMEOUT;
}

function touch_alive(PDO $db): void {
    $q = $db->prepare('UPDATE lm_rm_meta SET alive = ? WHERE id = 1');
    $q->execute([time()]);
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
    $db->prepare('INSERT INTO lm_rm_jobs (created, kind, name, body) VALUES (?, ?, ?, ?)')
        ->execute([$now, $kind, $name, $body]);
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

    if ($api === 'state' && $method === 'GET') {
        $row = $db->query('SELECT alive, state FROM lm_rm_meta WHERE id = 1')->fetch(PDO::FETCH_ASSOC);
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
        run_job($db, 'upload', $name, base64_encode($data), UPLOAD_WAIT);
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
    $action = (string)($in['action'] ?? '');

    if ($action === 'poll') {
        touch_alive($db);
        $db->prepare('DELETE FROM lm_rm_jobs WHERE created < ?')->execute([time() - 300]);
        $hold = max(0, min(HOLD, (int)($in['hold'] ?? HOLD)));
        $deadline = microtime(true) + $hold;
        $select = $db->prepare('SELECT id, kind, name, body FROM lm_rm_jobs WHERE status = 0 ORDER BY id LIMIT 5');
        $claim = $db->prepare('UPDATE lm_rm_jobs SET status = 1 WHERE id = ? AND status = 0');
        $lastTouch = time();
        while (true) {
            $select->execute();
            $jobs = [];
            foreach ($select->fetchAll(PDO::FETCH_ASSOC) as $job) {
                $claim->execute([(int)$job['id']]);
                if ($claim->rowCount() === 1) {          // nur wer den Auftrag wirklich bekommen hat, führt ihn aus
                    $jobs[] = ['id' => (int)$job['id'], 'kind' => $job['kind'], 'name' => $job['name'],
                        'body' => $job['body'] === null ? '' : (string)$job['body']];
                }
            }
            if ($jobs || microtime(true) >= $deadline) {
                json_out(['format' => FORMAT, 'jobs' => $jobs]);
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
        $db->prepare('UPDATE lm_rm_meta SET alive = ?, state = ? WHERE id = 1')->execute([time(), $data]);
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

    if ($action === 'bye') {
        $db->exec('UPDATE lm_rm_meta SET alive = 0 WHERE id = 1');
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
