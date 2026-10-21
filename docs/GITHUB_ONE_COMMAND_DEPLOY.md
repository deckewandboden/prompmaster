# PROMPTFINISHER – GitHub-geführtes Update mit einem Befehl

Diese Prozedur aktualisiert eine **bereits bestehende produktive PROMPTFINISHER-Installation** aus dem geprüften Branch `main`. Es gibt **keine lokalen ZIPs, ZIP-Installer oder zusätzliche PowerShell-Dateien**. Das Release-Skript und seine automatischen Tests liegen vollständig im GitHub-Repository.

## Einziger Aufruf unter Windows/PowerShell

```powershell
ssh root@85.215.172.6 'set -o pipefail; curl -fsSL https://raw.githubusercontent.com/deckewandboden/prompmaster/main/scripts/bootstrap_github_release.sh | bash'
```

Die Zugangsdaten und die bestehende Produktions-`.env` verbleiben auf dem Server und werden nicht in Git übertragen. Das GitHub-Repository ist öffentlich und wird mit HTTPS ohne zusätzliche Deploy-Keys gelesen. Dieser Bootstrap funktioniert deshalb auch, wenn auf dem Server `git@github.com: Permission denied (publickey)` erscheint. Der Starter stammt direkt aus GitHub, wird nur über HTTPS geladen und benötigt gültigen SSH-Zugang **zum Produktionsserver**, nicht zu GitHub. Die Prüfung bricht bei Fehlern ohne `git reset --hard` ab.

## Bestehende Änderungen am Server: automatisch und überprüfbar gesichert

Vor der Aktualisierung lädt der Starter den öffentlichen GitHub-`main`-Stand über HTTPS und prüft, dass ein Fast-Forward überhaupt möglich ist. Bestehende **getrackte** lokale Änderungen (z. B. die am 21.10. gemeldeten 20 Grafik-, CSS-, HTML- und Proxydateien) werden **vor** jeder Aktualisierung erhalten als:

- Git-Stash mit identifizierbarer `STASH_SHA`, ohne automatische Wiederanwendung;
- vollständiger Binär-Patch mit SHA256-Prüfsumme;
- eigenständiges Git-Bundle, nach Erstellung mit `git bundle verify` geprüft.

Das Backup befindet sich mit privaten Dateirechten **außerhalb** des Checkout unter `/root/projekte/docker/.promptfinisher-local-edit-rescue/`. Ignorierte und unversionierte Dateien einschließlich `.env` werden weder gestasht noch in das Bundle/den Patch übernommen. Bei Divergenz des Git-Verlaufs oder fehlendem Backup-Nachweis erfolgt kein Deployment. Danach wird `origin` dauerhaft auf die öffentliche HTTPS-URL gesetzt und `main` ausschließlich per Fast-Forward aktualisiert. Die gesicherten lokalen Anpassungen werden nicht in GitHub übernommen; sie müssen bei Bedarf gesondert gegen den GitHub-Stand verglichen werden.

## Was der Aufruf macht

1. Lädt den GitHub-Bootstrap öffentlich über HTTPS, prüft `main`, vorbestehende Produktionsmarkierung, saubere Rechte und einen Fast-Forward zur GitHub-SHA.
2. Sichert bei Bedarf die bereits veränderten getrackten Dateien in Stash, Binär-Patch und verifiziertem Bundle. Wechselt `origin` danach sicher von Git-SSH auf öffentliches Git-HTTPS.
3. Synchronisiert `origin/main` kontrolliert, startet `scripts/release_from_github.sh` aus dem nun aktuellen GitHub-Checkout und protokolliert die **volle Git-Commit-SHA**.
4. Führt das bestehende `scripts/deploy.sh` mit seinen Preflight-, Test-, Backup-, Migrations-, Health- und Last-known-good-Prüfungen aus. Docker-Volumes werden nicht gelöscht. Eine Mollie-Live-Aktivierung wird nicht aufgerufen.
5. Kontrolliert über echtes HTTPS mit vollständiger Zertifikatsprüfung Marketing, Free, Login, Pro/Login-Redirect, Django-Health und die aktuelle i18n-Datei. Alle zehn Sprachkennungen sowie die Cache-Header werden überprüft.
6. Erst nach bestandener externer Abnahme erscheint `DEPLOY=PASS; PUBLIC_HTTPS=PASS; LANGUAGES=10`. Der Nachweis steht im privaten Verzeichnis `artifacts/deploy-state/`.

## Nur die Quelle prüfen, ohne Container neu zu starten

```bash
bash scripts/release_from_github.sh --verify-only
```

Der Modus führt den kontrollierten Git-Fast-Forward und die Host-Vorabprüfung aus, **aber keinen Docker-Deploy**.

## Sicherheitsgrenzen

- Bei divergiertem `main`, verändertem Quelltext, abweichendem `origin`, fehlender produktiver `.env`, fehlendem Last-known-good oder bereits laufendem Release: **Abbruch statt Überschreiben**.
- Dies ist ein **technisches Update einer bereits vorhandenen Website**, keine Erstinstallation und keine Freigabe von Mollie-Live-Checkout. Erstmalige kommerzielle Inbetriebnahme und deren externe, sprachliche, visuelle, juristische und Backup-Freigaben verbleiben unter `scripts/go_live.sh` und `docs/RELEASE_GATES.md`.
- Die zehn auswählbaren UI-Sprachen und zentrale Katalogabdeckung bedeuten **nicht**, dass jede Übersetzung bereits eine vollständige Muttersprachler-/Rechtsprüfung bestanden hat.
- Ein grüner GitHub-Workflow bedeutet noch nicht, dass der Code auf dem Zielserver installiert ist. **Nur** der erfolgreiche SSH-Deploy samt externem HTTPS-Smoke belegt die Live-Version.
- Die Pro-Nutzeroberfläche ist durch Login/2FA geschützt. Der öffentliche Pro-Smoke beweist die Erreichbarkeit des Auth-Flows, nicht eine vollständige authentifizierte Pro-Endabnahme.

## GitHub-Gates

`scripts/test_bootstrap_github_release.py` überprüft den realen Git-Stash, Binär-Backup, Git-Bundle-Verifikation, HTTPS-Fast-Forward und wichtige Abbruchfälle mit isolierten lokalen Git-Repositories. `scripts/test_release_from_github.py` prüft die verbleibenden positiven und negativen Deployment-Verträge mit lokalen Git-/Docker-/HTTP-Mocks. Der Workflow `.github/workflows/release-safety.yml` führt die Tests aus; `.github/workflows/shell-syntax.yml` prüft außerdem die Bash-Syntax. Zusätzlich müssen die unveränderten Haupt-CI-, Browser- und Dependency-Security-Gates für den Release-Branch bestehen.
