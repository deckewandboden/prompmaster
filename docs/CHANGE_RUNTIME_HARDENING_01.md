# Runtime hardening 01

Basis: `baseline-green-2026-09-13`, Commit `5e0dc129a718e709cfc7aaeaca2a95640a28f0a4`.
Arbeitsbranch: `runtime-hardening-01`. Keine Änderungen an Produkt-, Auth-,
Lizenz-, Zahlungs- oder PromptDomain-Logik und keinen Golden Mastern.

## Runtime-Verträge

- PostgreSQL 18 verwendet dasselbe benannte `postgres_data`-Volume, jetzt am
  Image-konformen Mount `/var/lib/postgresql`. Healthcheck, internes data-Netz
  und fehlende öffentliche DB-Ports bleiben erhalten.
- Es erfolgt keine automatische Datenverschiebung, Initialisierung eines
  Ersatzvolumes oder Löschung. Vor Nutzung vorhandener Daten muss deren Layout
  geprüft werden: ein alter Cluster direkt an der Volume-Wurzel oder Daten in
  einem früheren anonymen Volume benötigen einen separat geprüften Transfer.
  Diese Änderung führt keine PostgreSQL-Datenmigration aus.
- Der Backup-Buildkontext enthält ausschließlich versionierte Quelldateien.
  Git und Docker schließen Runtime-Daten aus; nur Dockerfile, backup.sh und
  .dockerignore sind freigegeben.
- Restore-Tests verwenden einen eigenen temporären Cluster. Der Elternordner
  gehört root:postgres (0750), PGDATA und Socket postgres (0700). Der Restore
  bricht bei SQL-Fehlern ab und prüft anschließend die Migrationstabelle.
- Ein fehlgeschlagener Restore schreibt `restore_failed` in last-backup.json,
  `failed` in last-restore.json und beendet den Prozess mit Exitcode 1.
  Erfolg wird erst nach dem fälligen Restore gemeldet. Fehler setzen keinen
  erfolgreichen Restore-Zeitstempel. Vorhandene Snapshots werden nicht durch
  Fehler-Cleanup gelöscht; die bestehende Retention bleibt unverändert.
- Beat schreibt seine Schedule-Dateien ausschließlich nach /tmp/celerybeat
  (separates tmpfs, 16 MiB). Web, Worker und Beat behalten in Produktion ein
  schreibgeschütztes Root-Dateisystem. Der Beat-Schedule ist flüchtig und wird
  nach Container-Neustart neu erstellt; Geschäftsdaten liegen in PostgreSQL.

## Prüfungen

Der erste vollständige CI-Start wies zusätzlich fehlende Schreibrechte im
frischen static_data-Volume nach. Das Backend-Image legt /app/staticfiles nun
vor dem Benutzerwechsel mit app-Ownership an; Docker übernimmt diese Rechte
bei der erstmaligen Volume-Befüllung. collectstatic läuft weiterhin als app.

Der anschließende vollständige Pull wies die ungültige alte cAdvisor-Registry
nach. Version 0.60.5 bleibt unverändert; die Quelle ist jetzt
ghcr.io/google/cadvisor:v0.60.5 gemäß der offiziellen cAdvisor-Dokumentation.

`github_preflight.py` prüft nun auch den versionierten Backup-Kontext und die
PostgreSQL-/Beat-Konfiguration sowie sechs negative/positive Regressionstests.
Die CI validiert Staging- und Production-Compose und baut alle drei Images.
Der zusätzliche full-stack-Job startet den vollständigen Staging-Stack mit
dem Production-Dateisystem-Override, führt runtime_validate.sh aus und prüft
danach einen gezielt fehlgeschlagenen pg_restore samt erfolgreicher Wiederholung.
Die Fehlerinjektion ist ausschließlich in isolierten GitHub-Actions-Läufen erlaubt.

Die vorhandenen Staging-Source-Bind-Mounts bleiben Teil dieses Tests; er ersetzt
keine Production-Abnahme mit echten Provider-Zugangsdaten. S3, Graph, Mollie,
öffentliche DNS/TLS-Konfiguration und vorhandene Datenvolumes bleiben externe
Release-Gates. Docker ist auf dem lokalen Windows-Arbeitsplatz nicht verfügbar;
der konkrete CI-Nachweis und die tatsächlich ausgeführten Prüfungen werden im
Pull Request dokumentiert. Keine Produktionsfreigabe durch diese Änderung.
