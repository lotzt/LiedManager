<?php
/*
 * LiedManager – Sync-Server (All-Inkl: PHP + MySQL)
 *
 * Einrichtung: siehe README.md, Abschnitt „Datenbank auf mehreren Geräten abgleichen“.
 *   1. KAS -> Datenbanken: neue MySQL-Datenbank anlegen, Name/Benutzer/Passwort unten eintragen.
 *   2. Ein langes zufälliges TOKEN erfinden und unten eintragen (dasselbe Token kommt in jedes LiedManager).
 *   3. Diese Datei per WebFTP in einen Ordner der Domain legen, z. B.  https://deine-domain.de/sync/sync.php
 *
 * Der Server speichert pro Lied eine Zeile. Jedes Lied wird einzeln übertragen, damit große Audios/Bilder
 * die PHP-Grenzen (post_max_size, memory_limit) nicht sprengen. Bei Streit um dasselbe Lied gewinnt die
 * jüngere Änderung (gleiche Zeit: größere Geräte-Kennung) – genau wie im Programm.
 */

const TOKEN   = 'HIER-LANGES-ZUFAELLIGES-TOKEN';
const DB_HOST = 'localhost';
const DB_NAME = 'dXXXXXXX';
const DB_USER = 'dXXXXXXX';
const DB_PASS = 'HIER-DB-PASSWORT';

const FORMAT     = 1;      // Protokollversion (Programm und Server müssen zusammenpassen)
const LIST_LIMIT = 2000;   // Einträge pro „list“-Antwort

@ini_set('memory_limit', '512M');
@ini_set('display_errors', '0');
header('Content-Type: application/json; charset=utf-8');

function reply(array $data, int $code = 200): void {
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(405);
    exit;
}

$raw = file_get_contents('php://input');
if ($raw === false || $raw === '') {
    reply(['error' => 'Leere Anfrage – vermutlich ist sie größer als post_max_size.'], 400);
}
$in = json_decode($raw, true);
unset($raw);
if (!is_array($in)) {
    reply(['error' => 'Ungültige Anfrage.'], 400);
}
if (!hash_equals(TOKEN, (string)($in['token'] ?? ''))) {
    http_response_code(401);
    exit;
}

try {
    $db = new PDO('mysql:host=' . DB_HOST . ';dbname=' . DB_NAME . ';charset=utf8mb4', DB_USER, DB_PASS, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    $db->exec('CREATE TABLE IF NOT EXISTS lm_songs (
        k       VARCHAR(190) NOT NULL PRIMARY KEY,
        ts      BIGINT NOT NULL,
        dev     VARCHAR(32) NOT NULL,
        hash    VARCHAR(64) NOT NULL DEFAULT "",
        deleted TINYINT NOT NULL DEFAULT 0,
        seq     BIGINT NOT NULL,
        data    LONGBLOB NULL,
        INDEX idx_seq (seq)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin');
    $db->exec('CREATE TABLE IF NOT EXISTS lm_counter (id TINYINT NOT NULL PRIMARY KEY, v BIGINT NOT NULL)');
    $db->exec('INSERT IGNORE INTO lm_counter (id, v) VALUES (1, 0)');

    $action = (string)($in['action'] ?? '');

    if ($action === 'list') {
        // Metadaten (ohne Daten) aller Lieder, die seit „since“ geändert wurden – in Reihenfolge der Änderung.
        $since = (int)($in['since'] ?? 0);
        $max = (int)$db->query('SELECT v FROM lm_counter WHERE id = 1')->fetchColumn();
        $q = $db->prepare('SELECT k, ts, dev, deleted, seq FROM lm_songs WHERE seq > ? ORDER BY seq LIMIT ' . (LIST_LIMIT + 1));
        $q->execute([$since]);
        $items = $q->fetchAll(PDO::FETCH_ASSOC);
        $more = count($items) > LIST_LIMIT;
        if ($more) {
            array_pop($items);
        }
        foreach ($items as &$item) {
            $item['ts'] = (int)$item['ts'];
            $item['deleted'] = (int)$item['deleted'];
            $item['seq'] = (int)$item['seq'];
        }
        unset($item);
        reply(['format' => FORMAT, 'max' => $max, 'more' => $more, 'items' => $items]);
    }

    if ($action === 'get') {
        $q = $db->prepare('SELECT k, ts, dev, hash, deleted, seq, data FROM lm_songs WHERE k = ?');
        $q->execute([(string)($in['key'] ?? '')]);
        $row = $q->fetch(PDO::FETCH_ASSOC);
        if (!$row) {
            reply(['row' => null]);
        }
        $row['ts'] = (int)$row['ts'];
        $row['deleted'] = (int)$row['deleted'];
        $row['seq'] = (int)$row['seq'];
        reply(['row' => $row]);
    }

    if ($action === 'push') {
        $key = (string)($in['key'] ?? '');
        $ts = (int)($in['ts'] ?? 0);
        $dev = (string)($in['dev'] ?? '');
        $deleted = empty($in['deleted']) ? 0 : 1;
        $data = $deleted ? null : (string)($in['data'] ?? '');
        if ($key === '' || strlen($key) > 190 || $ts <= 0 || $dev === '' || strlen($dev) > 32) {
            reply(['error' => 'Ungültige Angaben.'], 400);
        }

        for ($attempt = 1; ; $attempt++) {
            try {
                $db->beginTransaction();
                $q = $db->prepare('SELECT ts, dev FROM lm_songs WHERE k = ? FOR UPDATE');
                $q->execute([$key]);
                $old = $q->fetch(PDO::FETCH_ASSOC);
                if ($old && ((int)$old['ts'] > $ts || ((int)$old['ts'] === $ts && strcmp($old['dev'], $dev) >= 0))) {
                    $db->rollBack();
                    reply(['accepted' => false]);       // auf dem Server liegt schon eine jüngere (oder dieselbe) Änderung
                }
                $db->exec('UPDATE lm_counter SET v = LAST_INSERT_ID(v + 1) WHERE id = 1');
                $seq = (int)$db->query('SELECT LAST_INSERT_ID()')->fetchColumn();
                $up = $db->prepare('INSERT INTO lm_songs (k, ts, dev, hash, deleted, seq, data) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON DUPLICATE KEY UPDATE ts = VALUES(ts), dev = VALUES(dev), hash = VALUES(hash),
                        deleted = VALUES(deleted), seq = VALUES(seq), data = VALUES(data)');
                $up->execute([$key, $ts, $dev, substr((string)($in['hash'] ?? ''), 0, 64), $deleted, $seq, $data]);
                $db->commit();
                reply(['accepted' => true, 'seq' => $seq]);
            } catch (PDOException $e) {
                if ($db->inTransaction()) {
                    $db->rollBack();
                }
                if ($attempt < 3 && $e->getCode() === '40001') {     // Deadlock: noch einmal versuchen
                    usleep(100000);
                    continue;
                }
                throw $e;
            }
        }
    }

    reply(['error' => 'Unbekannte Aktion.'], 400);
} catch (Throwable $e) {
    error_log('LiedManager-Sync: ' . $e->getMessage());
    reply(['error' => 'Serverfehler (Datenbank-Zugang oder Speichergrenze prüfen).'], 500);
}
