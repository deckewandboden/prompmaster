# Issue #87 – Freigabepflichtige Sprachfassungen für Rechtsdokumente

## Architektur und Sicherheitsgrenzen

Die aktive deutsche `LegalDocument`-Version ist und bleibt die Primärfassung.
Die neuen `LegalDocumentTranslation`-Datensätze sind je Primärdokument-ID und
Zielsprache (EN/ES/PT/TR/RU/PL/FR/IT/NL) eindeutig zugeordnet.
Die bestehende Tabelle `LegalAcceptance` und ihre historischen
Bestell-/Zustimmungsreferenzen werden nicht migriert oder verändert.

**Bei Installation sind fremdsprachige Dokumentkörper ausgeschaltet.**
`LEGAL_TRANSLATIONS_PUBLIC_ENABLED=0` ist Standard.
Selbst `approved`-Datensätze werden dann niemals öffentlich ausgegeben.
Für nicht-deutsche UI-Sprachen erscheint eine verständliche, sprachspezifische
Warnung und der ursprüngliche deutsche Dokumenttext mit `lang="de"`.
Dies ist kein stillschweigender Englisch-/Französisch-Text.

## Freigabeprozess

1. Zu einer konkreten deutschen Originalversion einen Übersetzungsentwurf mit
   `language`, `document` und `content` in Django Admin anlegen.
2. Den Entwurf nach redaktioneller Sichtung auf **review** setzen.
3. Juristische oder offiziell beauftragte Fachprüfung außerhalb des Systems
   durchführen; Nachweis unter `approval_reference` dokumentieren.
4. Ein Benutzer mit der separaten Django-Berechtigung
   `legal.approve_legal_translation` führt die Admin-Aktion zur Freigabe aus.
   Der Freigabevorgang speichert Prüfer, Zeitstempel und die SHA-256-Prüfsummen
   beider konkreter Textversionen.
5. Freigegebene Übersetzungsdatensätze sind über den ORM-Save und die
   Standard-Admin-Oberfläche unveränderlich. Ändert sich die deutsche
   Primärfassung nachträglich, erkennt die Laufzeitauswahl die abweichende
   Prüfsumme und verwendet sofort wieder das deutsche Original.
6. Erst nach **separater** fachlicher Produktfreigabe darf in einer kontrollierten
   Umgebung `LEGAL_TRANSLATIONS_PUBLIC_ENABLED=1` aktiviert werden.

**Wichtig:** Die technische Berechtigung oder der Freigabestatus ersetzt
keine juristische Qualifikation der prüfenden Person. Ohne einen belastbaren
externen Freigabenachweis darf keine Sprachfassung freigegeben werden.

## Aktueller Umfang und Restarbeiten

Umgesetzt in diesem Entwicklungszweig:
- isoliertes, migrationstaugliches Übersetzungsdatenmodell;
- Review-/Approval-Aktionen im Django Admin mit getrennten Rechten;
- public resolver mit geschützter Sprachwahl und Fallback in neun Sprachen;
- prüfbarer Content-Hash und echtes Sprachattribut des Dokumentkörpers;
- gezielte Regressionstests (unfreigegeben, Freigabe, Manipulation,
  Quellversionswechsel, XSS-Escaping, sechs Dokumenttypen).

**Noch nicht als abgeschlossen markieren:**
- Übersetzte Rechtsdokumentkörper existieren noch nicht; sie dürfen erst nach
  fachlicher Freigabe in neun Sprachen eingepflegt werden.
- Vertragsschluss-/Checkbox-Consent-Evidenz bei Bestellungen muss die tatsächliche
  angezeigte Fassung inkl. Originalversion, Sprachcode, Text-Hash und
  Freigabezeitpunkt dauerhaft protokollieren und gegen Race Conditions absichern.
  Bestehende `LegalAcceptance`-Verknüpfungen dürfen nicht geändert werden.
- Bestehende `/ns-admin/`-Rechtsdokumentverwaltung muss die neuen
  Übersetzungen und den Freigabestatus getrennt und rollenbasiert präsentieren,
  falls Django Admin im Betriebsmodell nicht zugänglich ist.
- Die Checkout-Erklärung zum Beginn vor Widerrufsfrist und Wertersatz ist
  juristisch für alle Sprachen separat zu prüfen, nicht nur technisch zu übersetzen.
- Vollständiger UI-/Browser-Regressionstest einschließlich Edit-/Approve-Workflows,
  Release-Flags, Migration und Rollback auf der tatsächlichen Umgebung.
- Keine Aktivierung, kein Merge und kein Deploy im Rahmen dieser Entwicklung.

## Betriebsprüfung

Nach Freigabe muss für alle sechs Dokumenttypen und zehn UI-Sprachen nachgewiesen
sein, ob tatsächlich eine freigegebene, versionstreue Sprachfassung angezeigt wird.
Falls keine Freigabe vorliegt, ist der Fallback eindeutig sichtbar.
Eine vorhandene UI-Übersetzung allein ist **kein** Nachweis für einen
übersetzten rechtlichen Dokumentkörper.
