# Validierung — Marketing-Frontend

Stand: 05.09.2026

## Automatisch geprüft

- 11 erfolgreiche Tests: Brutto-Jahrespreise 1/3/8 Benutzer, enthaltene Steuer ohne Aufschlag, Mengenbegrenzung, ungültige Eingaben, austauschbarer Katalog, ungültige Preisdaten, Währungsformat, vollständige FAQ/Inhaltsbereiche, verbotene Inhalte, Preistext, Anker und binäres Kopfmodell (zusammengefasst in 11 Testfällen).
- Inhaltsumfang: 20 FAQ, 6 Free-Anwendungen, 10 zusätzliche Pro-Anwendungen, Vergleich, sieben Arbeitsschritte, Lizenzregeln, Portal-, Datenschutz- und Payment-Inhalte.
- Keine erfundenen Nutzerzahlen, Referenzen, Bewertungen, eigenen KI-Leistungen oder Video-Funktion.
- Linter ohne Befunde.
- Statischer Produktionsbuild mit 14 vorbereiteten Routen.
- Kopf separat geladen; Marketing-Bundle enthält keine React-/Vinext-Laufzeit.
- Lokal erfolgreich per HTTP erreichbar.

## Bewusste Grenzen

Desktop-Hero bei 1279 × 856 visuell im Browser kontrolliert: Landschaft, Karten, Kopf, Netz, Augen und Brutto-Preis sichtbar. Preisrechner und Responsive-Regeln sind implementiert. Eine FPS-Messung auf Zielgeräten bleibt offen.

Kein Payment-, Authentifizierungs- oder Lizenzbackend implementiert. Die entsprechenden Routen zeigen ausdrücklich den Vorschauzustand. Rechtstexte und Unternehmensangaben sind als fehlend gekennzeichnet.

Die Originaldateien der Produkte fehlen. Es wurden keine Bestandsprodukte verändert; SHA-256-Vergleiche können erst nach Bereitstellung erfolgen.

Audit: Vite-Befund behoben (8.2.2). 10 verbleibende Befunde liegen in nicht ausgelieferten Starter-Serverabhängigkeiten. Der Veröffentlichungsumfang besteht ausschließlich aus dist, ohne Node-Server und ohne node_modules.
