Ja. Ich habe die Architektur noch einmal kritisch gegen eure aktuelle PromptMaster-Datei, aktuelle Frameworkstände, Three.js, Zahlungsabwicklung, Lizenzlogik, Authentifizierung und die deutsche E-Rechnungsentwicklung geprüft.

Eine Korrektur vorweg: Die Bibliothek heißt **Three.js**, nicht Tree.js. Three.js rendert aktuell über WebGL 2 und unterstützt Punktwolken direkt. Genau damit lässt sich der von dir beschriebene „Jarvis-Kopf“ aus tausenden leuchtenden Punkten bauen. citeturn173158search4turn173158search12

Das folgende Pflichtenheft würde ich als **verbindliche technische Basis** für die spätere Umsetzung verwenden.

:::writing{variant="document" id="58341" title="Pflichtenheft PromptMaster Commercial – Version 1.0"}
# Pflichtenheft PromptMaster Commercial
## Verkaufsplattform, Lizenzierung, Kundenportal und netstyle-Administration

**Projekt:** PromptMaster by netstyle  
**Dokumentstatus:** Technische Baseline V1.0  
**Stand:** 05.09.2026  
**Ziel:** Kommerzialisierung von PromptMaster Free und PromptMaster Pro, ohne die eigentliche PromptMaster-Produktlogik neu zu entwickeln.

---

# 1. Grundsatzentscheidung

PromptMaster wird künftig aus zwei grundsätzlich getrennten Ebenen bestehen:

### Ebene A – die bestehenden Produkte

- PromptMaster Free
- PromptMaster Pro

Diese Anwendungen bleiben hinsichtlich ihrer Prompt-Logik, Auswahlmechanismen und eigentlichen Bedienoberfläche unverändert.

Die aktuell vorliegende PromptMaster-Version bestätigt, dass die Anwendung vollständig browserseitig arbeitet: HTML, CSS und JavaScript erzeugen den Prompt lokal; PromptMaster selbst benötigt keine KI-API und verarbeitet die eingegebenen Inhalte nicht auf einem externen PromptMaster-Server. fileciteturn4file0

### Ebene B – die neue Commercial-Plattform

Neu entwickelt werden:

- Marketing-Website
- Three.js-Animation
- Produktvergleich
- Preis-/Lizenzrechner
- Checkout
- Payment
- Rechnungsprozess
- Registrierung
- Login
- Unternehmensverwaltung
- Benutzerverwaltung
- Lizenzverwaltung
- Geräte-/Session-Verwaltung
- Kundenportal
- netstyle-Adminportal
- Ablaufüberwachung
- Verlängerung
- E-Mail-Benachrichtigungen
- Audit-Logging
- Datenbank
- Backup
- Monitoring

---

# 2. Klare Abgrenzung

## Wird NICHT neu entwickelt

- Prompt-Generator
- Prompt-Bausteine
- Microsoft-Copilot-Auswahl
- Aufgaben
- Zielgruppen
- Schwerpunkte
- Ausgabeoptionen
- Qualitätsregeln
- Prompt-Kopieren-Funktion
- bestehendes PromptMaster-Produktdesign

Diese Komponenten werden als **Golden Master** eingefroren.

Vor Beginn der Commercial-Entwicklung wird für die endgültige Free- und Pro-Datei jeweils ein SHA-256-Hash erzeugt.

Beispiel:

```text
PromptMaster-Free-final.html
SHA256: ...

PromptMaster-Pro-final.html
SHA256: ...
```

Damit kann nach jeder Integration automatisch geprüft werden:

> Hat sich am eigentlichen Produkt irgendein Byte verändert?

Sollwert:

**Nein.**

---

# 3. Kritische technische Validierung

| Anforderung | Ergebnis |
|---|---|
| Bestehende HTML/JS-Anwendung weiterverwenden | ✅ vollständig möglich |
| Free ohne Datenbank nutzbar lassen | ✅ möglich |
| Pro nur nach Login freigeben | ✅ möglich |
| 12-Monats-Lizenzen | ✅ problemlos |
| automatische Sperre nach Ablauf | ✅ problemlos |
| automatische Verlängerungserinnerungen | ✅ problemlos |
| Verlängerung über Checkout | ✅ problemlos |
| Kunden können Seats selbst verwalten | ✅ problemlos |
| netstyle kann alle Kunden verwalten | ✅ problemlos |
| PayPal/Karte/SEPA integrieren | ✅ mit Payment Provider |
| Rechnung integrieren | ✅ möglich |
| E-Rechnungen vorsehen | ✅ möglich |
| Three.js-Jarvis-Gesicht | ✅ sehr gut geeignet |
| Mausbewegung beeinflusst Gesicht | ✅ möglich |
| responsive Smartphone-Version | ✅ möglich |
| physikalischen PC zweifelsfrei identifizieren | ❌ Browser können das nicht zuverlässig |
| Geräte-/Browserregistrierung begrenzen | ✅ möglich |
| Weitergabe eines Benutzerkontos absolut verhindern | ❌ technisch nicht 100 % beweisbar |
| Anzahl registrierter Geräte begrenzen | ✅ möglich |
| Pro-HTML vor einem berechtigten Benutzer absolut verbergen | ❌ grundsätzlich unmöglich |

Der letzte Punkt ist wichtig:

Wenn ein Browser PromptMaster Pro ausführen soll, muss der Browser HTML und JavaScript erhalten.

Ein berechtigter Benutzer kann theoretisch Browser-Entwicklertools verwenden und JavaScript speichern.

**Lizenzkontrolle ist möglich. Absoluter Quellcode-Kopierschutz einer vollständig clientseitigen Webanwendung ist nicht möglich.**

Eine echte technische Verlagerung der Promptlogik auf den Server würde dieses Problem lösen, würde aber gegen die Vorgabe verstoßen, PromptMaster selbst unverändert zu lassen.

Für V1 wird deshalb festgelegt:

> Lizenzschutz ja.  
> Quellcode-DRM nein.

Minifizierung/Obfuscation kann später als zusätzliche Hürde eingesetzt werden, ist aber kein Sicherheitsmechanismus.

---

# 4. Zielarchitektur

```text
                         INTERNET
                            │
                            ▼
                       HTTPS / TLS
                            │
                            ▼
                          CADDY
                 Reverse Proxy / TLS
                            │
             ┌──────────────┴──────────────┐
             │                             │
             ▼                             ▼
       DJANGO WEB APP               THREE.JS ASSETS
             │
    ┌────────┼───────────┐
    │        │           │
    ▼        ▼           ▼
Marketing   Portal   PromptMaster Gate
    │        │           │
Checkout   Admin         ▼
    │                  PRO HTML
    │
    ▼
Backend / Business Logic
    │
 ┌──┼───────────┬────────────┬─────────────┐
 │  │           │            │             │
 ▼  ▼           ▼            ▼             ▼
DB Auth       License       Mail         Mollie
 │             Engine       Worker       API
 ▼
PostgreSQL
```

---

# 5. Empfohlener Technologie-Stack

## 5.1 Backend

**Django 5.2 LTS**

Begründung:

Django bringt bereits mit:

- Benutzerverwaltung
- Authentifizierung
- Sessionverwaltung
- Rollen und Rechte
- Formularvalidierung
- CSRF-Schutz
- Datenbankzugriff
- Datenbankmigrationen
- E-Mail-Framework
- Admin-System
- Logging
- Testframework

Django 5.2 ist eine LTS-Version und wird bis April 2028 unterstützt. citeturn173158search10turn853059search1

Damit vermeiden wir die Entwicklung fundamentaler Sicherheitsfunktionen von Grund auf.

### Entscheidung

**Kein React/Next.js-Zwang.**

Für PromptMaster wäre das in V1 unnötige Komplexität.

Wir verwenden:

- Django Templates
- HTML5
- CSS
- Vanilla JavaScript
- Three.js

Damit passt die neue Plattform technisch wesentlich besser zu euren vorhandenen HTML/JavaScript-Produkten.

---

# 6. Datenbank

## Produktivdatenbank

**PostgreSQL 18**

PostgreSQL 18 ist aktuell unterstützt; die derzeitige Supportplanung läuft bis November 2030. citeturn853059search4

Die Datenbank enthält ausschließlich Commercial-Daten.

### Nicht gespeichert werden:

- Prompttexte
- Eingaben in PromptMaster
- kopierte Prompts
- ausgewählte PromptMaster-Schwerpunkte
- Microsoft-Copilot-Inhalte

Damit bleibt das bestehende Datenschutzprinzip erhalten:

> PromptMaster verarbeitet die eigentlichen Prompt-Inhalte weiterhin lokal im Browser.

---

# 7. Docker-Architektur

Produktionssystem:

```text
promptmaster-commercial/
│
├── docker-compose.yml
├── .env
│
├── caddy/
│
├── app/
│   └── Django
│
├── worker/
│   └── gleiche Django-Codebasis
│
├── postgres/
│
├── promptmaster/
│   ├── free/
│   └── pro/
│
├── static/
│   ├── three/
│   ├── css/
│   ├── js/
│   └── images/
│
├── backups/
│
└── tests/
```

Benötigte Container:

| Container | Aufgabe |
|---|---|
| caddy | HTTPS / Reverse Proxy |
| web | Django Anwendung |
| worker | zeitgesteuerte Jobs und E-Mails |
| postgres | Datenbank |

### Kein Redis in V1.

Für diese Plattform ist ein zusätzliches Redis-System zunächst unnötig.

Hintergrundjobs können über PostgreSQL und einen dedizierten Worker sauber abgewickelt werden.

---

# 8. Server

Die Plattform darf nicht direkt in einem internen netstyle-Produktionsnetz betrieben werden.

Empfehlung:

**separate öffentliche Linux-VM / DMZ-VM**

Erreichbar:

```text
Internet
   │
   ▼
Firewall
   │
443 / 80
   │
   ▼
PromptMaster VM
```

PostgreSQL erhält:

**keinen öffentlichen Port.**

Die Datenbank ist ausschließlich im internen Docker-Netz erreichbar.

Extern offen:

- TCP 443 HTTPS
- TCP 80 nur HTTPS-Redirect

SSH ausschließlich über:

- VPN
- Administrationsnetz
- oder eingeschränkte Quell-IP

---

# 9. Domainstruktur

Empfohlene Struktur:

```text
promptmaster.netstyle.de
```

Alternativ später eigene Domain.

URLs:

```text
/
 /free/
 /pro/
 /preise/
 /vergleich/
 /checkout/
 /login/
 /portal/
 /app/pro/
 /admin/
```

Keine komplizierte Subdomain-Landschaft in V1.

---

# 10. Öffentliche Website – Designkonzept

Die Marketingseite erhält bewusst ein anderes Erscheinungsbild als die eigentliche PromptMaster-Anwendung.

PromptMaster selbst bleibt sachlich.

Die Verkaufswebsite wird:

- dunkel
- hochwertig
- technisch
- futuristisch
- ruhig animiert
- netstyle-blau
- ohne „Gaming“-Optik
- ohne kitschige KI-Roboter

Die aktuelle PromptMaster-Version verwendet bereits die netstyle-nahe Farbwelt:

```text
#30399a
#0c71c3
#2ea3f2
```

fileciteturn4file0

Diese Farben werden für die Commercial-Website in ein dunkles Farbsystem überführt.

Beispielsweise:

```text
Hintergrund     #05070d
Flächen          #0b1018
netstyle Indigo  #30399a
netstyle Blau    #0c71c3
Highlight Blau   #2ea3f2
Text hell        #f5f7fa
Text sekundär    #9ba8b4
```

---

# 11. Three.js „Jarvis“-Hero

Die zentrale Animation wird mit **Three.js** realisiert.

Three.js unterstützt Punktgeometrien direkt über `BufferGeometry`, `Points` und `PointsMaterial`; der Renderer verwendet WebGL 2. citeturn173158search12turn173158search4

## Darstellung

Zentraler menschlicher Kopf.

Nicht fotorealistisch.

Bestehend aus:

- mehreren tausend Lichtpunkten
- Netzwerkverbindungen
- Tiefenwirkung
- blauen Partikeln
- Lichtnebel
- subtiler Datenbewegung

### Mausinteraktion

Mausposition wird in X/Y-Koordinaten umgerechnet.

Kopf reagiert:

```text
Maus links
→ Kopf dreht leicht nach links

Maus rechts
→ Kopf dreht leicht nach rechts

Maus oben
→ Blick hebt sich

Maus unten
→ Blick senkt sich
```

Maximale Rotation wird begrenzt.

Keine hektische Bewegung.

---

# 12. Weitere Interaktionen des Gesichts

## Hover „Free“

- Kopf bewegt sich leicht nach links
- Partikel werden etwas ruhiger
- Free-Bereich wird hervorgehoben

## Hover „Pro“

- Kopf bewegt sich leicht nach rechts
- Netzwerkdichte erhöht sich
- Partikel leuchten stärker
- Pro-Bereich erhält stärkere visuelle Tiefe

## Scrollen

Beim Scrollen können:

- Partikel auseinanderdriften
- Datenlinien entstehen
- Feature-Bereiche aus der Punktwolke hervorgehen

Die Animation darf jedoch niemals die Bedienung blockieren.

---

# 13. Performance-Fallback

WebGL darf nicht Voraussetzung für den Shop sein.

Deshalb:

```text
WebGL2 vorhanden
→ volle Animation

schwaches Mobilgerät
→ reduzierte Partikelzahl

prefers-reduced-motion
→ stark reduzierte Animation

kein WebGL
→ statischer Hero
```

Zielwerte:

Desktop:

**ca. 60 FPS**

ältere/mobile Geräte:

**mindestens ca. 30 FPS**

---

# 14. Öffentliche Navigation

Header:

```text
netstyle | PromptMaster

Funktionen
Free vs. Pro
Preise
FAQ

[PromptMaster Free]
[Anmelden]
```

---

# 15. Startseite – Buttons

## Button: „PromptMaster Free starten“

Route:

```text
/free/
```

Aktion:

Bestehendes PromptMaster Free wird geladen.

Keine Registrierung.

Keine Datenbankabfrage erforderlich.

---

## Button: „PromptMaster Pro entdecken“

Aktion:

Scroll zu:

```text
#pro
```

oder Vergleichsbereich.

Keine Anmeldung.

---

## Button: „Free & Pro vergleichen“

Aktion:

Scroll:

```text
#vergleich
```

---

## Button: „PromptMaster Pro kaufen“

Aktion:

```text
/checkout/?quantity=1
```

---

## Button: „Anmelden“

Aktion:

```text
/login/
```

---

# 16. Preisbereich

Darstellung:

```text
PromptMaster Pro

Benutzer

        [ – ]   8   [ + ]

Preis pro Benutzer/Jahr
XX,XX € netto

8 Benutzer
XXX,XX € netto

+ MwSt.
────────────
XXX,XX € brutto

[8 Lizenzen kaufen]
```

Preis wird **nicht im JavaScript fest programmiert**.

Preis stammt aus der Datenbank.

Dadurch kann netstyle später Preise ändern.

---

# 17. Preisberechnung

Geldbeträge werden niemals als JavaScript-Floating-Point-Werte gespeichert.

Intern:

```text
2399
```

entspricht:

```text
23,99 €
```

Speicherung erfolgt in Cent.

Bestellungen speichern immer einen Preis-Snapshot.

Wenn netstyle später den Preis ändert, darf eine alte Bestellung nicht verändert werden.

---

# 18. Checkout – V1-Geschäftsmodell

Empfehlung für V1:

**B2B Deutschland.**

Das reduziert erheblich:

- Umsatzsteuerkomplexität
- Verbraucherrecht
- Widerrufsprozesse
- EU-Reverse-Charge
- OSS-Themen

EU-/internationaler Verkauf kann später ergänzt werden.

---

# 19. Checkout Schritt 1 – Bestellung

Felder:

```text
Produkt:
PromptMaster Pro

Anzahl:
8

Laufzeit:
12 Monate

Preis:
...

[Zurück]
[Weiter]
```

### „–“

reduziert Anzahl.

Minimum:

```text
1
```

### „+“

erhöht Anzahl.

### „Weiter“

serverseitige Preisneuberechnung.

Clientpreis allein wird niemals akzeptiert.

---

# 20. Checkout Schritt 2 – Unternehmensdaten

Pflichtfelder:

- Firmenname
- Straße
- Hausnummer
- PLZ
- Ort
- Land
- Rechnungs-E-Mail
- Ansprechpartner
- E-Mail
- ggf. Telefonnummer

B2B zusätzlich:

- USt-ID optional/abhängig vom Fall
- Unternehmensnummer optional

Die Bestelldaten werden serverseitig validiert.

---

# 21. Checkout Schritt 3 – Administrator

Der Erstkäufer wird Kundenadministrator.

Felder:

```text
Vorname
Nachname
E-Mail-Adresse
```

Noch kein Passwort.

Nach erfolgreichem Kauf erhält er eine Aktivierungs-E-Mail.

---

# 22. Checkout Schritt 4 – Zahlungsmethode

Integration über Mollie.

Mollie unterstützt aktuell unter anderem:

- PayPal
- Kreditkarten
- SEPA-Überweisung
- SEPA-Lastschrift
- Apple Pay
- Google Pay citeturn173158search11


Welche Methoden tatsächlich angeboten werden, wird im Mollie-Konto konfiguriert.

Empfohlener Start:

- PayPal
- Kreditkarte
- SEPA-Überweisung
- Rechnung

SEPA-Lastschrift kann nach vollständigem Mandatstest aktiviert werden.

---

# 23. Zahlungsdaten

PromptMaster speichert niemals:

- Kreditkartennummer
- CVV
- vollständige Bankkartendaten
- PayPal-Passwort
- Onlinebanking-Zugangsdaten

Die Zahlung erfolgt im Hosted Checkout des Payment Providers.

Mollie beschreibt den Standardprozess als:

1. Payment erzeugen
2. Kunde zum Hosted Checkout schicken
3. Zahlungsstatus per Webhook verarbeiten citeturn173158search13


---

# 24. Payment-Webhook

Nach Zahlung:

```text
Mollie
   │
   ▼
Webhook
   │
   ▼
PromptMaster Backend
   │
   ▼
Payment erneut über Mollie API prüfen
```

Erst wenn Mollie tatsächlich:

```text
PAID
```

meldet, erfolgt Aktivierung.

Ein bloßer Browser-Redirect:

```text
/payment-success
```

aktiviert **niemals** eine Lizenz.

Das verhindert manipulierte „Erfolgreich bezahlt“-URLs.

Mollie empfiehlt ausdrücklich, nach einem Webhook den tatsächlichen Ressourcenstatus erneut abzurufen. citeturn173158search0

---

# 25. Webhook-Idempotenz

Ein Webhook kann mehrfach eintreffen.

Deshalb muss gelten:

```text
Payment ABC
bereits verarbeitet?

JA
→ nichts erneut erzeugen

NEIN
→ Zahlung verarbeiten
```

Es dürfen niemals durch doppelte Webhooks:

- doppelte Benutzer
- doppelte Seats
- doppelte Rechnungen
- doppelte Verlängerungen

entstehen.

---

# 26. Rechnungsstellung

Empfehlung:

**Nicht selbst programmieren.**

Mollie besitzt inzwischen eine Sales-Invoices-API und kann Rechnungen erstellen und an Kunden senden. Für Deutschland kann darüber auch E-Invoicing bzw. Peppol genutzt werden. citeturn302663search0turn302663search2

Das reduziert das Projekt erheblich.

Derzeit gelten in Deutschland Übergangsregeln zur E-Rechnung; bis Ende 2026 können Rechnungsaussteller grundsätzlich noch sonstige Rechnungen verwenden, bei bestimmten kleineren Unternehmen verlängert sich die Frist bis Ende 2027. Danach wird die strukturierte E-Rechnung im inländischen B2B-Bereich zunehmend zwingend. citeturn661439view1turn661439view3

Deshalb muss PromptMaster von Anfang an E-Rechnungsfähigkeit berücksichtigen.

---

# 27. Kauf auf Rechnung

Zwei Varianten:

## Variante A – Mollie Rechnung

Empfohlen.

Mollie erstellt Rechnung und Zahlungslink.

Bei Zahlung über Mollie kann der Status automatisiert werden.

## Variante B – klassische Überweisung auf netstyle-Konto

Problem:

Mollie kennt eine direkt auf das netstyle-Bankkonto erfolgte Zahlung nicht automatisch.

Dann wäre eine manuelle Kennzeichnung erforderlich. citeturn302663search1

### Entscheidung V1

Für Vollautomatik:

**Rechnung möglichst über Mollie-Zahlungsprozess.**

---

# 28. Bestellung abgeschlossen

Nach bestätigter Zahlung:

Backend führt atomar aus:

```text
1 Organisation erstellen
2 Kundenadministrator erstellen
3 Lizenzbundle erstellen
4 Anzahl Seats erzeugen
5 Laufzeit setzen
6 Bestellung PAID setzen
7 Rechnung verknüpfen
8 Aktivierungsmail erzeugen
9 Auditlog schreiben
```

Entweder alles erfolgreich oder keine Teilaktivierung.

---

# 29. Lizenzmodell

Produkt:

```text
PROMPTMASTER_PRO
```

Lizenztyp:

```text
PAID
TRIAL
COMPLIMENTARY
INTERNAL
```

---

# 30. Lizenzbundle

Ein Kauf von acht Lizenzen erzeugt:

```text
License Bundle #1234

Organisation:
Muster GmbH

Produkt:
PromptMaster Pro

Seats:
8

Beginn:
05.09.2026

Ende:
05.09.2027

Typ:
PAID
```

Dazu werden acht Seat-Datensätze erzeugt.

---

# 31. Seat-Modell

```text
Bundle #1234

Seat 1 → max@muster.de
Seat 2 → anna@muster.de
Seat 3 → frei
Seat 4 → frei
...
Seat 8 → frei
```

Dadurch ist jederzeit eindeutig:

- wie viele Seats gekauft wurden
- wer einen Seat besitzt
- wann dieser Seat abläuft

---

# 32. Zusätzliche Lizenzen während der Laufzeit

V1-Regel:

Jeder zusätzliche Kauf erzeugt ein eigenes 12-Monats-Bundle.

Beispiel:

```text
8 Seats
05.09.26 – 05.09.27

später gekauft:

2 Seats
01.12.26 – 01.12.27
```

Warum?

Eine automatische anteilige Preisberechnung bis zum bestehenden Vertragsende würde:

- Preislogik
- Rechnungslogik
- Rundung
- Verlängerungslogik

unnötig komplizieren.

Später kann „Co-Terming“ ergänzt werden.

---

# 33. Verlängerungslogik

Standard:

```text
8 Seats
gültig bis 05.09.2027
```

Kunde verlängert am:

```text
01.08.2027
```

Neue Laufzeit beginnt **nicht** am 01.08.2027.

Sie beginnt nach Ablauf der bestehenden Laufzeit.

```text
05.09.2027
bis
05.09.2028
```

Damit wird frühes Verlängern nicht bestraft.

---

# 34. Verlängerung nach Ablauf

Beispiel:

Lizenz endet:

```text
05.09.2027
```

Kunde verlängert erst:

```text
20.09.2027
```

Dann beginnt die neue Laufzeit am Zahlungstag.

```text
20.09.2027
bis
20.09.2028
```

Der Kunde bezahlt dadurch nicht für einen Zeitraum, in dem die Anwendung gesperrt war.

---

# 35. Keine automatische Verlängerung in V1

V1:

```text
12 Monate kaufen
↓
Erinnerungen
↓
aktive Entscheidung
↓
erneut bezahlen
```

Kein automatisches Jahresabo.

Das reduziert:

- Kündigungslogik
- Mandatsverwaltung
- fehlgeschlagene automatische Verlängerungen
- Reklamationen

Später kann Auto-Renew ergänzt werden.

---

# 36. Lizenzstatus

Mögliche Zustände:

```text
PENDING
TRIAL
ACTIVE
EXPIRING
EXPIRED
SUSPENDED
CANCELLED
```

Definition:

### PENDING
noch nicht bezahlt/aktiviert

### TRIAL
Testlizenz

### ACTIVE
normal gültig

### EXPIRING
innerhalb Warnzeitraum

### EXPIRED
Laufzeit überschritten

### SUSPENDED
manuell oder wegen Zahlungsproblem gesperrt

### CANCELLED
dauerhaft beendet

---

# 37. Lizenzprüfung

Beim Aufruf:

```text
/app/pro/
```

Backend prüft:

```text
1 Ist Benutzer angemeldet?
2 Benutzer aktiv?
3 Organisation aktiv?
4 Pro-Seat zugewiesen?
5 Lizenzbundle aktiv?
6 aktuelles Datum innerhalb Laufzeit?
7 Benutzer nicht gesperrt?
```

Nur wenn alle Prüfungen erfolgreich:

```text
ALLOW
```

ansonsten:

`
> **Preis-Hinweis:** Platzhalter und Netto-Angaben in diesem historischen Pflichtenheft-Auszug sind überholt. Verbindlich sind **2,99 € inklusive gesetzlicher MwSt. pro Benutzer und Monat bei 12 Monaten Laufzeit** beziehungsweise **35,88 € inklusive gesetzlicher MwSt. pro Benutzer und Jahr**.
