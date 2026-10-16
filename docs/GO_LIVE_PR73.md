# PROMPTFINISHER – Release- und Go-Live-Verfahren

## GitHub

PR #73 ist der Freigabe-Branch. Haupt-CI, Browser-Smoke, Full-Stack, Shell-/Container-/Dependency-Security **und** der zusätzliche Workflow `PROMPTFINISHER Release Safety Gates` müssen für **dieselbe HEAD-SHA** erfolgreich abgeschlossen sein. Erst danach Review und Merge nach `main`.

Die erfolgreiche GitHub-CI ist kein Nachweis einer realen Zielhost-Staging-Abnahme. Die erforderliche technische, sprachliche, visuelle und rechtliche Abnahme bleibt separat.

## Staging: ausschließlich isolierter Docker-Host

Die bestehenden Compose-Dateien verwenden physische `promptmaster_*`-Volumes sowie den Projektnamen `promptfinisher`. Deshalb kein unkontrolliertes `bootstrap.sh` auf dem bereits produktiv genutzten Docker-Host.

Auf einem **eigenen Staging-Host** separaten Checkout erstellen, `.env` mit Staging-Secrets und Mailpit konfigurieren und mit `chmod 600 .env` absichern. Danach vor Docker-Build oder Start:

```bash
cd /pfad/zum/eigenen/promptfinisher-staging-checkout
# Exakte, zuvor auf GitHub grün geprüfte vollständige PR-Commit-SHA einsetzen:
SHA="<FREIGEGEBENE_40_STELLIGE_GITHUB_SHA>"
python3 scripts/staging_readiness.py . --expected-sha "$SHA"
```

Nur `STAGING_READINESS=PRECHECK_PASS; NO_CHANGES_MADE=YES` erlaubt den anschließenden isolierten `bash scripts/bootstrap.sh`. Bei `BLOCKED` keinesfalls produktive Volumes, Container oder Netzwerke löschen oder stoppen. Die Konfiguration muss Staging-Mail ausschließlich auf `mailpit:1025`, Mollie nur auf Testzugänge und das Restic-Repository auf das isolierte Testvolume begrenzen.

Danach reale Anwendungs-, Rollen-/Mandanten-, CSRF-/2FA-, Sprach-, Mobile-/Desktop-, Zahlungs-, Backup-/Restore- und Proxy-Endabnahme durchführen. Für Mollie, sprachliche Qualität und Rechtstexte sind gesonderte Freigaben erforderlich.

## Produktiver Start – erst nach Merge UND nachgewiesener Abnahme

Auf dem Produktionsserver im vorhandenen Checkout:

```bash
cd /root/projekte/docker/promptmaster
git fetch origin main
git switch main
git pull --ff-only origin main
export PM_RELEASE_SHA="$(git rev-parse HEAD)"
export PM_GO_LIVE_CONFIRM="$PM_RELEASE_SHA"
export PM_STAGING_ACCEPTED_SHA="$PM_RELEASE_SHA"
export PM_LEGAL_APPROVED=YES
export PM_TRANSLATION_APPROVED=YES
export PM_VISUAL_APPROVED=YES
export PM_PAYMENT_TEST_APPROVED=YES
bash scripts/go_live.sh --verify-only
```

**Wichtig:** Die `*_APPROVED`-Angaben nur setzen, wenn die jeweiligen Prüfungen tatsächlich dokumentiert und erfolgreich abgeschlossen wurden. Nicht als Abkürzung verwenden.

Nach erfolgreicher Verifikation und Wartungsfreigabe:

```bash
PM_EXECUTE_GO_LIVE=YES bash scripts/go_live.sh
```

Der Wrapper erfordert: exakt bestätigte vollständige SHA, Branch `main`, passende `origin/main`, saubere getrackte Quellen, lokale Docker-Verbindung, private `.env`, ein nachgewiesenes Off-Host-Backup und sämtliche vorgenannten Freigaben. Standardmäßig bleibt **TLS-S3 zwingend**, ohne ausdrückliche Alternative.

### Backup-Alternative ohne S3 (nur mit echtem Offline-Restore und Risikofreigabe)

Für Betreiber mit einem bereits außerhalb des Servers auf einem verschlüsselten Windows-Rechner gesicherten Archiv kann ein **einmaliger** alternativer Go-Live-Backup-Nachweis erfolgen: Erst muss das Originalarchiv samt SHA256-Seitendatei auf einem gesonderten Linux-Recovery-Host mit `scripts/offline_recovery_drill.py` tatsächlich überprüft und dessen PostgreSQL-Dump isoliert wiederhergestellt worden sein. Der erzeugte JSON-Bericht darf **nicht simuliert** werden. Er ist mit Dateirechten 0600 auf dem Produktionsserver in einem nicht versionierten, root-geschützten Evidenzverzeichnis zu hinterlegen.

Der alternative Modus wird **ausschließlich** über `PM_OFFSITE_BACKUP_MODE=independent-offline` aktiviert. Er verlangt einen maximal 72 Stunden alten realen Restore-Bericht und ein maximal 72 Stunden altes Archiv-Erstellungsdatum, dessen `archive_sha256` dem auf Windows überprüften Backup entspricht, außerdem `PM_OFFSITE_RESTORE_REPORT`, `PM_OFFSITE_ARCHIVE_SHA256`, `PM_OFFSITE_STORAGE_CONFIRMED=YES`, `PM_OFFSITE_DISK_ENCRYPTED=YES` und die genaue bewusste Risikoakzeptanz `PM_OFFSITE_RISK_ACCEPTANCE=ACCEPT_MANUAL_OFFSITE_BACKUP_RISK_FOR_THIS_RELEASE`.

Fehlen Nachweise oder Betreiberfreigaben, bleibt `go_live.sh` gesperrt. Dieser Sonderweg bestätigt **keine** automatische Offsite-Backup-Replikation, keinen vollständigen Wiederanlauf der Webanwendung und keine fachlichen Freigaben. Die Windows-Archivpassphrase mit nur fünf Zeichen ist schwach; ein gesondert verschlüsselter Speicher ist eine notwendige Mindestkompensation. Siehe `docs/OFFLINE_RECOVERY_PR73.md`. Er ruft dann die bereits vorhandene, gehärtete `scripts/deploy.sh` mit Backup-/Migrations-/Health-/Rollback-Gates auf. Er selbst führt keinen Git-Checkout, keine Volume-Löschung und keine automatische Datenbank-Rückmigration aus.

**Nach dem Start:** öffentliche Marketing-/Free-/Login-/Pro-/Admin-Routen, echte E-Mail-Zustellung, Kauf-/Webhook-Fluss, Pro-Lizenzerstellung, aktuelle Versions-SHA sowie Backup-/Restore-Status gegen die produktive Domain prüfen. Nur dann den Livebetrieb fachlich abnehmen. Bei Fehlern das Last-Known-Good-/Backup-Verfahren aus `deploy.sh` anwenden und Datenbank-Migrationen nicht blind zurückdrehen.
