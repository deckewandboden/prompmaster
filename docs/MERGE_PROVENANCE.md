# Merge-Provenienz RC14

## Aktive Priorität

1. `SPEC.md`
2. spätere dokumentierte Change-Entscheidungen in `docs/`
3. aktiver RC14-Quellcode
4. unveränderte Free-/Pro-Golden-Master
5. `archive/` nur Provenienz / visuelle Referenz / historische Rekonstruktion

## Merge-Regeln

- RC13 wurde als stärkster aktiver Django-/Prompt-Plattform-Stand übernommen.
- Dateien aus der Chat-Transfer-Sicherung ersetzen **keinen** neueren RC13-Code; sie liegen unter `archive/`.
- Die Marketing-Sicherung vom 06.09.2026 ist der neueste vollständig physisch vorhandene Marketing-Source-Tree und wurde als `marketing/` aktiviert.
- Die zusätzlich mitgelieferten Marketing-Referenzdokumente liegen unter `docs/recovery/marketing-2026-09-06/`.
- Das exakte V15-Archiv ist weiterhin nicht materialisiert. Deshalb trägt der aktive Marketing-Source keine falsche Bezeichnung „exakt V15“.
- Der V13-Exporter wurde als Recovery-Werkzeug erhalten, weil er den dokumentierten Commit `d36033bdfc87ee5dbacd8459c8cca919ec2f2b45` aus dem ursprünglichen Git-Objektbestand exportieren kann.
- Alte UI-Prototypen und Designbilder werden nicht als Runtime importiert; sie bleiben Abnahmereferenzen.

## Integrationsänderungen gegenüber dem wiedergefundenen Marketing-Snapshot

Der Marketing-Snapshot wurde funktional an die aktuelle Plattform angebunden, ohne dessen Design-Assets zu ersetzen:

- öffentlicher Produktkatalog `/catalog.json` kommt aus Django
- aktuelle Pro-Anwendungsanzahl: 34, davon 28 zusätzlich zu den 6 Free-Anwendungen
- Login-/Checkout-/Portal-/Pro-Pfade werden am Reverse Proxy auf die aktuelle Django-Routenstruktur geführt
- `integration-patch.js` synchronisiert den sichtbaren App-Katalog mit der serverseitigen Produktquelle
- Caddy baut das Marketing-Frontend reproduzierbar über `Dockerfile.caddy`

## Alte Phase-2-Baseline

Die im Chat-Transfer vorhandene `03_PHASE2_ACTUAL_CODE_BASELINE/` bleibt vollständig archiviert. Sie wird nicht in die aktive Runtime gemischt, da RC13/RC14 deren Funktionen bereits weiterentwickelt und abgesichert enthalten.
