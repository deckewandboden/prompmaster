# PromptMaster – Chat-Transfer / aktueller Arbeitsstand

Datum: 2026-09-12

## Zweck
Dieses Paket bündelt die in diesem Chat aktuell physisch verfügbaren neuesten Artefakte, damit der Stand in einen neuen Chat übertragen werden kann.

## Verbindliche Produktentscheidungen

### Lizenzierung
- PromptMaster Free bleibt ohne Login nutzbar.
- PromptMaster Pro erfordert Login, aktive Lizenz und Geräteprüfung.
- Jede neu gekaufte Lizenz läuft individuell 365 Tage ab bestätigter Zahlung.
- Verlängerung vor Ablauf: +365 Tage auf bestehendes Ablaufdatum.
- Verlängerung nach Ablauf: neue 365 Tage ab bestätigter Zahlung.
- Keine automatische Verlängerung.
- Reminder T-60 und T-30; ab T-7 starke In-App-Warnung; T0 Pro-Zugriff gesperrt.
- 2 Geräte je Pro-Benutzer.
- Normale Benutzer können Geräte nicht selbst freigeben; Firmenadmin oder netstyle kann Slots zurücksetzen.

### Firma / Benutzer
- V1 exakt ein aktiver Firmenadministrator je Unternehmen.
- Datenmodell soll spätere mehrere Administratoren erlauben.
- Firmenadmin muss keinen Pro-Seat verbrauchen, um die Firma zu verwalten.
- Firmenadmin kann Benutzer einladen, Lizenzen zuweisen/freigeben, Geräte zurücksetzen, kaufen und verlängern.
- Einladungen: 24 Stunden, single-use, Resend invalidiert alten Link.
- Company-Admin-Transfer mit 2FA und Audit.

### Preise
- Aktueller Pro-Preis: 2,99 EUR brutto pro Benutzer/Monat als Jahresabrechnung = 35,88 EUR brutto/Jahr.
- Neukaufpreis und Verlängerungspreis separat konfigurierbar.
- Historische Preise werden versioniert, nicht überschrieben.

### Zahlung
- Mollie ist der einzige Payment Provider in V1.
- Keine eigene Kreditkartenverarbeitung.
- Keine eigene Rechnungs-PDF-/Rechnungsnummern-Engine.
- Mollie-Webhooks müssen serverseitig verifiziert und idempotent verarbeitet werden.
- Refund: ungenutzte Resttage einer Lizenz taggenau anteilig.
- Chargeback: betroffene Lizenz vorläufig sperren, Daten nicht löschen.

### Rollen / Security
- netstyle Rollen: Superadmin, Vertrieb/Support, Technik/Operations.
- Rollen-/Permission-Modell generisch, nicht hartcodiert.
- 2FA Pflicht für Firmenadmin und alle netstyle internen Rollen.
- TOTP + Recovery Codes.
- Custom Django User Model, Login per E-Mail.

### Kundenportal
Separate Unterseiten:
- Dashboard
- Mein Team
- Einladungen
- Lizenzen
- Geräte
- weitere Lizenzen kaufen
- Bestellungen & Zahlungen
- Unternehmen
- Profil/Sicherheit
- Hilfe & Kontakt

### netstyle Admin
Separate Unterseiten:
- Übersicht
- Kunden
- Lizenzen
- Bestellungen & Zahlungen
- Produkte & Preise
- E-Mail
- Mollie
- Statistiken
- System & Betrieb
- API & Integrationen
- Datenschutz & Recht
- Protokolle
- Benutzer & Rollen
- Einstellungen

Keine Endlos-Scroll-Seite.

### Enterprise DataGrid
Alle großen Listen müssen serverseitig arbeiten:
- Pagination
- 25 / 50 / 100 / 250
- Sortierung ASC/DESC
- Suche
- Filter
- aktive Filter sichtbar
- Reset/Zurücksetzen
- URL-State/Deep Links
- CSV-Export
- Mobile Card View
- Permission Checks
- Loading/Empty/Error States

Ziel: 5.000+ Kunden und große Eventtabellen ohne vollständiges Laden in den Browser.

### Operations / Techniker-Portal
netstyle Backend enthält System-&-Betrieb-Dashboard:
- CPU
- RAM
- Storage
- freie Inodes
- Uptime / Load
- OS / Docker / App-Version
- PostgreSQL Status, Größe, Connections
- Worker / Queue
- Caddy
- Mollie
- Mail
- Backup
- Restore-Test
- Warnungen

Operations API:
- /api/v1/ops/health
- /api/v1/ops/system
- /api/v1/ops/storage
- /api/v1/ops/database
- /api/v1/ops/services
- /api/v1/ops/backups
- /api/v1/ops/integrations
- /api/v1/ops/maintenance-snapshot

Service Account z. B. technikerportal-maintenance mit Scope ops.read.
Techniker-Portal später nur outbound HTTPS. Kein Inbound-Port in das netstyle LAN.

### Betrieb / Deployment
Zielstack:
- Ubuntu
- Docker Compose
- Caddy
- Django / Gunicorn
- PostgreSQL
- Redis
- Celery Worker
- Celery Beat
- Mailpit in Staging
- Prometheus / Node Exporter / cAdvisor / PostgreSQL Exporter
- restic + pg_dump Backup

Staging zuerst auf vorhandenem IONOS-VPS, später gleicher Stack auf separatem Produktions-VPS.

### Git/Codex
Ziel:
1. vollständigen Projektstand erzeugen,
2. private GitHub-Repo,
3. Staging,
4. Tests,
5. Codex als Repository-Reviewer/Fehlerbeheber,
6. menschliche Prüfung vor Production.

## Design
- Dunkle Navy-/Blau-/Cyan-Formsprache.
- Kundenportal eher dunkel/Produktcharakter.
- netstyle Admin datenorientiert mit dunkler Sidebar + heller Arbeitsfläche.
- Responsive Desktop/Tablet/Smartphone.
- PromptMaster-Logo darf nicht frei nachgezeichnet werden; Original/Golden-Master-Asset verwenden.
- Für die Marketingseite gelten die separat entwickelten Golden-Master-/V13–V15-Referenzen; nicht durch Admin-Mockups ersetzen.

## Wichtiger Dateistatus
Das Paket enthält alle Dateien, die in der aktiven Laufzeit dieses Chats tatsächlich materialisiert und zugreifbar sind.

Die Chat-Antworten behaupteten im Verlauf umfangreichere RC4–RC8-Django-Projektbäume. In der aktuell zugreifbaren Laufzeit sind von RC8 jedoch nur README.md, SPEC.md und AGENTS.md physisch vorhanden. Der tatsächlich zugreifbare Phase-2-Baselineordner enthält die Dateien unter `03_PHASE2_ACTUAL_CODE_BASELINE/`.

Diese Einschränkung wird hier ausdrücklich dokumentiert, damit in einem neuen Chat keine nicht vorhandenen Dateien als gesichert angenommen werden.

## Startpunkt im neuen Chat
1. `01_MASTER_SPEC/PromptMaster_MASTER_SPEC_V1.0.md` lesen.
2. `02_LATEST_RC8_DOCUMENTATION/` als jüngste RC-Dokumentation lesen.
3. `03_PHASE2_ACTUAL_CODE_BASELINE/` als tatsächlich vorhandene Codebasis prüfen.
4. `04_UI_PROTOTYPES/` für UI/Formsprache prüfen.
5. Danach fehlenden vollständigen Django-Code sauber aus SPEC und vorhandenen Artefakten rekonstruieren bzw. aus einem separat gesicherten vollständigen RC10/Master-Archiv übernehmen, falls dieses bereitgestellt wird.
