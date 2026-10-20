# PROMPTFINISHER: Offline-Backup / isolierter Restore-Drill

**Stand 13.10.2026:** Windows bestätigt PROMPTFINISHER_FULL_DOWNLOAD_SHA256=PASS für das 142298393-Byte-Archiv PROMPTFINISHER_FULL_20261013T143343Z_9606150d.tar.gz.gpg. Dies ist ein manueller Off-Host-Transfer, kein vollständiger Disaster-Recovery-Test.

## Nur auf eigenständigem Linux-Recovery-Host

Auf der produktiven IONOS-VM NICHT ausführen. Erforderlich sind Linux, GnuPG, Python 3.11+, ein lokaler Docker-Daemon sowie das verschlüsselte Archiv UND seine .sha256-Datei vom Windows-PC. Der Runner verweigert bekannte PROMPTFINISHER-Container und Legacy-Volumes und erstellt keinen Produktiv-Stack.

```bash
python3 scripts/offline_recovery_drill.py /sicherer/pfad/PROMPTFINISHER_FULL_20261013T143343Z_9606150d.tar.gz.gpg --report /sicherer/pfad/offline-recovery-evidence.json
```

Passphrase verdeckt eingeben. Prüfschritte: Windows-Archiv-SHA256, durchgehender verschlüsselter TAR-Datenstrom, kritische .env/Git/Compose/Restic-Dateien, interne Hashes für PostgreSQL-Dump und Redis-RDB, echter pg_restore in neuem Einweg-PostgreSQL-18-Container ohne Netzwerk und persistente Volumes, Prüfung von django_migrations und Tabellenzahl. Der Container wird gelöscht. Nur bei Erfolg wird ein JSON-Report mit Dateirechten 0600 erzeugt.

## Grenzen und Release-Freigabe

* Kein kompletter Application-/Reverse-Proxy-Wiederanlauf, keine rechtliche/visuelle/Übersetzungs-/Provider-/Zahlungs-Abnahme.
* Das Archiv enthält keine komplette Ubuntu-VM und keinen globalen Reverse Proxy.
* Eine einmalige Windows-Kopie ersetzt keine fortlaufende externe Backupstrategie mit RPO/RTO.
* Das gewählte 5-Zeichen-Archivpasswort ist schwach: nur auf zusätzlich verschlüsseltem geschützten Datenträger aufbewahren.
* Der Standardpfad `go_live.sh` verlangt weiterhin ein TLS-S3-Repository (`PM_OFFSITE_BACKUP_MODE=s3` bzw. nicht gesetzt). Die lokale Restic-Sicherung allein genügt nicht.
* **Alternativer, ausdrücklich risikobehafteter Einzel-Release-Pfad:** `PM_OFFSITE_BACKUP_MODE=independent-offline` ruft nach der normalen produktiven Umgebungsvalidierung `scripts/offline_backup_go_live_gate.py` auf. Nur zulässig, wenn tatsächlich die separat gespeicherte Windows-Archivkopie in einem **eigenständigen Recovery-Host** entschlüsselt, ein frischer vollständiger TAR-Stream geprüft und der PostgreSQL-Dump isoliert restauriert wurde. Der echte JSON-Nachweis muss absolut adressiert, Mode 0600, nicht verlinkt, höchstens 72 Stunden alt sein und zusätzlich das tatsächliche Archiv-Erstellungsdatum als höchstens 72 Stunden alt bestätigen; er muss einer aktuellen SHA256-Prüfsumme der Windows-Datei zuordenbar sein.
* Zusätzlich verlangt der Ausnahmeweg **drei bewusste manuelle Attestierungen**: `PM_OFFSITE_STORAGE_CONFIRMED=YES` (Datei liegt auf unabhängigem Rechner), `PM_OFFSITE_DISK_ENCRYPTED=YES` (dieser ist separat verschlüsselt) und `PM_OFFSITE_RISK_ACCEPTANCE=ACCEPT_MANUAL_OFFSITE_BACKUP_RISK_FOR_THIS_RELEASE`. Nachweisdatei: `PM_OFFSITE_RESTORE_REPORT=/absoluter/pfad/report.json`, dazu `PM_OFFSITE_ARCHIVE_SHA256=<64-stellige-Prüfsumme>`. Diese Werte niemals künstlich setzen; sie bescheinigen reale Betreiberentscheidungen und keine automatisch prüfbare externe Datensicherheit.
* Die Ausnahme ersetzt **keine** laufende automatische Offsite-Sicherung, keinen vollständigen Anwendung-/Reverse-Proxy-Wiederanlauf, keine 2FA-/Security-, Mollie-, SMTP-, Translation-, Design- oder Rechtstext-Abnahme. Der normale `PM_STAGING_ACCEPTED_SHA`-Nachweis, die vier menschlichen Approvals, Main-Merge, clean Git, last-known-good und kontrolliertes `deploy.sh` bleiben ohne Abkürzung verpflichtend.
* **Freigabe nicht erfolgt:** Der konkrete echte Windows-Backup-Restore wurde noch nicht auf einem unabhängigen Host ausgeführt. Der jetzt implementierte Pfad blockiert daher weiterhin.
* PR #73 ist CI-grün, aber bis zum Abschluss der echten Staging- und Fachabnahmen Draft und nicht produktiv freigegeben.
