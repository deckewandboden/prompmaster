# Production Acceptance

Diese Datei beschreibt ausschließlich die Gates, die reale Provider-/Infrastrukturzugänge benötigen. Secrets werden niemals ins Repository geschrieben.

## Mailversand — SMTP oder Microsoft Graph

PROMPTFINISHER unterstützt produktiv SMTP1, optional SMTP2 und Microsoft Graph. Der
für den Release tatsächlich gewählte Primärprovider muss real gegen einen externen
Empfänger abgenommen werden. Ein nicht verwendeter Provider ist kein Go-Live-Blocker.

### SMTP-Abnahme

Für SMTP muss der produktive Pfad über einen persistierten `EmailMessage`-Datensatz
laufen. Zu dokumentieren sind mindestens:

- `status=sent`, `retry_count=0` und der tatsächlich verwendete Provider;
- reale Zustellung an einen externen Empfänger;
- SPF, DKIM und DMARC beim Empfänger jeweils `PASS`;
- TLS auf dem Provider-Hop;
- `From`, `Return-Path` und `Reply-To` passend zur freigegebenen Absenderidentität;
- Message-ID mit der konfigurierten Absenderdomain statt eines Container-/Docker-Hostnamens.

Spam-/Inbox-Klassifizierung wird separat als Deliverability/Reputation beobachtet und
ist nicht mit erfolgreicher technischer Authentifizierung gleichzusetzen.

## Microsoft Graph

Microsoft Graph ist nur dann ein verpflichtendes externes Gate, wenn Graph im finalen
Routing tatsächlich als Primär- oder Failover-Provider aktiviert wird.


Voraussetzungen:

- `EMAIL_PROVIDER=graph`
- `GRAPH_TENANT_ID`
- `GRAPH_CLIENT_ID`
- `GRAPH_CLIENT_SECRET`
- `GRAPH_SENDER`
- Microsoft Graph App-only-Authentifizierung über die konfigurierte Entra-App
- in Exchange Online eine **Application-RBAC**-Zuweisung `Application Mail.Send`, deren Ressourcenbereich ausschließlich das tatsächlich benötigte PROMPTFINISHER-Absenderpostfach umfasst
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

Eine Produktionsinstanz darf für technische Pre-Go-Live-Abnahmen ohne Mollie-Key laufen.
Solange kein Mollie-Key konfiguriert ist, sind providerbasierte Zahlungen nicht verfügbar.
Vor dem kommerziellen Go-Live des automatischen Pro-Kaufs ist die folgende Mollie-Abnahme
verpflichtend.

Der Acceptance-Command akzeptiert ausschließlich API-Keys mit `test_`-Präfix. Live-Keys werden abgelehnt. Die `--base-url` muss eine öffentlich erreichbare HTTPS-Adresse sein; `localhost`, lokale/Test-Domains sowie private/Loopback-IP-Adressen werden bereits vor der Provider-Aktion abgelehnt, weil Mollie den Webhook sonst nicht real zurückrufen könnte.

### 1. Echten PROMPTFINISHER-Kauf starten

Der Benutzer muss ein normal nutzbarer Staging-Kunde mit verifizierter E-Mail, vollständigen Rechnungsdaten und den benötigten Rechtstexten/Steuerregeln sein.

```bash
docker compose exec -T web python manage.py external_mollie_acceptance start \
  --user-email ABNAHME_KUNDE@example.com \
  --base-url https://STAGING-DOMAIN.example.com \
  --confirm CREATE-MOLLIE-TEST-PAYMENT
```

Der Command verwendet den echten Portal-POST `/portal/licenses/buy/`. Er akzeptiert den Lauf nur, wenn Mollie den angelegten Payment-Datensatz selbst mit `mode=test` zurückliefert, `metadata.order_id` exakt auf die lokal erzeugte Bestellung zeigt und die von Mollie gespeicherte `webhookUrl` exakt dem öffentlichen PROMPTFINISHER-Webhook der angegebenen Base-URL entspricht. Erwartete Ausgabe: `payment_id`, `order`, `checkout_url`, `provider_mode=test`, `webhook_url` und ggf. `change_payment_state_url`.

Die `checkout_url` im Mollie-Testmodus öffnen und den Teststatus auf **paid** setzen. Mollie muss anschließend den echten PROMPTFINISHER-Webhook aufrufen.

### 2. Webhook und Aktivierung prüfen

```bash
docker compose exec -T web python manage.py external_mollie_acceptance verify \
  --payment-id tr_... \
  --expect paid
```

Das Gate verlangt zusätzlich erneut `provider_mode=test`, passende Order-Metadaten und mindestens ein verarbeitetes `MollieEvent`. Nur ein manuelles Ändern der lokalen Datenbank reicht daher nicht.

### 3. Refund über den produktiven Refund-Service

```bash
docker compose exec -T web python manage.py external_mollie_acceptance refund \
  --payment-id tr_... \
  --confirm CREATE-MOLLIE-TEST-REFUND
```

Danach erneut `verify` mit dem tatsächlich erreichten lokalen Refundstatus ausführen.

### 4. Chargeback und Chargeback-Reversal

Für eine bezahlte Testzahlung Mollies `changePaymentState`-Link verwenden und einen Chargeback erzeugen. Mollies regulärer Payment-Status bleibt dabei typischerweise `paid`; der Acceptance-Command lädt deshalb zusätzlich die Chargeback-Ressourcen des Payments. Ein Chargeback mit `reversedAt=null` muss lokal zu `Payment.status=chargeback` und für alle betroffenen aktiven Lizenzen zu `payment_review` führen. Danach:

```bash
docker compose exec -T web python manage.py external_mollie_acceptance verify \
  --payment-id tr_... \
  --expect chargeback
```

Ein Chargeback-Reversal darf **nur** dann als bestanden markiert werden, wenn Mollie für denselben Chargeback einen gesetzten `reversedAt`-Zeitpunkt liefert und dieser Zustand über den öffentlichen Webhook erneut in PROMPTFINISHER verarbeitet wurde. Der Acceptance-Command verlangt dabei gleichzeitig den Provider-Chargeback-Zustand, einen verarbeiteten lokalen `chargeback_reversed`-Event und wieder freigegebene betroffene Lizenzen. Mollie dokumentiert für den Testmodus ausdrücklich das Erzeugen von Refunds und Chargebacks über `changePaymentState`; ein jederzeit verfügbarer manueller Reversal-Schalter ist dagegen nicht garantiert. Falls die verwendete Mollie-Testumgebung einen Reversal-Pfad anbietet, anschließend prüfen:

```bash
docker compose exec -T web python manage.py external_mollie_acceptance verify \
  --payment-id tr_... \
  --expect chargeback_reversed
```

Der Command akzeptiert hierfür weder ein lokales Datenbank-Umschreiben noch nur einen alten `paid`-Datensatz: Providerstatus, verarbeiteter Webhook und wieder freigegebener Lizenzstatus müssen gemeinsam passen. Bietet Mollie im verwendeten Testkonto keinen Reversal-Pfad an, bleibt genau dieser Teil des externen Gates **offen** und muss mit einem von Mollie bereitgestellten/providerunterstützten Reversal-Test nachgewiesen werden. Chargeback selbst kann davon unabhängig vollständig abgenommen werden.

## Mollie Live-Readiness — read-only Produktionsprobe

Nach erfolgreicher Sandbox-Abnahme und erst nachdem der Mollie-Account produktiv freigeschaltet wurde, werden in Produktion der effektive `live_`-API-Key und die erwartete Profil-ID konfiguriert. Vor dem ersten echten Kundenkauf wird ausschließlich read-only geprüft:

```bash
docker compose exec -T web python manage.py external_mollie_acceptance probe-live
```

Das Probe-Gate ist nur bestanden, wenn der Command JSON mit `"status": "ok"` liefert und gleichzeitig nachweist:

- der effektive Runtime-Key ist ein `live_`-Key;
- `GET /v2/profiles/me` liefert exakt die konfigurierte Profil-ID;
- das Profil läuft in `mode=live`;
- `profile.status=verified`;
- `GET /v2/methods?sequenceType=oneoff` liefert mindestens eine Zahlart mit `status=activated`.

Die Probe erstellt **keine** Zahlung, Erstattung oder sonstige Provider-Mutation. Ein Profil mit `unverified`/`blocked` oder ohne aktivierte Live-Zahlart bleibt Go-Live-blockierend. Auch nach erfolgreichem `probe-live` bleibt der öffentliche Produktiv-Checkout absichtlich gesperrt.

Erst die bewusste finale Freigabe aktiviert neue echte Käufe:

```bash
docker compose exec -T web python manage.py external_mollie_acceptance activate-live \
  --confirm ENABLE-MOLLIE-LIVE-CHECKOUT
```

`activate-live` wiederholt dieselben read-only Providerprüfungen und setzt nur nach vollständigem Erfolg den lokalen Gate-Wert `mollie_checkout_enabled=true`. Jede spätere Änderung an Mollie-Profil-ID oder API-Key setzt diese Freigabe automatisch wieder auf `false`.

Eine sofortige Notabschaltung ist im Netstyle-Backend auf der Mollie-Seite über **„Produktiv-Checkout sperren“** möglich. Sie verhindert neue Kaufstarts, ohne bestehende Payment-Webhooks, Refunds oder Reconciliation abzuschalten.

## Externes S3/restic + echter Restore-Drill

Der reguläre Stack kann zunächst das persistente Docker-Volume `/repository` als lokales
Restic-Ziel verwenden. Das schützt gegen Anwendungs-/Datenbankfehler, ist aber kein
Off-Host-Disaster-Recovery. Externes S3 und AWS-kompatible Zugangsdaten sind deshalb für
den technischen Pre-Go-Live-Deploy optional, bleiben aber vor der endgültigen
Disaster-Recovery-/Go-Live-Freigabe ein separates Acceptance-Gate.

Voraussetzungen für die **externe** S3-Abnahme:

- `RESTIC_REPOSITORY=s3:...`
- `RESTIC_PASSWORD`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION` bei S3-kompatiblen Endpunkten, falls die Region nicht aus dem Endpoint hervorgeht (`S3_REGION` wird im Runner nur noch als Altbestand-Alias akzeptiert)
- bei temporären S3-Credentials zusätzlich `AWS_SESSION_TOKEN`
- laufende PostgreSQL-Instanz

Ausführung:

```bash
PM_EXTERNAL_BACKUP_ACCEPTANCE=RUN_EXTERNAL_S3_RESTORE \
  ./scripts/external_backup_acceptance.sh
```

Der Lauf verweigert lokale, Platzhalter- und unverschlüsselte `s3:http://`-Ziele. Falls der reguläre Backup-Service läuft, wird er für die Dauer des Acceptance-Drills angehalten und beim Verlassen des Skripts automatisch wieder gestartet; dadurch kann kein paralleler geplanter Snapshot den Nachweis verfälschen. Der Runner prüft zuerst die laufende PostgreSQL-Instanz, merkt sich dann den vorherigen externen `promptfinisher-db`-Snapshot, erstellt einen echten PostgreSQL-Dump, speichert ihn im externen S3/restic-Repository und verlangt danach eine **neue Snapshot-ID**. Anschließend restauriert der Backup-Container den neuesten Snapshot in ein isoliertes PostgreSQL, prüft `django_migrations` und verlangt einen nichtleeren `backup_ref` im Restore-Status. Die Ausgabe enthält die neue `external_snapshot_id` als Abnahmeevidenz. Retention/Prune wird in diesem Acceptance-Lauf nicht ausgelöst. Historische `promptmaster-db`-Snapshots aus Releases vor dem Infrastruktur-Rebrand bleiben ausschließlich als Restore-Fallback lesbar; neue Backups und Acceptance-Nachweise verwenden `promptfinisher-db`. Der Drill soll auf Staging bzw. gegen ein dediziertes externes Acceptance-/Backup-Repository laufen, nicht als Experiment gegen ein unbekanntes Produktions-Repository.

Zusätzlich muss `scripts/runtime_validate.sh` auf demselben Release-Kandidaten `MONITOR TRUST BOUNDARY OK` ausgeben. Dieser Runtime-Nachweis bestätigt die laufende Monitoring-Isolation (keine Host-Ports, ausschließlich internes `monitor`-Netz, cAdvisor privileged und Host-Mounts read-only). Die verbleibende Entscheidung ist anschließend ausschließlich die bewusste menschliche Akzeptanz dieser dokumentierten Host-Trust-Boundary.

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
