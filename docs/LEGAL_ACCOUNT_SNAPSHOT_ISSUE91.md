# Issue #91 – signierte Dokumentangebote vor Kontoanlage / Neubenutzer-Einladung

## Scope

Die technische Implementierung befindet sich **ausschließlich in Draft PR #89**.
Sie wird **nicht** durch einen Merge, eine Deployment-Aktion oder eine Änderung
der juristischen Freigabe-Flags freigeschaltet.

Eigener Schalter: `LEGAL_ACCOUNT_SNAPSHOT_REQUIRED=0` (**Default OFF**).
Bei OFF bleiben die bisherigen Registrierung- und Neubenutzer-Einladungswege
funktionsgleich. `LegalAcceptance.evidence` markiert sie ausdrücklich mit
`verification=legacy_without_signed_snapshot` sowie
`presentation_proof=not_recorded`; dies ist **kein signierter Beweis**.

`LEGAL_ACCOUNT_SNAPSHOT_REQUIRED=1` ist ausschließlich für isolierte
QA-/Stagingprüfungen vorgesehen, bis sämtliche fachlichen und technischen
Freigaben gesondert dokumentiert sind. Auch ein erfolgreich signierter
Dokumentnachweis ist keine externe juristische Prüfung von Rechtstexten.

## Angebotsvertrag bei eingeschaltetem Gate

1. GET `/auth/register/` bzw. GET einer **neuen** Unternehmensidentität
   unter `/auth/invite/<token>/` gibt zwei gepinnte URLs für AGB und
   Datenschutz sowie ein signiertes, zeitlich begrenztes Formularfeld zurück.
   Kontoerstellung ohne dokumentierte POST-Zustimmung ist nicht erlaubt.
2. Unter `/legal/<typ>/?account_snapshot=<token>` ist die signierte
   Präsentation für diese Sitzung und nur für die angebotenen Dokumente
   erreichbar. Ungültige, veraltete, fremde oder kombinierte Checkout-/Konto-
   Tokens ergeben HTTP 409 mit `no-store`, `no-referrer` und `noindex`.
   Auch **leere, mehrfach angegebene oder gemischte** Snapshot-Query-Parameter
   führen zwingend zu HTTP 409 und niemals zur öffentlichen Standardansicht.
3. Tokenbindung: anhaltender Django-Session-Key (geheim abgeleitete HMAC),
   genau ein Flow (`registration` oder `invitation`), bei Einladung
   zusätzlich einen HMAC-Fingerabdruck der konkreten Einladung aus Firma,
   Rolle, E-Mail und Einladungstoken-Hash. E-Mail und Token-Hash werden
   **nicht im lesbaren signierten URL-Token gespeichert**; die Einladungs-ID
   ermöglicht nur die serverseitige Nachprüfung.
4. Rechtsinhalte: zwei aktuell gültige deutsche Primärdokumente. Der
   Snapshot bindet ID, Dokumenttyp, Version, Quellidentitäts-SHA-256,
   tatsächliche Textsprache und Text-SHA-256. Bei ausstehender oder
   unveröffentlichter Übersetzung bleibt der sichtbare Körper **deutsch**
   mit explizitem Hinweis auf der Rechtsseite; es wird keine fremdsprachige
   Rechtsfassung erfunden.
5. POST validiert Token, Session, Flow, Einladungsidentität, deutsche
   Primärquelle und dargestellte Textversion innerhalb der
   Datenbanktransaktion **vor** Benutzer- oder Mitgliedschaftserstellung.
   Jeder Drift führt zu Abbruch; eine neue Anzeige muss geholt werden.
   Bereits vorhandene Benutzer durchlaufen einen separaten, unveränderten
   Mitgliedschaftsprozess. Der signierte Token wird vor Kontoerstellung
   über einen atomaren, serverseitigen Einmalverwendungsnachweis beansprucht;
   bei Redis-/Cache-Ausfall wird der POST verweigert. Ein nach Datenbank-
   Rollback verbrauchter Token muss durch ein neues Angebot ersetzt werden.
6. Tatsächlich angenommene Fassungen werden je Primärdokument in
   `LegalAcceptance` festgehalten. `verification` ist
   `signed_session_bound_document_offer`,
   `presentation_proof=links_offered_not_read_receipts`. Der Beleg sagt
   **nicht**, dass Links geöffnet oder die Texte gelesen wurden.
7. Unterschiedliche GETs in zwei Tabs **derselben bestehenden Browser-
   Sitzung** invalidieren einander nicht. Konto- und Einladungsidentitäten
   sowie die spätere Sessionrotation nach erfolgreicher Anmeldung verhindern
   eine fremde oder nachfolgende Kontoanlage mit demselben Angebot. Tokens
   sind höchstens 30 Minuten gültig; kein stiller Legacy-Fallback bei
   fehlerhaftem Token in aktiviertem Modus.

## Grenzen und Freigabe

- `LEGAL_TRANSLATIONS_PUBLIC_ENABLED=0` bleibt unabhängig ausgeschaltet:
  aus technischer Signatur entsteht **keine** Rechtsübersetzungs-Freigabe.
- `LEGAL_CHECKOUT_SNAPSHOT_REQUIRED=0` bleibt unabhängig ausgeschaltet:
  der bestehende Checkout wird nicht verändert.
- Keine Tabellenmigration: alle zusätzlichen Zustimmungsattribute liegen
  im vorhandenen JSON-Feld der `LegalAcceptance`.
- Eine technische 4/4-CI-Abnahme ist commitgenau nachzuweisen,
  einschließlich der Tests in
  `apps.legal.tests_account_snapshot` und
  `apps.accounts.tests_legacy_legal_evidence`.
- Ergänzte CI-Regressionsfälle: veröffentlichungsberechtigte Englischfassung wird
  mit tatsächlich angezeigtem Body-Hash gespeichert; nachträgliche Manipulation
  verweigert Link und POST. Entwurf/Review bleibt deutscher Fallback.
  Abgelaufene Einladungen und fehlende CSRF-Tokens blockieren Benutzeranlage.
- Der isolierte Backend-Playwright-Browserlauf aktiviert den Account-Snapshot-
  Testschalter **nur im untergeordneten CI-Django-Server**. Er prüft im echten
  Browser signiertes Formularfeld, gepinnte AGB- und Datenschutzlinks,
  gemeinsame Session-Cookies und anschließend die erfolgreiche Privat- bzw.
  Firmenregistrierung inklusive bisheriger 2FA- und Verifikationsabläufe.
  Das ersetzt keine separate produktive Freigabe.
- Der reale Browser-403 wurde als `Origin checking failed` diagnostiziert:
  `Referrer-Policy: no-referrer` auf einem HTML-POST-Formular verursacht
  `Origin: null`, was Django-Original-CSRF verwirft. Deshalb nutzen nur
  die signierten Registrierungs- und Einladungsformular-Antworten
  `Referrer-Policy: origin` (ohne Pfade, Query-Strings oder Tokens).
  Die gepinnten AGB-/Datenschutz-GET-Seiten behalten weiterhin
  `Referrer-Policy: no-referrer`. Der isolierte Browserlauf setzt
  **keine** zusätzlichen `CSRF_TRUSTED_ORIGINS` und deaktiviert
  **keine** Sicherheitsprüfung.
- Für Freischaltung benötigt Issue #91 zusätzlich einen dokumentierten
  isolierten QA-Lauf mit Replay-/Parallel-Tab-/Drift- und
  End-to-End-Tests; Releaseentscheidungen und die rechtliche Prüfung in
  Issue #87 sind getrennt.
