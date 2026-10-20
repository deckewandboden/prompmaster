# PROMPTFINISHER – GitHub-geführtes Update mit einem Befehl

Diese Prozedur aktualisiert eine **bereits bestehende produktive PROMPTFINISHER-Installation** aus dem geprüften Branch `main`. Es gibt **keine lokalen ZIPs, ZIP-Installer oder zusätzliche PowerShell-Dateien**. Das Release-Skript und seine automatischen Tests liegen vollständig im GitHub-Repository.

## Einziger Aufruf unter Windows/PowerShell

```powershell
ssh root@85.215.172.6 'cd /root/projekte/docker/promptmaster && git switch main && git pull --ff-only origin main && bash scripts/release_from_github.sh'
```

Die Zugangsdaten und die bestehende Produktions-`.env` verbleiben auf dem Server und werden nicht in Git übertragen. Der Befehl verwendet den vorhandenen GitHub-Checkout und verlangt gültigen SSH-Zugang. Wenn eine Prüfung fehlschlägt, wird mit einem eindeutigen Fehler abgebrochen; es erfolgt **kein** erzwungener Git-Reset.

## Was der Aufruf macht

1. Wechselt auf `main`, zieht ausschließlich Fast-Forward-Commits von `origin` und führt `scripts/release_from_github.sh` aus.
2. Prüft das erlaubte GitHub-Repository, saubere getrackte Dateien, die lokale Docker-Engine, private `.env`-Dateirechte und die Existenz eines bereits erfolgreich installierten Releases.
3. Synchronisiert `origin/main` nochmals kontrolliert und protokolliert die **volle Git-Commit-SHA**.
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

`scripts/test_release_from_github.py` prüft positive und negative Fälle mit lokalen Git-/Docker-/HTTP-Mocks. Der Workflow `.github/workflows/release-safety.yml` führt die Tests aus; `.github/workflows/shell-syntax.yml` prüft außerdem die Bash-Syntax. Zusätzlich müssen die unveränderten Haupt-CI-, Browser- und Dependency-Security-Gates für den Release-Branch bestehen.
