# Issue #87 – Sprachfassungen juristischer Dokumente

## Konzeption und Sicherheitsgrenzen

Deutsches `LegalDocument` bleibt die alleinige Primärfassung. Für jede der
neun anderen UI-Sprachen (EN/ES/PT/TR/RU/PL/FR/IT/NL) kann eine
`LegalDocumentTranslation` je deutschem Dokument hinterlegt werden.
Unfreigegebene Texte sind niemals öffentlich. Der Originaltext, seine
Dokument-ID, sein Typ, seine Version, sein Gültigkeitsbeginn und sein
Inhalt sind über SHA-256-Prüfsummen an die genehmigte Übersetzung gebunden.
Wird der Originaltext oder die Originalidentität verändert, wird die
Übersetzung aus der öffentlichen Auswahl ausgeschlossen.

**Keine automatische Publikation:** `LEGAL_TRANSLATIONS_PUBLIC_ENABLED=0`
ist der Installationsstandard und bleibt bis zur juristischen Freigabe
unverändert. Bei fehlender freigegebener Übersetzung erscheint ausschließlich
der deutsche Originaltext mit sichtbar lokalisiertem Fallback-Hinweis und
korrektem `lang="de"`.

## Produktive Admin-Governance

`/ns-admin/legal/translations/` ist in das bestehende
PROMPTFINISHER-Rollenmodell eingebunden. `legal.read` berechtigt zur
Ansicht, `legal.write` zum Entwurf und zur Einreichung, `legal.approve`
zur Freigabe nach **getrennter** fachlicher Prüfung. Der Einreicher
`submitted_by` darf nicht selbst freigeben. Änderungen und Freigaben
werden als Audit-Ereignisse protokolliert. Freigegebene Versionen sind
schreibgeschützt; eine Änderung erfordert eine neue, separat geprüfte
deutsche Originalversion bzw. erneute Prüfung.

Der Django-Fallback-Admin steht produktiv **nicht** zur Verfügung.
Das neue Produkt-Admin ist der maßgebliche Verwaltungsweg. Die Rolle
`superadmin` erhält bei `seed_defaults` das neue Freigaberecht.
Für tatsächliche juristische Prüfung ist darüber hinaus eine qualifizierte
externe Freigabe mit belastbarer Referenz erforderlich.

## Öffentlicher Checkout: signierter Rechtsdokument-Snapshot

Die statische Marketing-Kaufseite ruft
`GET /api/v1/checkout/legal-snapshot/?customer_type=company|private` auf.
Der Server erzeugt einen zeitlich begrenzten, signierten und
sessiongebundenen Snapshot mit Dokumentversionen, Dokument-IDs,
SHA-256-Fingerprints und den tatsächlich angebotenen Textsprachen. Interne
Prüfer-IDs und Freigabereferenzen werden **nicht** in Browser-Links
transportiert, sondern nur serverseitig bei der Bestellprüfung zugeordnet.
Für parallel geöffnete Checkout-Tabs derselben Sitzung bleibt der aktive
Nonce bis zur erfolgreichen Weiterleitung an den Zahlungsanbieter
stabil. Ein Redis-Cache-Eintrag pro gehashtem Django-Session-Schlüssel wird
bei der ersten Ausstellung atomar per `cache.add` erstellt; die beiden
parallel gestarteten ersten GETs erhalten denselben Nonce. Der Cache-Eintrag
wird unabhängig von der veränderlichen Django-Session gespeichert.
Insbesondere kann die verzögerte Speicherung eines
`last_activity_at`-Werts durch die Login-/Portal-Middleware keine bereits
erfolgte Nonce-Rotation zurücksetzen. Nach erfolgreichem Checkout-Handoff
rotiert der Nonce im Cache; alle vorherigen Angebote werden ungültig.

Jeder Snapshot trägt weiterhin einen eigenen Signaturzeitpunkt
(30 Minuten maximal gültig), die konkrete Dokumentfassung und die gewählte
Kundenart. Redis ist damit eine verpflichtende Verfügbarkeitsschranke für
signierte Rechtsnachweise: Nicht erreichbarer oder verlorener Cachezustand
führt zur Ablehnung alter Links, nicht zu einem unsignierten Fallback.
Die Laufzeit des Cachezustands deckt mindestens Sitzungs- und Angebotslaufzeit
ab. Zwei Tab-Aufrufe **ohne zuvor gemeinsamen Browser-Session-Cookie**
lassen sich naturgemäß noch keiner gemeinsamen Sitzung zuordnen.

Die Regression umfasst unabhängige Reads einer bestehenden Sitzung,
parallel startende reale Browser-Tabs, unberechtigte Fremdsitzungen,
Replay nach Handoff sowie verspätetes Schreiben einer alten Session-Kopie.


Die Formularlinks
verwenden `/legal/<typ>/?checkout_snapshot=<token>` und zeigen nur
die versionierte Fassung. Bei Quellen- oder Übersetzungsdrift werden sie
mit HTTP 409 abgewiesen, ohne einen aktuelleren Text einzuschieben.

Der Checkout-POST validiert den Snapshot erneut innerhalb der
Bestelltransaktion unter Datenbanksperre. Erfolgreich validierte
Metadaten werden mit dem `Order.billing_snapshot` und den
`LegalAcceptance.evidence`-Datensätzen gespeichert. Bestehende historische
Akzeptanzdatensätze werden nicht nachträglich überschrieben.

**Beweisgrenze:** Der Nachweis bestätigt die im Kaufprozess **angebotenen,
per Link abrufbaren** Textfassungen und die angekreuzten Erklärungen.
Er beweist **nicht**, dass der Käufer die Links geöffnet oder den gesamten
Text gelesen hat. Es werden daher bewusst keine fingierten
`viewed`/`read`-Bestätigungen erstellt.

`LEGAL_CHECKOUT_SNAPSHOT_REQUIRED=0` ist der Rollout-Standard.
Die aktualisierte Marketing-Oberfläche benötigt bereits einen Snapshot.
Bei aktiviertem Gate `LEGAL_CHECKOUT_SNAPSHOT_REQUIRED=1` wird
jeder Legacy-Checkout ohne gültigen Snapshot zurückgewiesen, bevor Konto,
Bestellung oder Zahlung erstellt werden. Solange das Gate aus ist,
werden Legacy-Bestellungen ausdrücklich als
`legacy_without_signed_snapshot` und `not_recorded` markiert.

## Angemeldete Portal-Kaufwege

`/portal/licenses/buy/` und `/portal/licenses/<id>/renew/`
stellen den Snapshot beim Formular-GET serverseitig bereit und verwenden
ihn in den Rechtstext-Links und als versteckten POST-Parameter. Bei
aktiviertem Pflicht-Gate werden fehlende, abgelaufene oder abweichende
Angebote vor Order/Payment abgewiesen. In der Bestelltransaktion werden
die geprüften Originaldokumente gesperrt; ein bereits bestehender
Bestellsnapshot wird beim Idempotenz-Retry nicht durch andere Daten
überschrieben. Ohne Gate ist weiterhin ein ausdrücklich als
`legacy_without_signed_snapshot` gekennzeichneter Altweg möglich.

## Einwilligung zum vorzeitigen Leistungsbeginn

Auch die gesonderte Checkbox zur vorzeitigen Bereitstellung vor Ablauf der
Widerrufsfrist besitzt nun einen versionierten, signierten Text-Nachweis
(`early-performance-services-2026-v1`). Die bereits vorhandenen
Formulierungen in DE/EN/ES/PT/TR/RU/PL/FR/IT/NL werden als **unverändert
vorgefundener UI-Wortlaut**, nicht als juristisch geprüfte Übersetzung,
gespeichert. Der Snapshot enthält nur Textversion, Sprache und SHA-256;
die konkret angebotene Formulierung selbst wird serverseitig in
`legal_offer.early_performance_clause.text` in der Bestellung und in
`LegalAcceptance.evidence` erhalten.

Die Marketing-Checkout-Seite setzt den private-Checkbox-Wortlaut aus dem
signierten Serverangebot. Die Portal-Kauf- und Verlängerungsformulare
verwenden denselben Servertext als Checkbox-Beschriftung. Ein veränderter
Text oder abweichende Sprachversion invalidiert den früheren Snapshot,
und ein neuer muss ausgegeben werden. Ein eigenständiger Repository-Quelltexttest kontrolliert vor dem
Containerbau die unveränderte Zuordnung aller neun Marketing-Übersetzungen
zu den Backend-Fassungen. Die Django-Laufzeittests prüfen unabhängig
von Marketing-Dateien den 10-Sprachen-Vertrag und die Hashes.

**Freigabegrenze:** Dies dokumentiert nur, was die Checkbox ausdrückt und
was bestätigt wurde; es ersetzt keine rechtskundige Prüfung der genauen
Formulierung je Sprache und keine separate Prüfung der konkreten
Vertrags-/Leistungsart. Das Veröffentlichungs-/Pflicht-Gate bleibt
unverändert deaktiviert, bis technische und juristische Freigaben vorliegen.

## Offene Freigabepunkte

- Vollständige rechtlich geprüfte Übersetzungsfassungen aller benötigten
  Vertrags-/Widerrufs-/Datenschutz-/Lizenztexte liegen noch nicht vor.
- Die konkrete Erklärung zum vorzeitigen Leistungsbeginn/Wertersatz
  einschließlich übersetzter Varianten benötigt eine gesonderte,
  versionierte und rechtlich geprüfte Evidenzbindung.
- Auch die angemeldeten Portalwege für Lizenzkauf und Verlängerung
  verwenden versionierte, signierte Formularlinks und bewahren die
  Dokument-Snapshots in Bestell- und Zustimmungsnachweisen auf.
  Für Registrierung, Einladungsannahme und weitere Zustimmungswege ist
  weiterhin eine gesonderte, versionsgebundene Nachweiskette erforderlich.
- Browser-/Regressionstests, Migrationsprüfung, Deployment-Freigabe und
  kontrollierte Gate-Aktivierung auf der Zielumgebung sind erforderlich.
- Kein Merge und kein Produktivdeployment durch diesen Entwicklungszweig.

## Abnahme

Alle sechs Dokumentarten in zehn Sprachen auf tatsächlichen Inhalt und
korrektes Fallback prüfen. Echte Browserabläufe für Privat/Geschäftlich,
Sprachwechsel, gesperrten Altlink, Zeitablauf, Replay, mehrfachen Kauf,
Mollie-Weiterleitung und Auditdatensätze durchführen. Rechtsfreigabe und
Betriebsfreigabe bleiben unabhängig von erfolgreichen CI-Tests.
