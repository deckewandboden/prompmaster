# Production Acceptance

Diese Datei beschreibt ausschließlich die Gates, die reale Provider-/Infrastrukturzugänge benötigen. Secrets werden niemals ins Repository geschrieben.

## Microsoft Graph

Voraussetzungen:

- `EMAIL_PROVIDER=graph`
- `GRAPH_TENANT_ID`
- `GRAPH_CLIENT_ID`
- `GRAPH_CLIENT_SECRET`
- `GRAPH_SENDER`
- Entra-Anwendungsberechtigung `Mail.Send` mit Admin Consent
- der Graph-App-Zugriff sollte auf das tatsächlich benötigte Absenderpostfach eingeschränkt werden

Ausführung im laufenden Web-Container:

```bash
docker compose exec -T web python manage.py external_graph_acceptance \
  --recipient ABNAHME_EMPFAENGER@example.com \
  --confirm SEND-GRAPH-ACCEPTANCE
```

Das Gate gilt erst als bestanden, wenn der Command JSON mit `"status": "ok"` liefert und die Testmail beim vorgesehenen Empfänger angekommen ist. Der Command führt zusätzlich mit denselben realen OAuth-Credentials eine absichtlich ungültige Sender-Anfrage aus und erwartet einen echten Graph-Fehler. Der lokale Celery-Retrypfad bleibt zusätzlich durch die normale Django-CI abgesichert.

## Mollie Testmodus

Der Acceptance-Command akzeptiert ausschließlich API-Keys mit `test_`-Präfix. Live-Keys werden abgelehnt.

### 1. Echten PromptMaster-Kauf starten

Der Benutzer muss ein normal nutzbarer Staging-Kunde mit verifizierter E-Mail, vollständigen Rechnungsdaten und den benötigten Rechtstexten/Steuerregeln sein.

```bash
docker compose exec -T web python manage.py external_mollie_acceptance start \
  --user-email ABNAHME_KUNDE@example.com \
  --base-url https://STAGING-DOMAIN.example.com \
  --confirm CREATE-MOLLIE-TEST-PAYMENT
```

Der Command verwendet den echten Portal-POST `/portal/licenses/buy/`. Erwartete Ausgabe: `payment_id`, `order`, `checkout_url` und ggf. `change_payment_state_url`.

Die `checkout_url` im Mollie-Testmodus öffnen und den Teststatus auf **paid** setzen. Mollie muss anschließend den echten PromptMaster-Webhook aufrufen.

### 2. Webhook und Aktivierung prüfen

```bash
docker compose exec -T web python manage.py external_mollie_acceptance verify \
  --payment-id tr_... \
  --expect paid
```

Das Gate verlangt mindestens ein verarbeitetes `MollieEvent`. Nur ein manuelles Ändern der lokalen Datenbank reicht daher nicht.

### 3. Refund über den produktiven Refund-Service

```bash
docker compose exec -T web python manage.py external_mollie_acceptance refund \
  --payment-id tr_... \
  --confirm CREATE-MOLLIE-TEST-REFUND
```

Danach erneut `verify` mit dem tatsächlich erreichten lokalen Refundstatus ausführen.

### 4. Chargeback und Chargeback-Reversal

Für eine bezahlte Testzahlung Mollies `changePaymentState`-Link verwenden und einen Chargeback erzeugen. Danach:

```bash
docker compose exec -T web python manage.py external_mollie_acceptance verify \
  --payment-id tr_... \
  --expect chargeback
```

Die Testzahlung anschließend über Mollies Testoberfläche wieder auf bezahlt/reversed setzen und prüfen:

```bash
docker compose exec -T web python manage.py external_mollie_acceptance verify \
  --payment-id tr_... \
  --expect chargeback_reversed
```

Damit werden die realen Mollie-Webhooks, die lokale Zahlungszustandsmaschine und die Lizenzsperre/-freigabe gemeinsam abgenommen.

## Externes S3/restic + echter Restore-Drill

Voraussetzungen in der Deployment-Umgebung:

- `RESTIC_REPOSITORY=s3:...`
- `RESTIC_PASSWORD`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION` bei S3-kompatiblen Endpunkten, falls die Region nicht aus dem Endpoint hervorgeht (`S3_REGION` wird aus Bestandsgründen weiterhin als Alias akzeptiert)
- laufende PostgreSQL-Instanz

Ausführung:

```bash
PM_EXTERNAL_BACKUP_ACCEPTANCE=RUN_EXTERNAL_S3_RESTORE \
  ./scripts/external_backup_acceptance.sh
```

Der Lauf verweigert lokale restic-Ziele. Er erstellt einen echten PostgreSQL-Dump, speichert ihn im externen S3/restic-Repository, restauriert den neuesten `promptmaster-db`-Snapshot in ein isoliertes PostgreSQL und prüft `django_migrations`. Retention/Prune wird in diesem Acceptance-Lauf nicht ausgelöst.

## Abnahmeevidenz

Für die Produktionsfreigabe werden mindestens festgehalten:

- Datum/Uhrzeit und Commit-SHA
- Graph Probe-ID + Graph Request-ID + tatsächlicher Mail-Empfang
- Mollie Order-/Payment-ID und erfolgreich verarbeitete Webhook-Zustände
- Mollie Refund-ID sowie Chargeback-/Reversal-Zustände
- Ausgabe `EXTERNAL S3/RESTIC BACKUP + ISOLATED POSTGRES RESTORE OK`
- Entscheidung zur cAdvisor-Host-Trust-Boundary
- Name des menschlichen Release-Freigebenden

Keine Provider-Secrets oder Restic-Passwörter in Screenshots, Tickets oder Abnahmeprotokolle übernehmen.
