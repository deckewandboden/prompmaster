# Free Legacy → PM20 Mapping Status

## Status

**Noch kein fachlich freigegebenes Legacy→PM20-Mapping. Keine Zuordnung wird geraten.**

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

## Aktuelle Runtime

Das fehlende PM20-Mapping blockiert **nicht mehr** die serverseitige Free-Komposition. Statt die 16 Free-Aufgaben fachlich auf PM20 zu raten, wird ihr eigener geprüfter Legacy-Vertrag in der Datenbank materialisiert:

1. `seed_prompt_catalog` übernimmt für jede der 16 Aufgaben den vollständigen Free-Runtime-Vertrag in `PromptLegacyContract.payload.runtime_contract`.
2. `/api/v1/prompts/compose/` lädt bei `product=FREE` genau diesen gespeicherten Vertrag.
3. Die aktuelle Route `/free/` erzeugt den fertigen Prompt über diese API und kennzeichnet das Ergebnis als Datenbankquelle.
4. `/free-old/` bleibt als unveränderte Rollback-/Referenzroute beim lokalen Golden-Master-Composer.
5. Die Free-Komposition bleibt zustandslos; Promptinhalte werden nicht persistiert.

Damit kommt auch **PromptMaster Free im aktuellen Produkt aus der Prompt-Datenbank**, ohne eine fachlich nicht belegte Free→PM20-Zuordnung zu erfinden.

## PM20-Mapping bleibt offen

Die fachliche Semantik der 16 Free-Aufgaben überschneidet sich teilweise mit PM20. Die wiedergefundenen Quellen enthalten aber weiterhin keinen verbindlichen maschinenfesten Legacy→PM20-Vertrag. Deshalb bleibt `mapping_status=unmapped`.

Ein späteres Mapping darf erst erfolgen, wenn pro Legacy-Task Titel, Eingabefelder, Ausgabe, Microsoft-Tier, Semantik und Golden-Output gegen die geeignete PM20-Definition fachlich geprüft und explizit freigegeben wurden.
