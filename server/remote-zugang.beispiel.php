<?php
// Zugangsdaten für remote.php – umbenennen in „remote-zugang.php“, Werte eintragen und neben remote.php auf den
// Server legen. Diese Datei gehört NIE ins Repository. Wird sie direkt aufgerufen, zeigt sie nichts an.
define('TOKEN',   'HIER-LANGES-ZUFAELLIGES-TOKEN');     // auch in LiedManager: Einstellungen → Remote
define('PIN',     'HIER-PASSWORT-FUER-DEN-BROWSER');    // Anmeldung im Browser, mindestens 8 Zeichen
define('DB_HOST', 'localhost');
define('DB_NAME', 'dXXXXXXX');
define('DB_USER', 'dXXXXXXX');
define('DB_PASS', 'HIER-DB-PASSWORT');
