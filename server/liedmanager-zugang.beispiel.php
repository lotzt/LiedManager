<?php
// Zugangsdaten für remote.php und sync.php – umbenennen in „liedmanager-zugang.php“, Werte eintragen und auf den
// Server legen: neben die beiden Dateien oder einen Ordner darüber (z. B. …/steuerung/remote.php und …/sync/sync.php,
// dann die Zugangsdatei in …/). Gehört NIE ins Repository. Wird sie direkt aufgerufen, zeigt sie nichts an.
define('TOKEN',   'HIER-LANGES-ZUFAELLIGES-TOKEN');     // auch in LiedManager: Einstellungen → Remote und → Lieder
define('PIN',     'HIER-PASSWORT-FUER-DEN-BROWSER');    // Anmeldung im Browser (nur Fernsteuerung), mindestens 8 Zeichen
define('DB_HOST', 'localhost');
define('DB_NAME', 'dXXXXXXX');
define('DB_USER', 'dXXXXXXX');
define('DB_PASS', 'HIER-DB-PASSWORT');
