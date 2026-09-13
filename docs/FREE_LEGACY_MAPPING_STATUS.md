# Free Legacy → PM20 Mapping Status

## Status

**Noch kein fachlich freigegebenes Mapping. Keine Zuordnung wird geraten.**

Der exakte aktuelle Free-Golden-Master enthält 16 Free-Kernaufgaben mit historischen IDs. Diese werden in `PromptLegacyContract` vollständig erhalten und durch den Free-Golden-Master-Hash abgesichert.

Historische IDs:

- `chat_sum`
- `chat_write`
- `out_reply`
- `out_improve`
- `out_cal_next`
- `out_cal_schedule`
- `out_todo_create`
- `out_todo_prioritize`
- `teams_notes`
- `teams_chat`
- `word_rewrite`
- `word_sum`
- `excel_explain`
- `excel_compare`
- `ppt_outline`
- `ppt_rewrite`

Die fachliche Semantik überschneidet sich teilweise mit PM20, aber die wiedergefundenen Quellen enthalten keinen verbindlichen maschinenfesten Legacy→PM20-Vertrag. Deshalb bleibt `mapping_status=unmapped` und die serverseitige Free-Komposition fail-closed (`free_mapping_pending`).

Die bestehende Free-HTML bleibt davon unberührt und weiter eigenständig nutzbar. Vor einem Mapping sind pro Legacy-Task Titel, Eingabefelder, Ausgabe, Microsoft-Tier, Semantik und Golden-Output gegen die geeignete PM20-Definition zu prüfen.
