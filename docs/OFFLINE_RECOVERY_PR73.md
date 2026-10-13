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
* Der produktive --require-go-live-Validator verlangt nach wie vor ein TLS-S3-Repository. Keine Offline-Ausnahme ohne unabhängigen Restore-Nachweis und explizite Risikofreigabe; nicht mit fingierten Approvals umgehen.
* PR #73 ist CI-grün, aber bis zum Abschluss der echten Staging- und Fachabnahmen Draft und nicht produktiv freigegeben.
