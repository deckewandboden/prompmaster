# PromptMaster Commercial Platform
## MASTER-SPEZIFIKATION V1.0 — SOURCE OF TRUTH

**Projekt:** PromptMaster Commercial Platform  
**Organisation:** netstyle  
**Status:** FUNCTION / ARCHITECTURE FREEZE V1.0  
**Datum:** 11.09.2026  
**Zweck:** Verbindliche Grundlage für Phase 2 (Codegenerierung), Codex-Review, Tests, Staging und Produktion.

---

# 0. Verbindlichkeit und Entscheidungsregeln

## 0.1 Source of Truth

Dieses Dokument ist ab V1.0 die verbindliche funktionale und technische Spezifikation für die Commercial-Plattform von PromptMaster.

Bei Widersprüchen gilt:

1. **Diese Master-Spezifikation V1.0**
2. spätere schriftlich freigegebene Änderungsentscheidungen
3. ältere Chat-/Projektentscheidungen
4. alte Mockups und Prototypen
5. technische Standardannahmen

Ältere widersprüchliche Varianten gelten als überholt, sobald sie hier eindeutig festgelegt sind.

## 0.2 Änderungsmanagement

Jede fachliche Änderung nach Beginn von Phase 2 benötigt:

- Change-ID
- Beschreibung
- betroffene Requirements
- Datenbank-/Migrationsauswirkung
- UI-Auswirkung
- Testauswirkung
- Security-/Datenschutz-Auswirkung
- Freigabe
- Versionsanhebung der Spezifikation

Keine stillen Funktionsänderungen im Code.

## 0.3 Grundprinzipien

Die Plattform wird gebaut als:

- modularer Django-Monolith
- PostgreSQL als zentrale relationale Datenbank
- serverseitige Autorisierung
- serverseitige Pagination / Suche / Sortierung
- Docker-Compose-basiertes Deployment
- getrennte Staging- und Production-Konfiguration
- eigenständiges Kundenportal
- eigenständiges netstyle Admin-Backend
- bestehende Marketing-/Free-/Pro-Oberflächen bleiben eigenständige Frontend-Bestandteile
- API-first für Operations-/Techniker-Dashboard-Anbindung
- keine Microservices in V1
- kein Kubernetes in V1
- keine eigene Rechnungsengine
- keine eigene Kreditkartenverarbeitung
- keine öffentliche Datenbank-/Redis-/Monitoring-Schnittstelle

---

# 1. Produktumfang

## PM-PROD-001 — PromptMaster Free

PromptMaster Free:

- bleibt ohne Benutzerkonto nutzbar
- ist direkt über die Marketingseite erreichbar
- benötigt keine Registrierung
- benötigt keine Gerätebindung
- wird nicht durch das Commercial-Lizenzsystem blockiert
- bestehende Free-HTML bleibt funktional eigenständig
- spätere Pro-Upsell-Popups innerhalb Free werden separat im Free-Frontend umgesetzt

**Out of Scope Commercial Backend:** interne Prompt-Logik von Free.

## PM-PROD-002 — PromptMaster Pro

PromptMaster Pro:

- ist eine Webanwendung
- benötigt Benutzeranmeldung
- benötigt aktive Pro-Lizenz
- benötigt gültige Geräte-Registrierung
- Lizenzprüfung erfolgt serverseitig
- Lizenzrechte dürfen nicht ausschließlich über JavaScript geschützt werden
- Microsoft Copilot ist separat erforderlich
- PromptMaster selbst betreibt kein eigenes KI-Modell für die eigentliche Prompt-Verarbeitung

## PM-PROD-003 — zukünftige Produkte

Die Produktengine darf nicht auf `FREE` und `PRO` hartcodiert sein.

Später müssen ohne grundlegenden Codeumbau angelegt werden können:

- Ultra
- Ultra 2
- Premium
- Team
- Enterprise
- weitere PromptMaster-Varianten
- weitere netstyle-Softwareprodukte

Dafür existieren generische Produkt-, Preis- und Entitlement-Modelle.

---

# 2. Preis- und Laufzeitmodell

## PM-PRICE-001 — aktueller Pro-Neukaufpreis

Initiale Konfiguration:

- Monatsäquivalent: 2,99 € brutto pro Benutzer
- Abrechnung: jährlich im Voraus
- Jahrespreis: 35,88 € brutto pro Lizenz
- Währung: EUR
- Initiales Verkaufsland V1: Deutschland
- Preiswerte sind Konfiguration, niemals Hardcode

## PM-PRICE-002 — Verlängerungspreis

Der Verlängerungspreis ist separat konfigurierbar.

Initial:

- Neukauf: 35,88 € brutto
- Verlängerung: 35,88 € brutto

Spätere Preisänderungen gelten nur entsprechend ihrer definierten Gültigkeit.

## PM-PRICE-003 — Preisversionierung

Preise werden historisiert.

Ein bestehender Preisdatensatz wird nicht überschrieben, wenn ein neuer Preis gilt.

Beispiel:

- 35,88 € gültig ab 01.09.2026
- 39,90 € gültig ab 01.01.2028

Bestellungen speichern immer den tatsächlich verwendeten Preis als Snapshot.

## PM-LIC-001 — Laufzeit neue Lizenz

Jede neu gekaufte Pro-Lizenz:

- startet nach serverseitig bestätigter erfolgreicher Mollie-Zahlung
- läuft **exakt 365 Tage**
- besitzt eigenes `valid_from`
- besitzt eigenes `valid_until`
- ist unabhängig von anderen Lizenzen desselben Unternehmens

Nachgekaufte Seats werden **nicht** an bestehende Firmenlaufzeiten angeglichen.

## PM-LIC-002 — Verlängerung vor Ablauf

Wird eine aktive Lizenz vor Ablauf verlängert:

`neues valid_until = bisheriges valid_until + 365 Tage`

## PM-LIC-003 — Verlängerung nach Ablauf

Wird eine bereits abgelaufene Lizenz reaktiviert:

`valid_from = bestätigter Zahlungszeitpunkt`

`valid_until = valid_from + 365 Tage`

## PM-LIC-004 — keine automatische Verlängerung

PromptMaster Pro verlängert sich nicht automatisch.

Ohne Verlängerung:

- Lizenz wird nach Ablauf gesperrt
- Kundenkonto bleibt bestehen
- Benutzer bleiben bestehen
- Unternehmensdaten bleiben bestehen
- Bestell-/Lizenzhistorie bleibt gemäß Retention-Regeln bestehen

---

# 3. Unternehmen, Benutzer und Mandantenmodell

## PM-COMP-001 — Kundentypen

V1 unterstützt:

- Privatkunde
- Unternehmen

Die Architektur bleibt länder- und steuerregel-erweiterbar.

## PM-COMP-002 — Unternehmen

Ein Unternehmen besitzt:

- UUID
- Kundennummer
- Firmenname
- Rechtsform
- Straße
- Hausnummer
- PLZ
- Ort
- Land
- geschäftliche E-Mail
- Telefon optional
- USt-IdNr. optional/regelbasiert
- Steuernummer optional/regelbasiert
- Status
- created_at / updated_at

Requiredness von Steuerfeldern wird über Kundentyp/Land/TaxRule konfiguriert und nicht hartcodiert.

## PM-COMP-003 — Firmenadministrator

V1 erlaubt **exakt einen aktiven Firmenadministrator je Unternehmen**.

Der Firmenadministrator:

- ist selbst normaler User
- besitzt zusätzlich Unternehmensadmin-Rechte
- kann Benutzer einladen
- Lizenzen zuweisen/freigeben
- Geräte zurücksetzen
- weitere Lizenzen kaufen
- Lizenzen verlängern
- Unternehmensdaten verwalten
- Zahlungen/Bestellungen des Unternehmens sehen
- Supportformular absenden

Datenmodell bleibt technisch für mehrere Company-Admins erweiterbar.

## PM-COMP-004 — Adminübertragung

Firmenadmin kann seine Rolle an einen bestehenden Benutzer übertragen.

Anforderungen:

- Re-Authentication / 2FA
- Bestätigungsdialog
- AuditEvent
- alter Admin verliert Company-Admin-Rolle nach erfolgreicher Übertragung
- niemals zwei aktive Company-Admins in V1
- netstyle Superadmin/Support darf Admin nach Identitätsprüfung übertragen

## PM-USER-001 — Custom User Model

Von Projektbeginn an Custom User Model.

Login-ID:

- E-Mail-Adresse

Pflichtfelder:

- UUID
- E-Mail eindeutig
- Vorname
- Nachname
- Status
- email_verified_at
- last_login
- created_at
- updated_at

Keine fachliche Logik an frei vergebenen Usernames.

---

# 4. Einladungen

## PM-INV-001 — Einladung

Firmenadmin kann Mitarbeiter per E-Mail einladen.

Invitation enthält:

- UUID
- Company
- E-Mail
- Vorname optional
- Nachname optional
- Token-Hash
- created_at
- expires_at
- accepted_at
- revoked_at
- invited_by

## PM-INV-002 — Gültigkeit

Einladungslink ist **24 Stunden** gültig.

## PM-INV-003 — Sicherheit

- Token kryptografisch zufällig
- nur Hash serverseitig speichern
- einmal verwendbar
- neue Einladung invalidiert vorherige aktive Einladung derselben Zieladresse
- erneutes Senden möglich
- Widerruf möglich
- Rate Limit für Einladung/Resend

## PM-INV-004 — Ablauf

Abgelaufene Einladung:

- kann nicht angenommen werden
- zeigt eindeutigen Fehler
- verweist auf Firmenadmin
- Admin kann neue Einladung senden

---

# 5. Lizenzpool und Zuweisung

## PM-ASSIGN-001 — Lizenz ist unabhängig vom Benutzer

License und User sind getrennte Objekte.

Eine Lizenz kann:

- frei
- einem Benutzer zugewiesen
- gesperrt
- abgelaufen
- refundiert/beendet
- payment-review

sein.

## PM-ASSIGN-002 — Zuweisung

Firmenadmin darf eine freie gültige Lizenz einem aktiven Firmenbenutzer zuweisen.

## PM-ASSIGN-003 — Freigabe

Firmenadmin darf Lizenz von Benutzer lösen.

Lizenz:

- bleibt bestehen
- behält ursprüngliches Start-/Ablaufdatum
- wird wieder frei
- kann anderem Benutzer zugewiesen werden

## PM-ASSIGN-004 — Benutzer löschen/deaktivieren

Bei Deaktivierung/Löschung eines Benutzers:

- aktive Lizenzzuweisung endet
- Lizenz wird wieder frei, sofern Lizenz noch gültig
- Geräte des Benutzers werden revoked
- Sessions werden invalidiert
- AuditEvent wird geschrieben

---

# 6. Geräteverwaltung

## PM-DEV-001 — Limit

Initialer Pro-Default:

**2 aktive Geräte je Pro-Benutzer**

Das Limit wird als Produktkonfiguration gespeichert.

## PM-DEV-002 — technische Definition

PromptMaster ist browserbasiert.

Ohne lokalen Agenten ist eine 100 % sichere physische Geräteidentifikation nicht möglich.

V1 verwendet daher:

- serverseitig erzeugten kryptografischen Device-Key
- Device-Key nur als sicherer HttpOnly/Secure/SameSite Cookie im Browser
- serverseitig nur Hash
- DeviceRegistration UUID
- benutzerdefinierter Gerätename
- Browserfamilie
- Betriebssystem grob
- created_at
- last_seen_at
- revoked_at

Keine aggressive Canvas-/Font-/Fingerprinting-Technik.

Ein Browserprofil kann technisch als eigener Geräteslot wirken.

## PM-DEV-003 — Registrierung

Beim ersten Pro-Aufruf auf unbekanntem Gerät:

- aktiven Lizenzstatus prüfen
- Anzahl aktiver Geräte prüfen
- wenn Slot frei: Registrierung anbieten
- nach Bestätigung Gerät registrieren
- dann Pro freigeben

## PM-DEV-004 — Limit erreicht

Bei 2/2:

- Pro-Zugriff auf neuem Gerät verweigern
- Nutzer sieht verständliche Meldung
- Hinweis auf Firmenadministrator
- kein Selbst-Reset durch normalen Mitarbeiter

## PM-DEV-005 — Resetrechte

Gerät darf entfernt/revoked werden durch:

- Firmenadministrator
- netstyle Support mit Recht
- netstyle Superadmin

Nicht durch normalen Pro-Benutzer.

## PM-DEV-006 — Audit

Geräteanlage, Geräte-Reset und Revoke werden auditiert.

---

# 7. Reminder und Ablauf

## PM-REM-001 — E-Mail Reminder T−60

60 Tage vor Lizenzablauf:

- genau eine Reminder-E-Mail
- Empfänger: Lizenzinhaber optional + Firmenadmin zwingend für Firmenkunden
- Reminder-Datensatz erstellen
- sent_at/status/error protokollieren
- Idempotenz sicherstellen

## PM-REM-002 — E-Mail Reminder T−30

30 Tage vor Ablauf:

- zweite Reminder-E-Mail
- gleicher Nachweis wie T−60

## PM-REM-003 — Portal-/Pro-Warnung

Zusätzlich:

- ab T−60 dezenter Hinweis
- ab T−30 deutlicher Warnbanner
- ab T−7 deutlicher In-App-Hinweis bei Anmeldung/Pro-Start
- T0: Pro-Zugriff sperren

## PM-REM-004 — Reminderkonfiguration

Reminder-Tage sind pro Produkt konfigurierbar.

Initial:

- reminder_1_days = 60
- reminder_2_days = 30
- critical_days = 7

---

# 8. Mollie und Zahlungsabwicklung

## PM-PAY-001 — Zahlungsanbieter

V1 verwendet Mollie.

PromptMaster speichert keine Kreditkarteninformationen.

## PM-PAY-002 — Checkout

Ablauf:

1. Produkt / Anzahl auswählen
2. Kunde/Firma validieren
3. aktuelle Preisversion bestimmen
4. Order + OrderItems erzeugen
5. Mollie Payment erstellen
6. Kunde zu Mollie weiterleiten
7. Rückkehrseite zeigt nur UI-Status
8. endgültige Freischaltung ausschließlich serverseitig nach verifiziertem Mollie-Status

## PM-PAY-003 — Webhook

Mollie Webhook:

- Event empfangen
- Request minimal speichern
- Payment-ID validieren
- aktuellen Status über Mollie API erneut abrufen
- idempotent verarbeiten
- Duplicate darf niemals doppelte Lizenzen erzeugen
- Verarbeitung in Transaktion
- Event/Audit protokollieren

## PM-PAY-004 — Payment States

Mindestens:

- created
- open
- pending
- paid
- failed
- canceled
- expired
- refunded_partial
- refunded_full
- chargeback
- chargeback_reversed

Interne Zustände werden sauber auf Mollie-State gemappt.

## PM-PAY-005 — Lizenzfreischaltung

Nur `paid` erzeugt/aktiviert bezahlte Lizenzanzahl.

Jede gekaufte Lizenz erhält:

- eigene UUID/Lizenznummer
- own `valid_from`
- own `valid_until`

## PM-PAY-006 — keine eigene Rechnungsengine

PromptMaster erzeugt:

- keine eigenen Rechnungsnummern
- keine eigenen Rechnungs-PDFs
- keine eigenen Gutschriftdokumente

Rechnungs-/Belegprozess wird über Mollie bzw. dessen dafür vorgesehenen Funktionen abgewickelt.

PromptMaster speichert nur erforderliche Referenzen/Statusdaten.

---

# 9. Refunds

## PM-REF-001 — taggenaue Erstattung

Nutzungsregel:

- Lizenzdauer = 365 Tage
- genutzte Tage werden berechnet
- ungenutzte Resttage werden erstattet

Grundformel:

`refund = paid_gross_amount * remaining_days / 365`

auf Cent kaufmännisch gerundet.

## PM-REF-002 — Refund-Vorschau

Vor Auslösung zeigt netstyle Backend:

- Lizenz
- Kaufdatum
- Lizenzstart
- aktuelles Datum
- genutzte Tage
- Resttage
- bezahlter Preis
- berechneter Refund
- resultierender Lizenzstatus

## PM-REF-003 — Durchführung

Refund:

- nur berechtigte netstyle Rolle
- Bestätigungsdialog
- optional Begründung
- Mollie Refund API
- Status nach Webhook/API bestätigen
- Lizenz danach terminieren/revoken
- Sessions invalidieren
- AuditEvent

## PM-REF-004 — Teilrefund mehrerer Seats

Refund erfolgt lizenzbezogen.

Bei Bestellung mit mehreren Seats muss explizit ausgewählt werden, welche Lizenz(en) refundiert werden.

---

# 10. Chargeback

## PM-CB-001

Meldet Mollie Chargeback:

- betroffene Lizenz(en) → `payment_review` / vorläufig gesperrt
- kein Löschen von Kundendaten
- Firmenadmin informieren
- netstyle Dashboard Warnung
- AuditEvent

## PM-CB-002

Bei Chargeback-Reversal:

- Status erneut bewerten
- Lizenz ggf. reaktivieren
- AuditEvent

---

# 11. Authentifizierung und 2FA

## PM-AUTH-001

E-Mail + Passwort.

## PM-AUTH-002

E-Mail-Verifikation erforderlich für Kauf/Pro.

## PM-AUTH-003 — 2FA Pflicht

Pflicht für:

- Firmenadministrator
- netstyle Superadmin
- netstyle Vertrieb/Support
- netstyle Technik/Operations

Normaler Pro-Benutzer:

- V1 optional
- System vorbereitet für spätere Pflicht

## PM-AUTH-004 — TOTP

V1:

- TOTP Authenticator Apps
- Recovery Codes
- geprüfte Bibliothek, keine eigene Kryptografie
- Recovery Codes gehasht speichern
- einmalig nutzbar

## PM-AUTH-005 — Session Security

- Secure
- HttpOnly
- SameSite
- Sessionrotation nach Login/Privilege Change
- Sessioninvalidate bei Passwortwechsel
- Sessioninvalidate bei relevanten Security-Aktionen
- Idle-/Absolute Timeout konfigurierbar

## PM-AUTH-006 — Brute Force

- Rate Limiting
- Login Throttling
- temporäre Sperrlogik
- Audit / Security Log

---

# 12. Kundenportal

## PM-PORTAL-001 — Routing

Eigene Unterseiten, keine Endlosseite.

Mindestens:

- `/portal/dashboard/`
- `/portal/team/`
- `/portal/team/invitations/`
- `/portal/licenses/`
- `/portal/licenses/<uuid>/`
- `/portal/licenses/renew/`
- `/portal/devices/`
- `/portal/orders/`
- `/portal/company/`
- `/portal/profile/`
- `/portal/security/`
- `/portal/help/`

## PM-PORTAL-002 — Dashboard

Zeigt:

- Lizenzanzahl gesamt
- vergeben
- frei
- Ablaufwarnungen
- Geräteauslastung
- Team-Kurzliste
- freie Lizenz-Hinweise
- offene Zahlungsprobleme nur bei Handlungsbedarf
- Unternehmensdatenwarnung nur bei Bedarf
- PromptMaster Pro starten, sofern eigener User aktive Lizenz besitzt

## PM-PORTAL-003 — Firmenadmin ohne eigene Pro-Lizenz

Firmenadmin darf Portal verwalten, ohne selbst Pro-Seat zu belegen.

PromptMaster-Startbutton wird nur gezeigt, wenn eigene gültige Pro-Zuweisung besteht.

## PM-PORTAL-004 — Team

Funktionen:

- Liste
- Suche
- Statusfilter
- Benutzer einladen
- Einladung erneut senden
- Einladung widerrufen
- Lizenz zuweisen
- Lizenz freigeben
- Geräte anzeigen
- Benutzer deaktivieren
- Benutzer löschen

## PM-PORTAL-005 — Lizenzen

Funktionen:

- eigene individuelle Lizenzzeilen
- Lizenz-ID
- Produkt
- Zuweisung
- valid_from
- valid_until
- Resttage
- Status
- Reminderstatus
- Verlängerung
- Zuweisung ändern

## PM-PORTAL-006 — Geräte

- Benutzer gruppiert
- max 2 je Pro-Nutzer
- Gerätename
- OS grob
- Browserfamilie
- created_at
- last_seen_at
- revoke durch Firmenadmin

## PM-PORTAL-007 — Bestellungen/Zahlungen

Zeigt:

- Order-Nummer
- Datum
- Produkt
- Menge
- Betrag
- Paymentstatus
- Mollie Payment Reference
- zugehörige Lizenz-IDs

Keine eigene Rechnungs-PDF-Logik.

## PM-PORTAL-008 — Unternehmen

Firmenadmin kann verwalten:

- Stammdaten
- Adresse
- Steuerfelder
- Kontakt
- Firmenadminübertragung

## PM-PORTAL-009 — Support

Kontaktformular:

Kategorien:

- Lizenz
- Zahlung
- Benutzer
- Gerät
- Technisches Problem
- Datenschutz
- Sonstiges

Automatischer Kontext:

- Kunde
- Unternehmen
- User-ID
- ggf. Lizenz-ID
- Zeitpunkt

Keine unnötigen sensitiven Daten mitsenden.

V1 kein Ticketsystem.

---

# 13. netstyle Admin-Backend

## PM-ADMIN-001 — Grundsatz

Eigenes Admin-Frontend.

Django Admin darf intern als technische Fallback-/Datenpflegeoberfläche existieren, ist aber nicht das primäre netstyle-Frontend.

## PM-ADMIN-002 — Routing

Mindestens:

- `/ns-admin/`
- `/ns-admin/customers/`
- `/ns-admin/customers/<uuid>/`
- `/ns-admin/customers/<uuid>/users/`
- `/ns-admin/customers/<uuid>/licenses/`
- `/ns-admin/customers/<uuid>/devices/`
- `/ns-admin/customers/<uuid>/orders/`
- `/ns-admin/customers/<uuid>/payments/`
- `/ns-admin/licenses/`
- `/ns-admin/licenses/<uuid>/`
- `/ns-admin/orders/`
- `/ns-admin/payments/`
- `/ns-admin/products/`
- `/ns-admin/products/<uuid>/`
- `/ns-admin/email/templates/`
- `/ns-admin/email/log/`
- `/ns-admin/mollie/`
- `/ns-admin/mollie/events/`
- `/ns-admin/statistics/`
- `/ns-admin/ops/`
- `/ns-admin/ops/services/`
- `/ns-admin/ops/database/`
- `/ns-admin/ops/backups/`
- `/ns-admin/ops/restore-tests/`
- `/ns-admin/ops/alerts/`
- `/ns-admin/api/`
- `/ns-admin/legal/`
- `/ns-admin/audit/`
- `/ns-admin/users/`
- `/ns-admin/roles/`
- `/ns-admin/settings/`

Keine zentrale Endlosseite.

## PM-ADMIN-003 — Dashboard

Bereiche:

- Kunden gesamt
- aktive Lizenzen
- Ablauf <30
- Ablauf <60
- Umsatz 30 Tage
- letzte Bestellungen
- Produktmix
- Umsatzentwicklung
- fehlgeschlagene Zahlungen
- Chargebacks
- Kontaktanfragen
- Systemstatus kompakt
- Backupstatus
- Integrationsstatus

## PM-ADMIN-004 — Kundendetail

Eigene Tabs/Subroutes:

- Übersicht
- Unternehmen
- Benutzer
- Lizenzen
- Geräte
- Bestellungen
- Zahlungen
- E-Mail-Historie
- Datenschutz
- Audit

## PM-ADMIN-005 — Read-only Kundenportal-Vorschau

Support darf – mit entsprechender Berechtigung – eine read-only Darstellung der Kundenportal-Sicht öffnen.

Keine Session-Impersonation in V1.

---

# 14. Enterprise DataGrid Standard

Dieser Standard gilt verbindlich für **jede tabellarische Listenansicht**, sofern fachlich sinnvoll.

## PM-GRID-001 — serverseitig

Nie vollständige Listen clientseitig laden.

Sortierung, Suche, Filter und Pagination serverseitig.

## PM-GRID-002 — Standardpage

Default:

- 50 Datensätze

Auswahl:

- 25
- 50
- 100
- 250

Anzeige:

`1–50 von 5.284`

## PM-GRID-003 — Navigation

- erste Seite
- vorherige Seite
- nummerierte Seiten sinnvoll
- nächste Seite
- letzte Seite

Für sehr große Eventtabellen darf Cursor-/Keyset-Pagination verwendet werden.

## PM-GRID-004 — Sortierung

Klick auf sortierbaren Spaltenkopf:

1. ASC
2. DESC
3. optional zurück auf Default über Reset

Aktive Sortierung sichtbar.

Nur whitelisted DB-Felder dürfen sortiert werden.

## PM-GRID-005 — Suche

- serverseitig
- debounce ca. 300 ms
- Enter sofort
- Normalisierung
- keine unbounded Wildcard-Abfrage ohne Indexstrategie

## PM-GRID-006 — Filter

- status
- Produkt
- Datum
- Kundentyp
- Zahlungsstatus
- Lizenzstatus
- Rollen etc. abhängig vom Modul

Aktive Filter als Chips sichtbar.

## PM-GRID-007 — Zurücksetzen

Sobald Sortierung/Filter/Suche vom Default abweichen:

**Button „Zurücksetzen“ anzeigen.**

Reset setzt:

- Filter
- Suche
- Sortierung
- Page
- optional sichtbare Spalten auf Default

zurück.

## PM-GRID-008 — URL State

Filter/Sortierung/Page müssen in Query-Parametern stehen.

Beispiel:

`?q=muster&status=active&sort=company_name&dir=asc&page=4&page_size=50`

Deep Links müssen funktionieren.

## PM-GRID-009 — Spalten

Desktop:

- konfigurierbare sichtbare Spalten
- Default-Set je Tabelle
- Spaltenbreite responsive
- keine horizontalen Monsteransichten auf Mobile

V1.1 optional: persönliche Saved Views.

## PM-GRID-010 — Aktionen

Aktionen:

- echte Buttons oder klarer Action-Menu-Button
- keine nackten Textlinks für primäre Aktionen
- destructive Aktionen farblich und semantisch eindeutig
- Berechtigungen serverseitig prüfen

## PM-GRID-011 — Bulk Actions

Nur wo sinnvoll:

- mehrere Lizenzen auswählen
- Export
- ggf. Reminder/Statusoperationen

Keine gefährliche Massenaktion ohne Bestätigung.

## PM-GRID-012 — Export

CSV-Export:

- aktueller Filterzustand
- Permission Check
- Audit bei sensitiven Exporten

Große Exporte als Hintergrundjob.

## PM-GRID-013 — Zustände

Jede Liste besitzt:

- Loading
- Empty
- Error
- No Search Results
- Permission Denied

## PM-GRID-014 — Mobile

Smartphone:

- Card-Darstellung
- wichtigste 3–5 Felder
- „Öffnen/Verwalten“
- keine 1500px-Tabelle erzwingen

---

# 15. Globale Suche

## PM-SEARCH-001

netstyle Topbar:

Suche mindestens nach:

- Kundennummer
- Firmenname
- Person
- E-Mail
- Lizenz-ID
- Bestellnummer
- Mollie Payment ID

Ergebnis gruppiert nach Objektart.

## PM-SEARCH-002

PostgreSQL Indizes und ggf. `pg_trgm` für geeignete Suchfelder.

Keine Volltabellenscans bei erwartbarer Last.

---

# 16. netstyle Rollen und Berechtigungen

## PM-RBAC-001

Generische Modelle:

- Role
- Permission
- RolePermission
- UserRole

Keine dauerhafte Hardcodierung der Rechte.

## PM-RBAC-002 — Seed Rollen

### Superadmin
Alles.

### Vertrieb / Support

Mindestens:

- Kunden lesen/bearbeiten
- Benutzer verwalten
- Lizenzstatus lesen
- Zuweisung verwalten
- Geräte resetten
- Bestellungen/Zahlungsstatus lesen
- Supportkontakt bearbeiten
- Verlängerungsinformationen
- kein Secretzugriff
- keine Backup-Löschung
- keine Rollenadministration

### Technik / Operations

Mindestens:

- Ops Dashboard
- Monitoring
- Dienste
- Datenbankstatus
- Backupstatus
- Restore-Tests
- Logs
- API/Integrationen
- keine Preisänderung
- keine Mollie-Secrets
- keine geschäftlichen Refunds ohne Zusatzrecht

## PM-RBAC-003

Spätere Rollen ohne Codeumbau:

- Geschäftsführung
- Buchhaltung
- Auditor
- Read Only
- weitere

---

# 17. Produkte und Entitlements

## PM-PRODUCT-001

Product:

- UUID
- code eindeutig
- name
- description
- active
- visible
- purchasable
- default_license_days
- default_device_limit
- reminder_1_days
- reminder_2_days
- critical_warning_days
- created_at
- updated_at

## PM-PRODUCT-002

ProductPrice:

- Product
- type: new_purchase / renewal
- gross_amount
- net_amount optional berechnet/gespeichert nach Steuerlogik
- currency
- valid_from
- valid_until nullable
- active

## PM-PRODUCT-003

Feature / Entitlement:

- generische Feature-Codes
- Produkt ↔ Feature Zuordnung
- später für Ultra/Premium etc.
- Pro-Zugriff basiert serverseitig auf Entitlements

---

# 18. Datenmodell — Kernobjekte

Mindestens folgende Django Apps:

- accounts
- companies
- catalog
- orders
- payments
- licenses
- devices
- notifications
- support
- legal
- audit
- ops
- integrations
- core

## PM-DATA-001 — Primärschlüssel

Geschäftsobjekte verwenden UUID.

Menschenlesbare Nummern zusätzlich:

- customer_number
- license_number
- order_number

## PM-DATA-002 — Zeitstempel

Alle relevanten Modelle:

- created_at
- updated_at

Geschäftsereignisse zusätzlich immutable event timestamp.

## PM-DATA-003 — Soft Delete

Nicht pauschal für alle Tabellen.

- User: deaktivieren/anonymisieren nach Policy
- Company: Status/Löschworkflow
- AuditEvents: nicht normal löschbar
- PaymentEvents: Retention-basiert
- Geräte: revoke statt Hard Delete während notwendiger Historie

## PM-DATA-004 — Constraints

DB Constraints für:

- eindeutige E-Mail
- Produktcode
- Nummern
- max. einen aktiven Company Admin in V1 (durch Business Validation + transaktionale Sperre)
- keine überlappenden Preisversionen gleichen Typs, soweit technisch sinnvoll
- License valid_until > valid_from
- positive Beträge
- idempotency keys eindeutig

---

# 19. Order / Payment Modell

## Order

- UUID
- order_number
- customer / company
- billing snapshot JSON/strukturierte Felder
- status
- currency
- gross_total
- tax_total
- created_at

## OrderItem

- order
- product
- quantity
- unit_gross
- unit_net optional
- tax_rate snapshot
- product_name snapshot
- price_version reference

## Payment

- order
- provider
- provider_payment_id
- status
- amount
- currency
- method
- paid_at
- failed_at
- raw status metadata minimal

## MollieEvent

- provider event/payment ID
- received_at
- processed_at
- status
- idempotency key/hash
- error
- retry_count

---

# 20. E-Mail und Notifications

## PM-MAIL-001 — Staging

Mailpit.

Keine echten Kundenmails in Default-Staging.

## PM-MAIL-002 — Production

MailProvider-Abstraktion.

Bevorzugter Provider:

- Microsoft 365 / Microsoft Graph

Austauschbar ohne Businesslogikänderung.

## PM-MAIL-003 — Vorlagen

Mindestens:

- E-Mail-Verifikation
- Passwortreset
- Einladung
- Einladung erneut
- Zahlung bestätigt
- Zahlung fehlgeschlagen
- T−60
- T−30
- Lizenz abgelaufen
- Lizenz verlängert
- Refund bestätigt
- Chargeback / Zahlung prüfen
- Kontaktformular Eingangsbestätigung

## PM-MAIL-004 — Logging

EmailMessage:

- template
- recipient
- related object IDs
- queued_at
- sent_at
- status
- provider reference
- error code/message gekürzt
- retry_count

Keine sensitiven Secrets im Log.

---

# 21. Background Jobs

## PM-JOB-001

Celery Worker für:

- E-Mail
- Reminder
- Exporte
- Mollie Nachverarbeitung/Retry
- Reports/Aggregationen
- Systemwarnungen
- Backupstatus-Aufbereitung
- Retention Jobs

## PM-JOB-002

Celery Beat für:

- tägliche Reminderprüfung
- regelmäßige Alertprüfung
- Retention
- Health Snapshot/Aggregate
- geplante Housekeeping Jobs

## PM-JOB-003

Redis dient als interner Broker/Cache.

Redis nicht öffentlich exponieren.

---

# 22. Operations / System & Betrieb

## PM-OPS-001 — Dashboard

Eigene netstyle Unterseite.

Zeigt mindestens:

- Systemstatus
- CPU aktuell
- CPU 10-Min-Ø
- RAM gesamt/verwendet/frei
- Disk gesamt/verwendet/frei
- Disk %
- freie Inodes
- Uptime
- Load Average
- OS-Version
- Docker-Version
- App-Version
- Git Commit
- letztes Deployment
- PostgreSQL Status
- DB-Größe
- DB Connections
- Workerstatus
- Queue/failed jobs
- Caddy
- Mollie
- Mail
- Operations API
- Backup
- Restore-Test

## PM-OPS-002 — technische Datenerhebung

V1 vorgesehen:

- Prometheus
- Node Exporter
- cAdvisor
- PostgreSQL Exporter
- eigene Django Health/Business Metrics

Monitoringdienste nur intern.

Django erhält keinen uneingeschränkten Docker Socket.

## PM-OPS-003 — Warnschwellen

Initial konfigurierbar:

- Disk warning 80 %
- Disk critical 90 %
- RAM warning 80 %
- RAM critical 90 %
- CPU warning >80 % über 10 Minuten
- Backup warning >8 h
- Backup critical >24 h
- Restore Test warning >35 Tage
- Container unhealthy sofort
- wiederholter Mollie-Webhook-Fehler
- Mail-/Workerfehler

Keine Schwelle als unveränderbarer Hardcode.

---

# 23. Backup und Restore

## PM-BACKUP-001

PostgreSQL:

- automatischer logischer Dump mindestens alle 6 Stunden

Anwendungsdaten:

- mindestens täglich

Konfigurations-/Deploymentdaten:

- versioniert in Git, Secrets separat
- zusätzliche Sicherung bei relevanten Änderungen

## PM-BACKUP-002

Backups verschlüsselt auf externen Storage.

Nicht ausschließlich auf demselben VPS.

Ziel S3-kompatibel.

Provider wird vor Production festgelegt.

## PM-BACKUP-003 — initiale Retention

Technischer Default:

- 14 Tagesstände
- 8 Wochenstände
- 6 Monatsstände

Rechtliche Retention ist davon getrennt.

## PM-BACKUP-004 — Restore Test

Mindestens monatlich automatisiert:

1. Backup auswählen
2. temporären PostgreSQL Testcontainer starten
3. Restore
4. Integritätschecks
5. Ergebnis protokollieren
6. Testcontainer löschen

Dashboard zeigt:

- letzter Test
- Ergebnis
- Dauer
- verwendetes Backup

---

# 24. Operations API / Techniker-Dashboard Connector

## PM-API-001 — Versionierung

`/api/v1/`

## PM-API-002 — Ops Endpoints

Mindestens:

- `GET /api/v1/ops/health`
- `GET /api/v1/ops/system`
- `GET /api/v1/ops/storage`
- `GET /api/v1/ops/database`
- `GET /api/v1/ops/services`
- `GET /api/v1/ops/backups`
- `GET /api/v1/ops/integrations`
- `GET /api/v1/ops/maintenance-snapshot`

## PM-API-003 — Service Account

Späteres Techniker-Dashboard:

- Service Account: z. B. `technikerportal-maintenance`
- Scope: `ops.read`
- keine Kundenrechte
- keine Zahlungsrechte
- keine Secrets
- keine Schreibrechte

## PM-API-004 — Token Security

Service Tokens:

- mindestens 256 Bit Entropie
- nur einmal vollständig anzeigen
- serverseitig nur Hash
- Ablauf optional/konfigurierbar
- revoke
- rotation
- last_used_at
- optional IP-Allowlist später

## PM-API-005 — Maintenance Snapshot

Snapshot enthält mindestens:

- timestamp
- app version
- CPU
- RAM
- Disk
- DB-Größe
- DB Status
- Service Status
- Backup Status
- letzter Restore-Test
- Mollie Status
- Mail Status
- Uptime

Techniker-Portal speichert später diesen Wert als Wartungssnapshot.

---

# 25. Datenschutz / Recht

## PM-LEGAL-001

LegalDocument:

- type
- version
- valid_from
- content/file
- active

Typen mindestens:

- AGB
- Datenschutz
- Widerruf
- Lizenzbedingungen

## PM-LEGAL-002

LegalAcceptance:

- User
- Dokument
- Version
- accepted_at
- technischer Nachweis
- ggf. Order

Nicht nur boolean `agb=True`.

## PM-LEGAL-003 — Verbraucher

System unterstützt Privatkunden technisch.

Erforderliche Verbraucher-/Widerrufstexte werden vor Go-live juristisch validiert.

## PM-LEGAL-004 — Löschung

Löschworkflow:

1. Anfrage
2. Identitäts-/Statusprüfung
3. Konto deaktivieren
4. Sessions invalidieren
5. Device Tokens revoken/löschen
6. nicht mehr erforderliche personenbezogene Daten löschen/anonymisieren
7. gesetzlich erforderliche Daten separat/minimiert weiter aufbewahren
8. nach Frist endgültig löschen

## PM-LEGAL-005 — Retention

RetentionPolicy konfigurierbar nach Datenklasse.

Exakte gesetzliche Werte vor Production juristisch/steuerlich validieren.

Technische Logs dürfen eigene kurze Retention haben.

---

# 26. Audit Logging

## PM-AUDIT-001

Geschäftskritische Aktionen erzeugen Append-only AuditEvents.

Felder:

- event_id
- timestamp
- actor_user
- actor_role
- IP
- user agent grob
- action code
- object type
- object UUID
- previous values redacted
- new values redacted
- correlation_id

## PM-AUDIT-002 — Pflichtaktionen

Mindestens auditieren:

- Produkt-/Preisänderung
- Rollenänderung
- 2FA Reset
- Company Admin Transfer
- Lizenzzuweisung/freigabe
- Lizenz sperren/entsperren
- Gerät revoke
- Refund
- Chargeback Statusänderung
- Mollie-Konfiguration
- Mail-Konfiguration
- Service Account Create/Revoke
- Backup-/Restore-relevante Adminaktionen
- LegalDocument Aktivierung

Keine Secrets in Auditwerten.

---

# 27. Responsive Design / UI Standard

## PM-UI-001 — Desktop

Desktop primäre Arbeitsform fürs netstyle Backend.

- volle Sidebar
- DataGrid
- KPIs
- Charts
- Detailtabs

## PM-UI-002 — Tablet

- einklappbare Sidebar
- 2-Spalten-KPIs
- Tabellen reduzieren sinnvolle Spalten
- Actions erhalten

## PM-UI-003 — Smartphone

Kundenportal vollständig nutzbar.

netstyle:

- Status prüfen
- Kunde suchen
- Lizenz ansehen
- Geräte resetten, sofern erlaubt
- Warnungen prüfen

Komplexe Produkt-/Preis-/Rollenpflege bleibt Desktop-orientiert, muss aber ohne kaputtes Layout rendern.

## PM-UI-004 — Komponenten

Zentrales Designsystem für:

- AppShell
- Sidebar
- Topbar
- Buttons
- FormFields
- Cards
- KPI Cards
- DataGrid
- Mobile Cards
- Tabs
- Badges
- Alerts
- Modal/Dialog
- Toast
- Empty State
- Loading State
- Error State
- Pagination
- FilterBar
- ResetButton
- ConfirmDialog

Keine individuellen Buttonvarianten je Screen.

---

# 28. Sicherheit

## PM-SEC-001 — externe Ports

Public:

- 80 → Redirect
- 443 → HTTPS

Nicht public:

- PostgreSQL 5432
- Redis 6379
- Prometheus
- Exporter
- Django intern
- Celery

## PM-SEC-002 — Caddy

Reverse Proxy + TLS.

## PM-SEC-003 — Django Production

- DEBUG=False
- SECRET_KEY extern
- ALLOWED_HOSTS
- CSRF Trusted Origins
- Secure Cookies
- HSTS nach erfolgreichem Staging
- X-Content-Type-Options
- Referrer Policy
- CSP soweit mit Frontend kompatibel
- `manage.py check --deploy`

## PM-SEC-004 — Secrets

Keine Secrets im Repository.

Staging/Production separate Secretsets.

Mollie, DB, Mail etc.:

- Environment/Docker secrets
- Admin UI zeigt redacted values
- Änderung auditiert

## PM-SEC-005 — Authorization

Jede View/API:

- serverseitiger Permission Check
- tenant scoping
- kein Vertrauen in IDs aus Client
- IDOR Tests

## PM-SEC-006 — Input/Uploads

- serverseitige Validation
- Größenlimits
- MIME/Extension Prüfung wo Uploads existieren
- kein ausführbarer Uploadpfad

## PM-SEC-007 — Dependency Security

CI:

- Dependency Audit
- Python security checks
- Container image scan soweit praktikabel

---

# 29. Infrastruktur / Docker Compose

## PM-INFRA-001 — Container

V1 Staging/Production Stack:

- caddy
- web (Django + Gunicorn)
- postgres
- redis
- worker (Celery)
- beat (Celery Beat)
- mailpit nur Staging
- prometheus
- node-exporter
- cadvisor
- postgres-exporter
- backup

## PM-INFRA-002 — Networks

Mindestens:

- edge
- app
- data
- monitor

Prinzip: least connectivity.

## PM-INFRA-003 — Persistent Volumes

- postgres data
- caddy data/config
- prometheus data optional nach Retention
- app media falls erforderlich
- backup cache/config

## PM-INFRA-004 — Healthchecks

Für alle kritischen Container.

Compose Dependencies nach Health, nicht nur Startreihenfolge.

---

# 30. Technologie-Baseline

Für Phase 2 initial:

- Ubuntu 24.04 LTS Host
- Docker Engine + Docker Compose Plugin
- Django **5.2 LTS**, jeweils aktueller Security-Patch der 5.2-Reihe zum Buildzeitpunkt
- Python 3.14 oder unterstützte stabile Version nach Kompatibilität aller Dependencies
- PostgreSQL 18, aktueller Minor-Patch
- Redis als interner Broker/Cache
- Celery 5.6.x
- Caddy
- Prometheus + Exporter
- restic + pg_dump für Backup
- Git / GitHub

Keine automatische Major-Version-Anhebung ohne Test/Freigabe.

---

# 31. Staging / Production

## PM-ENV-001 — Development

lokal / Entwicklerumgebung.

## PM-ENV-002 — Staging

Privater IONOS VPS.

- echte Subdomain
- HTTPS
- Mollie Test Mode
- Mailpit Default
- synthetische Testdaten
- niemals echte Production-Secrets

## PM-ENV-003 — Production

später separater Firmen-VPS.

- Production-Domain
- Mollie Live
- produktiver MailProvider
- externe Backups
- Monitoring Alerts
- keine Debugtools öffentlich

## PM-ENV-004 — Portabilität

Gleiche Images/Compose-Struktur.

Unterschied:

- Secrets
- Domains
- Provider Keys
- Ressourcenlimits
- Staging-only Dienste

---

# 32. Repository-Struktur

Ziel:

```text
promptmaster/
├── compose.yaml
├── compose.staging.yaml
├── compose.production.yaml
├── Dockerfile
├── Caddyfile
├── .env.example
├── .gitignore
├── README.md
├── SPEC.md
├── AGENTS.md
├── backend/
│   ├── config/
│   ├── apps/
│   │   ├── accounts/
│   │   ├── companies/
│   │   ├── catalog/
│   │   ├── orders/
│   │   ├── payments/
│   │   ├── licenses/
│   │   ├── devices/
│   │   ├── notifications/
│   │   ├── support/
│   │   ├── legal/
│   │   ├── audit/
│   │   ├── ops/
│   │   ├── integrations/
│   │   └── core/
│   ├── templates/
│   ├── static/
│   └── manage.py
├── frontend-assets/
├── monitoring/
├── backup/
├── scripts/
│   ├── bootstrap.sh
│   ├── deploy.sh
│   ├── update.sh
│   ├── backup.sh
│   ├── restore-test.sh
│   └── diagnose.sh
├── tests/
└── .github/workflows/
```

---

# 33. Bootstrap / Ein-Kommando-Installation

## PM-BOOT-001

Nach Docker/Git-Verfügbarkeit soll Deployment weitgehend über:

`./scripts/bootstrap.sh`

möglich sein.

Bootstrap:

1. OS/Architektur prüfen
2. Docker/Compose prüfen
3. Verzeichnisse/Rechte prüfen
4. `.env`/Secrets Voraussetzungen prüfen
5. fehlende sichere Standardsecrets generieren
6. Images build/pull
7. Networks/Volumes
8. PostgreSQL starten
9. Redis starten
10. Django Migrationen
11. collectstatic
12. Seed-Rollen/Permissions/Product Defaults
13. optional initialen Superadmin interaktiv/über env anlegen
14. Worker/Beat
15. Caddy
16. Monitoring
17. Backup-Service
18. Healthchecks
19. `check --deploy` in Production Mode Simulation
20. Statusbericht

Script muss bei Fehler abbrechen und verständliche Meldung liefern.

---

# 34. Deployment

## PM-DEPLOY-001

`deploy.sh`:

- Git/Release Version prüfen
- Backup vor schema-kritischem Deployment
- Images bauen
- Tests/Checks
- Migrationen
- Rolling/controlled restart auf Single Host
- Healthchecks
- bei Fehler klare Rollback-Anweisung

## PM-DEPLOY-002

App-Version und Git SHA im Admin Ops Dashboard sichtbar.

---

# 35. Git / GitHub

## PM-GIT-001

Private Repository.

Branches:

- `main` = freigegebener Stand
- `staging` = Staging
- `feature/*`

## PM-GIT-002 — CI

Mindestens:

- formatting/lint
- Django check
- migration check
- unit tests
- integration tests
- security/dependency checks
- Docker build
- optional seeded E2E smoke test

Kein Production Deploy bei roten Tests.

---

# 36. Performance und Skalierung

## PM-PERF-001

Zielgröße V1:

- 5.000+ Kunden ohne Architekturwechsel
- deutlich mehr Lizenz-/Eventdatensätze
- Testdaten mindestens 100.000 Datensätze für große Tabellen

## PM-PERF-002

Keine Listenabfrage lädt unbounded Daten.

## PM-PERF-003

DB-Indizes mindestens auf:

- customer_number
- company_name
- user email
- license_number
- license status
- valid_until
- product
- order_number
- provider payment ID
- created_at
- foreign keys

## PM-PERF-004

Dashboard-Aggregate dürfen gecacht/voraggregiert werden.

Keine teuren Full Aggregations bei jedem Seitenaufruf.

## PM-PERF-005

Richtziel Staging unter normaler Last:

- typische HTML/API-Antwort p95 < 500 ms ohne externe Providerlatenz
- Tabellenquery p95 < 500 ms bei realistischem Seed
- Operations Health Endpoint < 1 s

Diese Werte sind Engineering-Ziele, keine SLA-Zusage.

---

# 37. Observability

## PM-OBS-001

Structured Logs.

Mindestens:

- timestamp
- level
- service
- request/correlation ID
- user ID nur soweit nötig
- event code

Keine Secrets/Passwörter/Tokens.

## PM-OBS-002

Correlation ID über:

- Web Request
- Celery Task
- Mollie Event
- E-Mail
- Audit

soweit sinnvoll.

## PM-OBS-003

Admin Alerts:

- unhealthy service
- Backup zu alt
- Restoretest zu alt/fehlgeschlagen
- Disk/RAM/CPU threshold
- Mollie event retries
- Mail failures
- Worker queue problem
- DB unavailable

---

# 38. Tests

## PM-TEST-001 — Unit

Business Rules:

- 365 Tage
- Nachkauf separat
- Verlängerung vor Ablauf
- Verlängerung nach Ablauf
- Refund-Rechnung
- Reminder
- Geräte-Limit
- Invite 24 h
- Preisversionierung
- Company-Admin-Regel

## PM-TEST-002 — Integration

- Mollie webhook idempotent
- paid → richtige Anzahl Lizenzen
- duplicate paid → keine Duplikate
- failed → keine Lizenz
- refund
- chargeback
- Mail queue
- Celery Beat Reminder
- Ops API scopes

## PM-TEST-003 — Auth/Security

- IDOR
- Tenant Isolation
- Role Permissions
- 2FA
- invite token replay
- recovery code reuse
- device token revoke
- CSRF
- rate limit
- secret redaction

## PM-TEST-004 — DataGrid

Jede zentrale Liste:

- 0
- 1
- 49
- 50
- 51
- 5.000
- 100.000 Seed-Datensätze

Prüfen:

- Pagination
- Sortierung
- Filter
- Suche
- Reset
- Deep Link
- Export
- Performance

## PM-TEST-005 — Responsive

Breakpoints mindestens:

- Mobile ~360/390
- Tablet ~768
- Desktop ~1440
- Wide ~1920

## PM-TEST-006 — Backup

- Backup erzeugen
- Backup extern vorhanden
- Restore-Test
- Integritätsprüfung

## PM-TEST-007 — E2E Kernflow

1. Firma registriert
2. E-Mail bestätigt
3. Company Admin richtet 2FA ein
4. 5 Lizenzen kaufen
5. Mollie Test Paid
6. 5 License Records
7. Benutzer einladen
8. Invitation akzeptieren
9. Seat zuweisen
10. Device 1
11. Device 2
12. Device 3 blockiert
13. Pro startet
14. T−60 simulieren
15. T−30 simulieren
16. Ablauf simulieren
17. Verlängerung
18. Refund
19. Chargeback
20. Audit prüfen
21. Ops Dashboard
22. Maintenance Snapshot API

---

# 39. Acceptance Gates

## Gate A — Code Complete

- alle V1 Requirements implementiert
- keine kritischen TODOs

## Gate B — Tests

- Test Suite grün
- keine bekannten Critical/High Security Bugs
- Migrationen reproduzierbar

## Gate C — Staging

- HTTPS
- Mollie Test
- Mailpit
- E2E erfolgreich
- 100k Seed Performance
- Backup + Restoretest
- Responsive Prüfung

## Gate D — Codex Review

Codex erhält vollständiges Repository plus diese SPEC.

Review-Auftrag:

- Abweichungen von SPEC finden
- Securityprobleme
- Race Conditions
- Transaktionsprobleme
- fehlende Tests
- ineffiziente Queries/N+1
- Pagination
- Tenant Isolation
- idempotente Webhooks
- Secrets
- Docker/Deployment
- nur begründete Änderungen per PR

## Gate E — Human Review

Codex-Ergebnisse werden vor Merge geprüft.

## Gate F — Production Readiness

Vor Production zusätzlich:

- finaler Server
- Domain
- DNS
- Mollie Live Keys
- Mailprovider
- externer Backup Storage
- Rechtstexte
- Datenschutzprüfung
- Alert-Empfänger
- Restore dokumentiert
- Notfallzugang dokumentiert

---

# 40. Nicht-funktionale Anforderungen

## PM-NFR-001 — Wartbarkeit

- klare Django Apps
- Services für Businesslogik
- keine Businesslogik in Templates
- keine gigantischen Views
- wiederverwendbare DataGrid-/UI-Komponenten
- Type Hints soweit sinnvoll
- Docstrings bei nichttrivialer Businesslogik

## PM-NFR-002 — Transaktionen

Zahlung/Lizenz/Refund kritische Abläufe verwenden DB-Transaktionen und Row Locking, wenn Race Conditions möglich sind.

## PM-NFR-003 — Zeitzonen

Intern UTC.

UI Deutschland lokalisiert.

## PM-NFR-004 — Geld

Kein Float.

Decimal/Integer Minor Units.

## PM-NFR-005 — Accessibility

- Labels
- Keyboard
- Fokus
- semantische Buttons
- ausreichende Kontraste
- Status nicht ausschließlich über Farbe

## PM-NFR-006 — Browser

Aktuelle unterstützte Versionen:

- Chrome/Edge
- Firefox
- Safari mobile/desktop soweit relevant

---

# 41. Production Recht / externe Konfiguration — bewusst offen

Diese Punkte blockieren Phase 2 nicht, müssen aber vor Go-live final gesetzt werden:

- Production Domain
- Mollie Live Credentials
- Microsoft Graph App / produktive Mailadresse
- externer S3 Backup Provider
- endgültige AGB
- endgültige Datenschutztexte
- endgültige Widerrufs-/Verbrauchertexte
- finale steuerliche Requiredness-Regeln
- Monitoring Alert Empfänger

Phase 2 verwendet dafür Platzhalter/Testkonfiguration.

---

# 42. Definition „fertig“

V1 gilt als technisch fertig, wenn:

- Kundenportal vollständig in separaten Unterseiten funktioniert
- netstyle Backend vollständig in separaten Unterseiten funktioniert
- alle DataGrids Enterprise-Standard erfüllen
- Mollie Testflow funktioniert
- Lizenzen exakt 365-Tage-Regeln erfüllen
- Reminder T−60/T−30 funktionieren
- 2-Geräte-Regel funktioniert
- Company Admin / Invite / 2FA funktionieren
- Produkte/Preise konfigurierbar/historisiert sind
- Refund/Chargeback verarbeitet werden
- Ops Dashboard Daten liefert
- Backup + Restoretest funktioniert
- Ops API mit `ops.read` funktioniert
- Security-/Permissiontests grün sind
- Staging E2E grün ist
- Codex-Review durchgeführt und geprüft wurde

---

# 43. Phase-2-Codegenerierungsvertrag

Phase 2 darf keine Businessregel „kreativ interpretieren“.

Bei Unklarheit:

1. SPEC prüfen
2. jüngste Change-Spec prüfen
3. im Zweifel Implementierung konservativ blockieren statt Daten inkonsistent zu verändern

Phase 2 liefert:

- vollständiges Git-Repository
- Docker Compose
- Django Apps
- Templates/Static UI
- Migrationen
- Seed Commands
- Tests
- Bootstrap/Deploy/Backup/Restore-Test Scripts
- Monitoring-Konfiguration
- CI Workflow
- README
- AGENTS.md für Codex
- `.env.example`
- Staging-Konfiguration
- Production-Konfiguration ohne echte Secrets

---

# 44. Requirement-Index

## Produkt
PM-PROD-001 .. 003

## Preise/Lizenz
PM-PRICE-001 .. 003  
PM-LIC-001 .. 004

## Company/User
PM-COMP-001 .. 004  
PM-USER-001

## Einladungen
PM-INV-001 .. 004

## Assignment
PM-ASSIGN-001 .. 004

## Geräte
PM-DEV-001 .. 006

## Reminder
PM-REM-001 .. 004

## Payments
PM-PAY-001 .. 006

## Refund
PM-REF-001 .. 004

## Chargeback
PM-CB-001 .. 002

## Auth
PM-AUTH-001 .. 006

## Kundenportal
PM-PORTAL-001 .. 009

## netstyle Admin
PM-ADMIN-001 .. 005

## DataGrid
PM-GRID-001 .. 014

## Search
PM-SEARCH-001 .. 002

## Rollen
PM-RBAC-001 .. 003

## Produktengine
PM-PRODUCT-001 .. 003

## Daten
PM-DATA-001 .. 004

## Mail/Jobs
PM-MAIL-001 .. 004  
PM-JOB-001 .. 003

## Operations
PM-OPS-001 .. 003

## Backup
PM-BACKUP-001 .. 004

## API
PM-API-001 .. 005

## Legal
PM-LEGAL-001 .. 005

## Audit
PM-AUDIT-001 .. 002

## UI
PM-UI-001 .. 004

## Security
PM-SEC-001 .. 007

## Infrastruktur
PM-INFRA-001 .. 004

## Environment
PM-ENV-001 .. 004

## Bootstrap/Deploy/Git
PM-BOOT-001  
PM-DEPLOY-001 .. 002  
PM-GIT-001 .. 002

## Performance
PM-PERF-001 .. 005

## Observability
PM-OBS-001 .. 003

## Tests
PM-TEST-001 .. 007

## NFR
PM-NFR-001 .. 006

---

# 45. Schlussstatus

**FUNCTION FREEZE V1.0: FREIGABEFÄHIG FÜR PHASE 2**

Diese Spezifikation ist die verbindliche Grundlage für:

- Codegenerierung
- Datenbankmodell
- UI
- Docker
- Deployment
- Tests
- Codex Review
- Staging-Abnahme
- späteren Production Go-live

Neue Wünsche werden ab jetzt als versionierte Changes gegen diese SPEC geführt.
