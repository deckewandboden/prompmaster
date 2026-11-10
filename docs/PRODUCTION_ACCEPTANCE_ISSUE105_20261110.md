# Produktionsabnahme #105 – Arbeitsstand 10.11.2026

**Gesamtstatus: NICHT ABGENOMMEN.** Kein Merge, kein Produktionsdeployment.

Ziel: https://promptmaster.decke-wand-boden.de/ · freigegebene Basis a57468e673d22163ccf55efea9ec28738e2cf0dd.
Korrekturen: [Draft PR #110](https://github.com/deckewandboden/prompmaster/pull/110).

PASS gilt ausschließlich für den beschriebenen tatsächlich geprüften Schritt. FAIL bedeutet reproduziertes Fehlverhalten oder gescheitertes Gate. BLOCKED bedeutet nicht abgeschlossen; der Grund steht in der Zeile. Codekorrektur ist kein Live-Retest. Browserbefunde vom 06./07.11.; Wiederprüfung Lizenzdialog am 10.11.2026. Chromium Cloud, Desktop; andere Browser und Viewports nicht nachgewiesen. Die aktuelle laufende Server-SHA wurde in dieser Sitzung nicht unabhängig ausgelesen. Keine personenbezogenen Kundendaten, echten Käufe, Löschungen oder Benachrichtigungen erzeugt.

## Beobachtete Abläufe und offene Prüfgruppen

| ID | Bereich / Prüfschritt | Status | Ergebnis / konkrete Grenze |
|---|---|---|---|
| PUB-01 | Startseite DE/EN öffnen | PASS | Inhalte und Navigation angezeigt. Kein Nachweis sämtlicher Sprachen. |
| PUB-02 | Free-Link | PASS | Öffnet Free in neuem Tab. |
| PUB-03 | Lizenzrechner 1 → 2 → 1 | PASS | Jahresbetrag 35,88 → 71,76 → 35,88 EUR; Minimum 1. |
| PUB-04 | Kaufen | BLOCKED | Oberfläche meldet Kauf vorübergehend nicht verfügbar. Kommerzielle Freigabe nicht verändert. |
| PUB-05 | Alle 20 FAQ öffnen/schließen EN | PASS | Am 10.11. alle 20 Antworten geöffnet, Inhalt vorhanden und wieder geschlossen. |
| PUB-06 | Anker / übrige CTAs | BLOCKED | Einzelprüfung noch offen. |
| PUB-07 | Preise, Unternehmen, Kontakt | PASS | Seiten navigierbar; keine Kontaktanfrage abgesendet. |
| PUB-08 | Impressum, Datenschutz, AGB, Lizenz, Widerruf, Barrierefreiheit | PASS | Alle sechs Routen erreichbar. EN weist ausdrücklich auf deutsche freigegebene Rechtstexte hin; keine juristische Abnahme. |
| PUB-09 | Vertrag widerrufen: Formular anzeigen | PASS | Name, E-Mail, Auftragsreferenz und Bestätigung vorhanden. |
| PUB-10 | Verträge kündigen: Formular anzeigen | PASS | Kündigungsart, Name, E-Mail, Referenz, Datum und Grund vorhanden. |
| PUB-11 | Widerruf/Kündigung absenden | BLOCKED | Reale Rechtsfolgen/Benachrichtigungen; kein isolierter Testprozess nachgewiesen. |
| PUB-12 | Modell-Attribution | PASS | /models/ATTRIBUTION.txt lesbar. |
| FREE-01 | DE Zusammenfassen: Pflichtfelder und Fertigstatus | PASS | Synthetisches Projekt Alpha; Zielgruppe, Schwerpunkt, Detail, Format, Ton gewählt; 100 Prozent und Kopieren freigegeben. |
| FREE-02 | DE/EN Kopieren | PASS | Zwischenablage enthält erzeugten Prompt einschließlich synthetischer Quelle. |
| FREE-03 | Prompt-Inhalte DE/EN | FAIL | Inhalt, Zielgruppe und Regeln enthalten; abschließender Punkt der Eingabe wird verdoppelt (zusammen..). Fix in PR, Live-Retest offen. |
| FREE-04 | Reset | PASS | Prompt geleert, Kopieren gesperrt. |
| FREE-05 | Sprache DE → EN | PASS | Umschaltung lädt neu; Konfiguration wird geleert. Erhalt der Eingaben nicht als Anforderung belegt. |
| FREE-06 | Englische Beschriftungen | FAIL | Pro-Bereiche, Fortschritts-ARIA, Auswahlbadge, Zusammenfassungs-Hilfen, Formate und Markentext teilweise deutsch. Fix in PR, Live-Retest offen. |
| FREE-07 | Pro-Vergleich öffnen/schließen | PASS | Vergleich sichtbar; Schließen blendet ihn aus. |
| FREE-08 | Word-Lizenzdialog öffnen/zurück | PASS | Dialog öffnet und schließt; Lizenzsperre bleibt. |
| FREE-09 | Word-Lizenzdialog EN | FAIL | Titel, Anforderungssatz, aktuelle/benötigte Stufe und Buttons deutsch. Am 10.11. erneut bestätigt. Fix vorbereitet, Live-Retest offen. |
| FREE-10 | Lizenzwechsel im Word-Dialog | PASS | M365 Copilot (Basic) gewählt, Dialog geschlossen; Word/Excel/PowerPoint anschließend auswählbar. |
| FREE-12 | Word Textüberarbeitung EN erzeugen/kopieren | PASS | Synthetische Vorgabe und drei erledigte Beispielaufgaben unverändert; Zielgruppe, Fokus, Format, Ton und Quellenregeln englisch enthalten. 100 Prozent und Zwischenablage geprüft. |
| FREE-13 | Word-UI EN | FAIL | Pro-Vorschauaufgaben Strukturierten Bericht erstellen / Risiken und Lücken analysieren samt Beschreibung, vier Feldhinweise und PRO-Fokuslabels noch deutsch. Katalogkorrekturen und Übersetzung zusammengesetzter PRO-Labels im PR ergänzt; Live-Retest offen. |
| FREE-14 | Alle 28 zusätzlichen Pro-Kacheln | PASS | Einblenden, jede Kachel einzeln öffnen, Vorschau mit Kaufverweis vorhanden, Zurück schließt. Kein Checkout ausgelöst. |
| FREE-15 | Pro-Vorschauhinweis EN | FAIL | Satz PROMPTFINISHER Pro erweitert Apps, Rollen und Business-Prompts. Microsoft 365 Copilot wird separat lizenziert. bleibt deutsch. Korrektur im PR ergänzt; Live-Retest offen. |
| FREE-11 | Alle Auswahlkombinationen, Edit-Sprünge, Fokuslimit, Tastatur, Kopierfehler | BLOCKED | Nur oben genannter Summarize-Ablauf geprüft. |
| AUTH-01 | Pro anonym öffnen | PASS | Weiterleitung zu Anmeldung mit next=/pro/. |
| AUTH-02 | Erfolgreiche Anmeldung / Abmeldung | BLOCKED | Keine abgeschlossene sichere Anmeldung mit Testkonto. |
| AUTH-03 | Registrierung / Verifikation / Passwort vergessen | BLOCKED | Testpostfach und abgesicherter Mailpfad fehlen; keine Mail ausgelöst. |
| AUTH-04 | 2FA / Wiederherstellung / Sitzung / Rate Limit | BLOCKED | Testkonten und Authentifizierung fehlen. Keine Sperrversuche auf echten Konten. |
| PRO-01 | Alle 215 Aufgaben inkl. Quelle, Ausgabe, Kopieren, Rating | BLOCKED | Pro-Testkonto/Entitlement fehlen; Einzelinventar unten. |
| CUSTOMER-01 | Navigation, Profil, Tabellen, Suche, Sortierung, Filter, Seitenwechsel | BLOCKED | Geeignetes Kunden-Testkonto fehlt. |
| CUSTOMER-02 | Benutzer, Einladungen, Rollen, Lizenzen, Geräte, Deep Links | BLOCKED | Isolierter Testmandant mit mindestens zwei Testidentitäten fehlt. |
| CUSTOMER-03 | Bestellung, Rechnung, Verlängerung, Rückerstattung | BLOCKED | Kein Sandbox-Kontext; echte Finanzaktionen ausgeschlossen. |
| STAFF-01 | netstyle-Navigation und sämtliche Verwaltungslisten/Formulare | BLOCKED | netstyle-Testkonto und isolierte Testobjekte fehlen. |
| STAFF-02 | Prompt Studio Draft/Test/Review/Approve/Publish/Archive | BLOCKED | Testberechtigungen fehlen; kein produktiver Publish. |
| STAFF-03 | Mail, Mollie, Backup, Audit, Monitoring, Qualitätsregeln | BLOCKED | Berechtigter Read-only-Zugriff fehlt; Schreibfolgen nicht isoliert. |
| RBAC-01 | Rollenmatrix positiv/negativ / Mandantentrennung / IDOR | BLOCKED | Zwei Testmandanten und Konten mit unterschiedlichen Rollen erforderlich. |
| I18N-01 | Zehn Sprachen in allen Bereichen / generierten Prompts | BLOCKED | Nur DE/EN-Zusammenfassen live geprüft; Katalogtests ersetzen keine UI- und Sprachprüfung. |
| UX-01 | 360/390/768/1440/1920 px, Chrome/Edge/Firefox/Safari | BLOCKED | Desktop-Chromium-Teilprüfung; restliche Geräte-/Browsermatrix offen. |
| SEC-01 | Release-Sicherheitsgates im ersten PR-Lauf | PASS | GitHub Run 42358306553 erfolgreich. Kein vollständiger Sicherheitsnachweis. |
| CI-01 | CI / Full Stack am bisherigen PR-Head ff41b579 | FAIL | Doppelte Katalogschlüssel Offene Fragen, Termine, Zahlen / Fakten stoppen Preflight und Bootstrap. Lokal korrigiert; danach fehlender Manifest-Eintrag ebenfalls korrigiert. Neuer CI-Lauf erforderlich. |
| CI-02 | Container-Security am bisherigen PR-Head | FAIL | Caddy: musl-utils 1.2.5-r23, Scan fordert r24 (CVE-2026-107891); x/net v0.60.0, Scan fordert v0.62.0 (CVE-2026-78661). Korrektur vorbereitet; Scan muss erneut erfolgreich sein. |
| CI-03 | Shell Syntax / Live Free Locale read-only | PASS | Runs 42358306563 und 42358306700 erfolgreich. Begrenzter Smoke-Test, keine Vollabnahme. |
| RELEASE-01 | Human Review, gesicherter Release, Live-Retest | BLOCKED | PR bleibt Draft; kein neuer Produktionscommit freigegeben oder installiert. |

## Aufgaben- und Sprachinventar

Jede Zelle bezeichnet die vollständige Einzelabnahme (Felder, Optionen, Validierung, generierter Prompt, Kopieren, Übersetzung) für diese Aufgabe und Sprache. BLOCKED heißt: nicht vollständig live geprüft; Free offen im laufenden Testumfang, Pro mangels Testanmeldung. Die 17 Free-Pro-Vorschauen dürfen keinen kostenlosen Pro-Zugriff ermöglichen. Diese Aufgabe umfasst auch alle Varianten; ein einzelner positiver Smoke-Test reicht nicht für PASS. chat_sum DE/EN bleibt wegen des bestätigten Satzzeichenfehlers FAIL.

| Produkt | Aufgabe-ID | Typ | DE | EN | ES | PT | TR | RU | PL | FR | IT | NL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Free | chat_brief | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | chat_compare | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | chat_sum | Free-Vertrag | FAIL | FAIL | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | chat_write | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | excel_compare | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | excel_explain | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | excel_mgmt | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | excel_trends | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_actions | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_cal_conflicts | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_cal_next | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_cal_schedule | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_calendar_rules | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_improve | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_meeting_prep | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_reply | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_thread | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_todo_create | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_todo_extract | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_todo_prioritize | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | out_todo_week | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | ppt_analyze | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | ppt_exec | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | ppt_outline | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | ppt_rewrite | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | teams_chat | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | teams_meeting | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | teams_mgmt | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | teams_notes | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | word_report | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | word_rewrite | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | word_risk | Pro-Vorschau | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Free | word_sum | Free-Vertrag | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-001 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-002 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-003 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-004 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-005 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-006 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-007 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-008 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-009 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-010 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-011 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-012 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-013 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-014 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-015 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-016 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-017 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-018 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-019 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-020 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-021 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-022 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-023 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-024 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-025 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-026 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-027 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-028 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-029 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-030 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-031 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-032 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-033 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-034 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-035 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-036 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-037 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-038 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-039 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-040 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-041 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-042 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-043 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-044 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-045 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-046 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-047 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-048 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-049 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-050 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-051 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-052 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-053 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-054 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-055 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-056 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-057 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-058 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-059 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-060 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-061 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-062 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-063 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-064 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-065 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-066 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-067 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-068 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-069 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-070 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-071 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-072 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-073 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-074 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-075 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-076 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-077 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-078 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-079 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-080 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-081 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-082 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-083 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-084 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-085 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-157 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-158 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-159 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-160 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-161 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-162 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-163 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-164 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-165 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-166 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-167 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-168 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-169 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-170 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-171 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-172 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-173 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-174 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-175 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-176 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-177 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-178 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-179 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-180 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-181 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-182 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-183 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-184 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-185 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-186 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-187 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-188 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-189 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-190 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-191 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-192 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-193 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-194 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-195 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-196 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-197 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-198 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-199 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-200 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-201 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-202 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-203 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-204 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-205 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-206 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-207 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-208 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-209 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-210 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-211 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-212 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-213 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-214 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-215 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-216 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-217 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-218 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-219 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-220 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-221 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-222 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-223 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-224 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-225 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-226 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-227 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-228 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-229 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-230 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-231 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-232 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-233 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-234 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-235 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-236 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-237 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-238 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-239 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-240 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-241 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-242 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-243 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-244 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-245 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-246 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-247 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-248 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-249 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-250 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-251 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-252 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-253 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-254 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-255 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-256 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-257 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-258 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-259 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-260 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-261 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-262 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-263 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-264 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | PM20-265 | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | chat_brief | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | excel_compare | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | excel_explain | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | excel_mgmt | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | excel_trends | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | out_cal_conflicts | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | out_cal_next | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | out_cal_schedule | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | out_calendar_rules | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | out_improve | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | out_todo_create | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | out_todo_extract | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | out_todo_prioritize | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | out_todo_week | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | ppt_analyze | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | ppt_exec | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | ppt_outline | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | ppt_rewrite | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | teams_meeting | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | teams_mgmt | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Pro | word_report | Laufzeitaufgabe | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED | BLOCKED |

## Fortsetzung und Abnahmekriterium

1. Neue CI einschließlich Full Stack und Container-Scan muss grün sein.
2. Öffentliche und Free-Einzelprüfungen vervollständigen; fehlende Live-Tests bleiben BLOCKED.
3. Sichere Anmeldung mit dedizierten Testkonten für Pro, Kunde und netstyle, mindestens zwei Testmandanten für negative Berechtigungsprüfungen. Passwörter gehören nicht in Issue oder Bericht.
4. Authentifizierte UI vollständig inventarisieren; obige Bereichsgruppen in konkrete Formular-/Button-/Rollenfälle aufteilen. Die jetzige Matrix ist ausdrücklich keine Behauptung einer bereits vollständigen geschützten UI-Inventarisierung.
5. Nur nach Human Review über bestehenden gesicherten Release-Prozess deployen; alle Fehlerfälle am installierten Commit erneut prüfen. Gesamtfreigabe ausschließlich ohne offene FAIL/BLOCKED.

## CI-Fortschreibung

Head c4ecac3fe24264552365092f357b9c3d866f0569: Doppelschlüssel, Manifest und Lizenzdialog im PR korrigiert. Go-Abhängigkeiten x/net v0.62.0 und erforderliches x/crypto v0.58.0; Caddy verlangt musl/musl-utils mindestens 1.2.5-r24. Vollständiger lokaler github_preflight PASS. GitHub CI 42806103550 einschließlich Full Stack erfolgreich; Shell, Release Safety und Live Locale ebenfalls erfolgreich. Full Dependency Security 42806103710 bleibt FAIL: Web-Image zlib1g 1:1.3.dfsg+really1.3.1-1+b1, CVE-2026-76844 und CVE-2026-85091 laut Trivy. Neuester Fix installiert aktualisiertes zlib1g und prüft mindestens 1:1.3.dfsg+really1.3.1-1+deb13u1 im Build. Ein neuer vollständiger Lauf ist erforderlich. Keine Gesamt-CI-Freigabe.
