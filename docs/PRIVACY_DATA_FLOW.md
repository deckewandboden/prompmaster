# PromptMaster Pro — Datenschutz- und Datenflussvertrag

## Prompt-Komposition

PromptMaster Pro verwendet den serverseitigen Composer unter `/api/v1/prompts/compose/`.

Ablauf:

1. Browser übermittelt die für den gewählten Task notwendigen Eingaben über HTTPS.
2. Server prüft Login, aktive PromptMaster-Pro-Lizenz, Gerätebindung, PromptMaster-Entitlement und Microsoft-Tier.
3. Der Composer erzeugt den Prompt deterministisch aus der veröffentlichten Prompt-Version.
4. Eingabefelder und erzeugter Prompt werden durch den Composer **nicht persistiert**.
5. API-Antworten sind `Cache-Control: no-store`.
6. Audit-/Security-Logs enthalten keine Promptinhalte und keine freien Eingabefelder.
7. Die eigentliche KI-Ausführung findet weiterhin in Microsoft Copilot statt; PromptMaster betreibt dafür kein eigenes generatives Modell.

## Ratings

Gespeichert werden auf bewusste Nutzeraktion:

- Task-/Prompt-Version
- Benutzer
- 1–5 Sterne
- optionales Textfeedback nur bei 1–3 Sternen

Bei 4–5 Sternen wird Freitext serverseitig entfernt.

## Datenauskunft

`/portal/privacy/export/` liefert eine JSON-Auskunft der zum angemeldeten Benutzer gespeicherten PromptMaster-Daten. Secrets, Token-Hashes, fremde Benutzer- und rohe Providerdaten sind ausgeschlossen.

## Marketing-/Golden-Master-Hinweis

Historische Texte, die eine ausschließlich lokale Browser-Komposition behaupten, dürfen bei Aktivierung des Server-Composers nicht als aktuelle Datenschutzaussage verwendet werden. Die bytegenauen Golden-Master werden als Regression-Referenzen unverändert erhalten; aktuelle Marketing-/Datenschutztexte müssen den realen Datenfluss beschreiben.
