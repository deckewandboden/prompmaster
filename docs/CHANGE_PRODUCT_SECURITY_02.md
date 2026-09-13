# Produktzugriff und Kontosicherheit nach der grünen Runtime-Baseline

Basis: main `890daa6a4ed2da8c1ae83275b9681c67cddcf43d` (PR #1), alle drei CI-Jobs erfolgreich.

Der Geräte-Cookie `pm_device_v2` gilt für `/`, damit der echte Browser ihn auch
an `/api/v1/prompts/` sendet. Vorhandene `/pro/`-Cookies werden beim App-Aufruf
ohne zusätzliche Geräteregistrierung migriert. Verifizierte aktive Benutzer,
aktive Firmenmitgliedschaft und aktive Firma sind Voraussetzungen für Pro.
Free-/Pro-Golden-Master und der abgeleitete Runtime-Hash bleiben unverändert.

TOTP-Zeitschritte und Recovery-Codes werden unter Benutzersperre genau einmal
verbraucht. Einrichtung und Passwort-Reset werden transaktional serialisiert;
ausstehende TOTP-Secrets sind in der Sitzung verschlüsselt. Sitzungen haben
acht Stunden absolute Laufzeit und standardmäßig 1.800 Sekunden Inaktivitätsfrist
(`SESSION_IDLE_TIMEOUT`). Firmenbeitritt benötigt auch für bestehende Benutzer
eine explizite POST-Bestätigung mit CSRF. Sicherheitsaktionen werden auditiert.

Dashboard und globale Suche prüfen die jeweiligen Leserechte. MCP-Preview-Audit
enthält ausschließlich Ergebnis-Metadaten; eine Datenmigration entfernt frühere
Preview-Inhalte aus bestehenden Auditzeilen, ohne deren Identität oder Zeitstempel
zu verändern. Die normale Audit-Schnittstelle bleibt append-only.
Der öffentliche Caddy-Host sperrt `/api/v1/mcp*`; interne MCP-Clients benötigen
Zugriff über das interne Containernetz und weiterhin einen berechtigten Token.
Es wird kein zusätzlicher öffentlicher Port geöffnet.

Regressionen werden mit echten Django-HTTP-Endpunkten für Registrierung des
Geräts, Katalog, Komposition, Cookie-Migration, Kontosperren und Mandantenstatus
geprüft. Ergänzt sind TOTP-/Recovery-/Sitzungs- und eingeschränkte Admin-Rollentests
sowie MCP-JSON- und Datenschutztests. PostgreSQL- und Docker-Nachweis erfolgen
in CI; lokale statische Prüfungen und alle 194 Composer-Smokes sind erfolgreich.

Dies ist ein abgegrenzter Zwischenstand. Zahlungs-/Lizenztransaktionen,
Mail-Outbox, weitere Admin-/Portal-/Studio-Funktionen, Frontend-Integration,
Produktionskonfiguration und abschließende End-to-End-Prüfungen bleiben Teil
des laufenden Gesamtauftrags. Externe Providerzugänge und echtes Deployment
sind hiermit nicht produktiv validiert.
