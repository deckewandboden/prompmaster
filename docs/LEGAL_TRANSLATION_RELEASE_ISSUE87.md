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
sessiongebundenen Snapshot mit den Dokumentversionen, Dokument-IDs,
SHA-256-Fingerprints, tatsächlichen Textsprachen sowie bei veröffentlichten
Übersetzungen Freigabezeitpunkt, Referenz und Prüfer-ID. Die Formularlinks
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

## Offene Freigabepunkte

- Vollständige rechtlich geprüfte Übersetzungsfassungen aller benötigten
  Vertrags-/Widerrufs-/Datenschutz-/Lizenztexte liegen noch nicht vor.
- Die konkrete Erklärung zum vorzeitigen Leistungsbeginn/Wertersatz
  einschließlich übersetzter Varianten benötigt eine gesonderte,
  versionierte und rechtlich geprüfte Evidenzbindung.
- Die angemeldeten Portal-Kauf- und Verlängerungswege sowie weitere
  Registrierungs-/Einladungsvorgänge müssen denselben verbindlichen
  Dokument-Snapshot erhalten. Derzeit ist nur der **öffentliche**
  Marketing-Checkout durch die neue Signaturstrecke abgedeckt.
- Browser-/Regressionstests, Migrationsprüfung, Deployment-Freigabe und
  kontrollierte Gate-Aktivierung auf der Zielumgebung sind erforderlich.
- Kein Merge und kein Produktivdeployment durch diesen Entwicklungszweig.

## Abnahme

Alle sechs Dokumentarten in zehn Sprachen auf tatsächlichen Inhalt und
korrektes Fallback prüfen. Echte Browserabläufe für Privat/Geschäftlich,
Sprachwechsel, gesperrten Altlink, Zeitablauf, Replay, mehrfachen Kauf,
Mollie-Weiterleitung und Auditdatensätze durchführen. Rechtsfreigabe und
Betriebsfreigabe bleiben unabhängig von erfolgreichen CI-Tests.
