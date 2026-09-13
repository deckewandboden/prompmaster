# PromptMaster Commercial — Marketing-Frontend

Separate Marketing-Anwendung. Die bestehenden Free-/Pro-Produkte werden weder erzeugt noch verändert.

## Ausführen

Node.js ab 22.13; im Ordner frontend:

- npm ci
- npm run dev
- npm test
- npm run build
- npm start

Die gebaute Website liegt in dist. Die Veröffentlichungsgrenze ist ausschließlich dieser statische Ordner. Kein React-, Vinext- oder Cloudflare-Server wird ausgeliefert.

## Architekturentscheidung

Das von Sites verlangte Startprojekt enthält Vinext/React und Shadcn. Diese Abhängigkeiten bleiben im Lockfile erhalten, sind aber kein Bestandteil des Marketing-Bundles. Der expliziten Vorgabe des Pflichtenhefts folgend wird die eigentliche Seite mit semantischem HTML, CSS, Vanilla JavaScript und Three.js gebaut. vite.marketing.config.js ist der aktive Build. Generierte UI-Komponenten werden nicht in den Marketing-Build importiert.

- index.html: Header und Hero
- src/content.js und src/faq.json: Content Freeze, semantische FAQ
- src/main.js: Navigation, vorbereitete Routen, Preisrechner
- src/pricing.js: centgenaue Preislogik, keine Bestellautorisierung
- public/catalog.json: austauschbarer Vorschau-Katalog
- src/head.js: lokal geladenes Modell, Three.js-Partikel und Netzwerk
- scripts/finalize.mjs: statische Inhalte und direkte Routen

## Django/PostgreSQL/Mollie

Die spätere Django-Anwendung besitzt /checkout/, /login/, /portal/ und /app/pro/. Diese Vorschau sammelt keine Zugangsdaten und legt keine Zahlungen oder Konten an. Katalog-Flags schalten keine sicherheitskritischen Funktionen frei.

Django kann /catalog.json aus PostgreSQL liefern, mit demselben Schema. Sämtliche Bestellpreise müssen nochmals serverseitig aus product_id und quantity berechnet werden. Browserpreise sind ausschließlich Anzeigen; Bestellungen speichern unveränderliche Preis-Snapshots.

Der Reverse Proxy bedient /assets/ und /models/ statisch. Die Marketing-HTML kann als Django-Template übernommen werden; keine React-Laufzeit ist dafür nötig. Für einen strikt templatebasierten Betrieb wird der Inhalt aus src/content.js beim Build vorgerendert und in das Django-Basistemplate integriert.

Mollie-Geheimnisse, Sessions, CSRF, Zahlungsprüfung, Webhook-Idempotenz, Lizenzbundles und PostgreSQL-Zugänge gehören ausschließlich ins Backend. Ein Zahlungsredirect darf niemals eine Lizenz aktivieren. Jeder Nachkauf bildet laut Pflichtenheft ein eigenes 12-Monats-Bundle. Keine automatische Verlängerung in V1.

Free: /free/ bleibt bis zum Vorliegen des Golden Masters eine verständliche Hinweisseite. Nach Integration unveränderte Datei über Django ausliefern oder freeUrl im Katalog auf eine gleich-originige, separate Asset-Route setzen. Pro-HTML niemals in public oder dist kopieren; ausschließlich nach serverseitiger Berechtigungsprüfung ausliefern.

## Bekannte offene Übergabepunkte

- Originale Free-/Pro-Dateien und deren SHA-256-Baseline fehlen im bereitgestellten Projekt.
- Verbindliche Unternehmensdaten und Rechtstexte fehlen.
- Login, Mollie, Kundenportal und serverseitige Lizenzkontrolle sind eine spätere Phase.
- Vorschau ist privat und noindex; öffentliche Betriebsfreigabe ist nicht Teil dieses Frontend-Schritts.
- Referenzgespräch liefert das Pflichtenheft nur als begrenzten Textauszug; die hier umgesetzten Frontend-Anforderungen sind darin enthalten.
- Automatische Funktions- und Buildprüfungen ersetzen keine visuelle Browser-Abnahme oder FPS-Messung auf Zielgeräten.
- Der Audit meldet weiterhin 10 Befunde in ungenutzten Starter-Serverabhängigkeiten. Diese werden nicht veröffentlicht. Der aktiv genutzte Vite-Entwicklungsserver wurde auf die korrigierte Version 8.2.2 angehoben. Vor einem künftigen Einsatz der Starter-Serverabhängigkeiten müssen deren Befunde separat behoben werden.

## Kopfmodell

Lee Perry-Smith / Infinite Realities, CC BY 3.0. Siehe public/models/ATTRIBUTION.txt. Das Modell wird als blaue Punktwolke mit Netzverbindungen dargestellt. Keine externen Laufzeitabrufe, kein Video.

Bei fehlendem WebGL/Modell erscheint der statische Hero-Kernsatz. Reduced Motion pausiert die Bewegung initial; die Pause ist jederzeit manuell steuerbar. Bei unsichtbarem Tab oder außerhalb des Viewports stoppt die Render-Schleife. Mobil reduzierte Punktzahl und Auflösung.
