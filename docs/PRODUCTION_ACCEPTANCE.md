# Production Acceptance

Diese Datei beschreibt ausschließlich die Gates, die reale Provider-/Infrastrukturzugänge benötigen. Secrets werden niemals ins Repository geschrieben.

## Microsoft Graph

Voraussetzungen:

- `EMAIL_PROVIDER=graph`
- `GRAPH_TENANT_ID`
- `GRAPH_CLIENT_ID`
- `GRAPH_CLIENT_SECRET`
- `GRAPH_SENDER`
- Microsoft Graph App-only-Authentifizierung über die konfigurierte Entra-App
- in Exchange Online eine **Application-RBAC**-Zuweisung `Application Mail.Send`, deren Ressourcenbereich ausschließlich das tatsächlich benötigte PromptMaster-Absenderpostfach umfasst
- **kein zusätzlicher unbeschränkter Entra-`Mail.Send`-Application-Grant**, wenn Application RBAC die wirksame Postfachbegrenzung liefern soll; Entra- und Exchange-RBAC-Berechtigungen sind additiv

### Postfachbereich vor dem Versand nachweisen

In Exchange Online PowerShell muss derselbe Service Principal einmal gegen das erlaubte Absenderpostfach und einmal gegen ein bewusst nicht freigegebenes Kontrollpostfach geprüft werden:

```powershell
Test-ServicePrincipalAuthorization -Identity "<GRAPH_CLIENT_ID oder ServicePrincipal>" -Resource "<GRAPH_SENDER>" |
  Format-Table RoleName,GrantedPermissions,AllowedResourceScope,ScopeType,InScope

Test-ServicePrincipalAuthorization -Identity "<GRAPH_CLIENT_ID oder ServicePrincipal>" -Resource "<KONTROLLPOSTFACH>" |
  Format-Table RoleName,GrantedPermissions,AllowedResourceScope,ScopeType,InScope
```

Für `Application Mail.Send` muss beim `GRAPH_SENDER` **`InScope=True`** und beim Kontrollpostfach **`InScope=False`** nachgewiesen werden. Der Cmdlet-Test bewertet Exchange Application RBAC; deshalb ist zusätzlich im Entra-Portal zu prüfen, dass kein organisationsweiter `Mail.Send`-Application-Grant parallel aktiv ist.

### Reale Versand-/Fehlerprobe

Ausführung im laufenden Web-Container:

```bash
docker compose exec -T web python manage.py external_graph_acceptance \
  --recipient ABNAHME_EMPFAENGER@example.com \
  --confirm SEND-GRAPH-ACCEPTANCE
```

Das Gate gilt erst als bestanden, wenn der Command JSON mit `"status": "ok"` liefert und die Testmail beim vorgesehenen Empfänger angekommen ist. Der Erfolgsversand läuft über einen echten persistierten `EmailMessage`-Datensatz und denselben `send_email_message`-Task wie der Produktivversand. Anschließend wird mit denselben realen OAuth-Credentials absichtlich ein ungültiger Sender verwendet. Der Command verlangt dabei einen echten Graph-HTTP-Fehler **und** einen persistierten `failed`-Status mit erhöhtem `retry_count`. Damit sind Providerfehler und lokaler Retrypfad im selben externen Gate nachgewiesen. Microsoft Graph bestätigt einen Versandaufruf lediglich mit `202 Accepted`; deshalb bleibt der tatsächliche Mail-Empfang ein separater Abnahmepunkt.

## Mollie Testmodus

Der Acceptance-Command akzeptiert ausschließlich API-Keys mit `test_`-Präfix. Live-Keys werden abgelehnt. Die `--base-url` muss eine öffentlich erreichbare HTTPS-Adresse sein; `localhost`, lokale/Test-Domains sowie private/Loopback-IP-Adressen werden bereits vor der Provider-Aktion abgelehnt, weil Mollie den Webhook sonst nicht real zurückrufen könnte.

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

Ein Chargeback-Reversal darf **nur** dann als bestanden markiert werden, wenn Mollie selbst für die Testzahlung einen echten Reversal-/wieder-bezahlt-Zustand erzeugt und dieser über den öffentlichen Webhook erneut in PromptMaster verarbeitet wurde. Mollie dokumentiert für den Testmodus ausdrücklich das Erzeugen von Refunds und Chargebacks über `changePaymentState`; ein jederzeit verfügbarer manueller Reversal-Schalter ist dagegen nicht garantiert. Falls die verwendete Mollie-Testumgebung einen Reversal-Pfad anbietet, anschließend prüfen:

```bash
docker compose exec -T web python manage.py external_mollie_acceptance verify \
  --payment-id tr_... \
  --expect chargeback_reversed
```

Der Command akzeptiert hierfür weder ein lokales Datenbank-Umschreiben noch nur einen alten `paid`-Datensatz: Providerstatus, verarbeiteter Webhook und wieder freigegebener Lizenzstatus müssen gemeinsam passen. Bietet Mollie im verwendeten Testkonto keinen Reversal-Pfad an, bleibt genau dieser Teil des externen Gates **offen** und muss mit einem von Mollie bereitgestellten/providerunterstützten Reversal-Test nachgewiesen werden. Chargeback selbst kann davon unabhängig vollständig abgenommen werden.

## Externes S3/restic + echter Restore-Drill

Voraussetzungen in der Deployment-Umgebung:

- `RESTIC_REPOSITORY=s3:...`
- `RESTIC_PASSWORD`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION` bei S3-kompatiblen Endpunkten, falls die Region nicht aus dem Endpoint hervorgeht (`S3_REGION` wird aus Bestandsgründen weiterhin als Alias akzeptiert)
- bei temporären S3-Credentials zusätzlich `AWS_SESSION_TOKEN`
- laufende PostgreSQL-Instanz

Ausführung:

```bash
PM_EXTERNAL_BACKUP_ACCEPTANCE=RUN_EXTERNAL_S3_RESTORE \
  ./scripts/external_backup_acceptance.sh
```

Der Lauf verweigert lokale restic-Ziele. Er merkt sich den vorherigen externen `promptmaster-db`-Snapshot, erstellt einen echten PostgreSQL-Dump, speichert ihn im externen S3/restic-Repository und verlangt danach eine **neue Snapshot-ID**. Anschließend restauriert der Backup-Container den neuesten Snapshot in ein isoliertes PostgreSQL, prüft `django_migrations` und verlangt einen nichtleeren `backup_ref` im Restore-Status. Die Ausgabe enthält die neue `external_snapshot_id` als Abnahmeevidenz. Retention/Prune wird in diesem Acceptance-Lauf nicht ausgelöst. Der Drill soll auf Staging bzw. gegen ein dediziertes externes Acceptance-/Backup-Repository laufen, nicht als Experiment gegen ein unbekanntes Produktions-Repository.

## Abnahmeevidenz

Für die Produktionsfreigabe werden mindestens festgehalten:

- Datum/Uhrzeit und Commit-SHA
- Graph Application-RBAC-Nachweis: `Application Mail.Send` für `GRAPH_SENDER` mit `InScope=True`, Kontrollpostfach mit `InScope=False`, plus Bestätigung, dass kein unbeschränkter Entra-`Mail.Send`-Application-Grant parallel aktiv ist
- Graph Probe-ID + persistierte Erfolgs-/Fehler-Message-IDs + tatsächlicher Mail-Empfang; Graph Request-ID zusätzlich, sofern vom Provider geliefert
- Mollie Order-/Payment-ID und erfolgreich verarbeitete Webhook-Zustände
- Mollie Refund-ID sowie Chargeback-/Reversal-Zustände
- Ausgabe `EXTERNAL S3/RESTIC BACKUP + ISOLATED POSTGRES RESTORE OK`
- Entscheidung zur cAdvisor-Host-Trust-Boundary
- Name des menschlichen Release-Freigebenden

Keine Provider-Secrets oder Restic-Passwörter in Screenshots, Tickets oder Abnahmeprotokolle übernehmen.
