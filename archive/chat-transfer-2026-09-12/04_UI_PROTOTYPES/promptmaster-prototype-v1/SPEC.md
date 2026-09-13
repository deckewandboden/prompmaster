# PromptMaster V1 – Funktions-Freeze

## Lizenzierung
- Free ohne Konto.
- Pro mit Login.
- Jede neu gekaufte Pro-Lizenz: 365 Tage ab erfolgreicher Mollie-Zahlung.
- Nachgekaufte Seats haben eigene Laufzeit.
- Verlängerung vor Ablauf: +365 Tage auf bestehendes Ablaufdatum.
- Verlängerung nach Ablauf: 365 Tage ab erfolgreicher Zahlung.
- Reminder: T-60 und T-30 per E-Mail plus In-App-Warnung.
- Maximal 2 Geräte je Pro-Benutzer.
- Geräte entfernen: Firmen-Admin oder netstyle.
- Einladung: 24 Stunden.

## Firma / Rollen
- V1 exakt 1 Firmen-Admin.
- Architektur für mehrere Admins erweiterbar.
- 2FA Pflicht für Firmen-Admin sowie alle netstyle-Rollen.
- netstyle-Rollen: Superadmin, Vertrieb/Support, Technik/Operations.

## Zahlung
- Mollie.
- Keine eigene Rechnungsengine.
- Refund: taggenau anteilig; Ausführung via Mollie.
- Chargeback: Lizenz vorläufig sperren, Daten bleiben erhalten.

## Betrieb
- System & Betrieb im netstyle-Backend: CPU, RAM, Storage, DB-Größe, Dienste, Backup, Restore-Test, Integrationen, Warnungen.
- Operations API vorbereitet für späteres Techniker-Dashboard.
- Service Account nur `ops.read`.

## Mail
- Staging: Mailpit.
- Produktion: Provider abstrahiert; Microsoft 365 / Graph bevorzugt.

## Recht / Datenschutz
- AGB/Datenschutz/Widerruf versioniert.
- Zustimmungen protokolliert.
- Löschung/Retention regelbasiert.
