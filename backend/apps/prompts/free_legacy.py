from __future__ import annotations

from .composer_core import PromptValidationError


TIER_RANK = {'chatbasic': 0, 'm365basic': 1, 'premium': 2}

AUDIENCE_RULES = {
    'self': 'Richte die Ausgabe an mich als Anwender. Formuliere so, dass ich das Ergebnis unmittelbar verwenden und die relevanten nächsten Schritte schnell erfassen kann.',
    'customer': 'Richte Inhalt, Wortwahl und Detailtiefe auf einen externen Geschäftskontakt aus. Formuliere verständlich, professionell und nutzenorientiert und vermeide unnötigen internen Fachjargon.',
    'internal': 'Richte die Ausgabe auf interne Kolleginnen und Kollegen aus. Formuliere klar, direkt und arbeitsbezogen.',
    'participants': 'Richte die Ausgabe auf die beteiligten Besprechungsteilnehmenden aus. Stelle Zweck, Vorbereitung und nächste Schritte eindeutig dar.',
    'own_tasks': 'Richte die Ausgabe auf meine persönliche Arbeitsplanung aus. Formuliere Aufgaben eindeutig, handlungsorientiert und direkt bearbeitbar.',
    'team': 'Richte die Ausgabe auf ein internes Team bzw. Projekt aus. Stelle Aufgaben, Verantwortlichkeiten, Termine und Abhängigkeiten klar dar.',
}

DETAIL_RULES = {
    'short': 'Halte das Ergebnis sehr kurz und beschränke dich auf die absolut wesentlichen Punkte.',
    'compact': 'Erstelle eine kompakte, aber vollständige Darstellung ohne unnötige Wiederholungen.',
}

FORMAT_LABELS = {
    'bullets': 'Stichpunkte',
    'prose': 'Fließtext',
    'email': 'E-Mail / Antwortentwurf',
    'summary': 'Kurzübersicht',
    'schedule': 'Terminvorschlag',
    'checklist': 'Checkliste',
    'priority': 'Priorisierte Liste',
    'meeting_notes': 'Besprechungsnachbereitung',
    'slide_outline': 'Foliengliederung',
    'slide_text': 'Überarbeiteter Folientext',
}

TONE_RULES = {
    'professional': 'Formuliere professionell, klar und präzise.',
    'friendly': 'Formuliere freundlich, wertschätzend und professionell.',
    'factual': 'Formuliere sachlich, neutral und ohne unnötige Wertungen.',
}

METHOD_RULES = {
    'summarize': [
        'Erhalte Bedeutung und wichtige Details.',
        'Hebe Entscheidungen, Aufgaben und offene Punkte hervor, soweit vorhanden.',
        'Übernimm Zahlen, Namen und Termine korrekt.',
        'Erfinde nichts Fehlendes.',
    ],
    'draft': [
        'Ordne die Informationen in eine klare, zielgruppengerechte Struktur.',
        'Erhalte verbindliche Fakten und Zahlen.',
        'Formuliere direkt nutzbar.',
        'Vermeide unnötige Wiederholungen.',
    ],
    'analysis': [
        'Arbeite vom konkreten Untersuchungsziel aus.',
        'Nenne Datenbasis bzw. Kontext.',
        'Trenne Beobachtung, Interpretation und Empfehlung.',
        'Mache Lücken und Unsicherheiten sichtbar.',
    ],
    'compare': [
        'Bewerte die Inhalte nach denselben Kriterien.',
        'Zeige Unterschiede und Gemeinsamkeiten.',
        'Mache Trade-offs und Risiken sichtbar.',
        'Leite Aussagen nur aus vorhandenen Fakten ab.',
    ],
    'plan': [
        'Zerlege das Ziel in konkrete Schritte.',
        'Ordne Abhängigkeiten und Reihenfolge.',
        'Kennzeichne offene Verantwortlichkeiten oder Termine.',
        'Definiere ein überprüfbares Ergebnis.',
    ],
}

QUALITY_RULES = {
    'summarize': 'Prüfe, ob keine wesentliche Aussage, Entscheidung, Frist oder Verpflichtung verloren ging.',
    'draft': 'Prüfe, ob der Entwurf direkt nutzbar ist und alle Vorgaben enthält.',
    'analysis': 'Prüfe Logikfehler, unbelegte Kausalität und fehlende Datenbasis.',
    'compare': 'Prüfe, ob alle verglichenen Inhalte nach denselben Kriterien bewertet wurden.',
    'plan': 'Prüfe, ob die Schritte ausführbar, geordnet und auf ein klares Ergebnis ausgerichtet sind.',
}

APP_META = {
    'chat': {
        'name': 'Copilot Chat',
        'min_tier': 0,
        'rule': 'Nutze nur Quellen und Arbeitsdaten, auf die im gewählten Copilot-Kontext tatsächlich Zugriff besteht. Erfinde keine Unternehmensdaten und behaupte keinen Zugriff auf nicht bereitgestellte interne Informationen.',
        'basic_grounding': 'Nutze Webinformationen sowie Inhalte, die ich ausdrücklich in diesen Chat einfüge, hochlade oder referenziere. Gehe nicht davon aus, dass automatisch Zugriff auf weitere Unternehmensdaten besteht.',
        'premium_grounding': 'Priorisiere den aktuellen Arbeitskontext.',
    },
    'outlook': {
        'name': 'Outlook',
        'min_tier': 0,
        'rule': 'Beziehe dich nur auf E-Mails, Threads, Kalender- oder Meetinginformationen, die im aktuellen Kontext tatsächlich verfügbar sind. Stelle keine Nachricht als gesendet und keine Terminänderung als ausgeführt dar, solange keine bestätigte Aktion vorliegt.',
        'basic_grounding': 'Nutze den in Outlook tatsächlich verfügbaren aktuellen Kontext sowie Inhalte, die ich ausdrücklich bereitstelle oder referenziere. Wenn weiterer Kontext benötigt wird, nenne konkret, was fehlt.',
        'premium_grounding': 'Nutze den relevanten Outlook-Kontext als primäre Quelle und ergänze – soweit sinnvoll und verfügbar – Kalendertermine, Besprechungen, Anhänge, Teams-Kontext sowie passende Dateien aus OneDrive oder SharePoint.',
    },
    'teams': {
        'name': 'Teams',
        'min_tier': 0,
        'rule': 'Verwende nur Chats, Kanalbeiträge, Besprechungsnotizen, Transkripte oder Meetinginhalte, die im aktuellen Kontext tatsächlich verfügbar oder ausdrücklich bereitgestellt sind. Kennzeichne Verantwortlichkeiten, Beschlüsse und Termine als offen, wenn sie nicht eindeutig belegt sind.',
        'basic_grounding': 'Nutze ausschließlich den Teams-Inhalt, den ich dir im aktuellen Kontext tatsächlich bereitstelle, einfüge oder eindeutig referenziere. Gehe ohne Premium-Arbeitskontext nicht von automatisch verfügbarem Chat-, Kanal- oder Meetingwissen aus.',
        'premium_grounding': 'Nutze den relevanten Teams-Kontext als primäre Quelle und ergänze – soweit verfügbar – Chat-, Meeting- oder Dateikontext.',
    },
    'word': {
        'name': 'Word',
        'min_tier': 1,
        'rule': 'Arbeite mit dem geöffneten bzw. bereitgestellten Dokument und ausdrücklich referenzierten Quellen. Erhalte belegte Fakten, Zahlen, Namen und Anforderungen, sofern keine Änderung verlangt wurde.',
        'basic_grounding': 'Nutze das aktuell geöffnete bzw. von mir bereitgestellte Word-Dokument. Ziehe keine weiteren Unternehmensdaten automatisch hinzu.',
        'premium_grounding': 'Nutze das aktuelle Word-Dokument als primäre Quelle und ergänze nur tatsächlich relevante Microsoft-365-Arbeitsinformationen.',
    },
    'excel': {
        'name': 'Excel',
        'min_tier': 1,
        'rule': 'Beziehe Berechnungen und Aussagen ausschließlich auf den tatsächlich verfügbaren Datenbereich. Benenne Annahmen, fehlende Werte und Datenqualitätsprobleme und erfinde keine Kennzahlen.',
        'basic_grounding': 'Nutze die aktuell geöffnete bzw. von mir bereitgestellte Excel-Tabelle und die darin vorhandenen Daten. Erfinde keine Werte.',
        'premium_grounding': 'Nutze die aktuelle Arbeitsmappe als primäre Datenquelle und ergänze nur relevanten Arbeitskontext.',
    },
    'powerpoint': {
        'name': 'PowerPoint',
        'min_tier': 1,
        'rule': 'Erhalte belegte Fakten aus der aktuellen Präsentation und ausdrücklich referenzierten Quellen. Erfinde keine Kennzahlen, Referenzen oder Ergebnisse und trenne Folieninhalt von optionalen Erläuterungen.',
        'basic_grounding': 'Nutze die aktuell geöffnete bzw. von mir bereitgestellte Präsentation und ausdrücklich hinzugefügte Quellen.',
        'premium_grounding': 'Nutze die aktuelle Präsentation als primäre Quelle und ergänze nur relevante, tatsächlich verfügbare Arbeitsinformationen.',
    },
}


def _contract(
    *,
    app_code,
    family,
    intent,
    primary_required,
    secondary_required,
    audiences,
    formats,
    focus,
    primary_prefix,
    primary_suffix='',
    secondary_prefix='',
    secondary_suffix='',
):
    app = APP_META[app_code]
    return {
        'app_code': app_code,
        'app_name': app['name'],
        'minimum_tier_rank': app['min_tier'],
        'family': family,
        'intent': intent,
        'primary_required': primary_required,
        'secondary_required': secondary_required,
        'audiences': audiences,
        'formats': formats,
        'focus': focus,
        'primary_prefix': primary_prefix,
        'primary_suffix': primary_suffix,
        'secondary_prefix': secondary_prefix,
        'secondary_suffix': secondary_suffix,
        'app_rule': app['rule'],
        'basic_grounding': app['basic_grounding'],
        'premium_grounding': app['premium_grounding'],
    }


FREE_RUNTIME_CONTRACTS = {
    'chat_sum': _contract(
        app_code='chat', family='summarize',
        intent='Fasse die bereitgestellten Inhalte präzise zusammen und hebe die für das gewünschte Ziel relevanten Kernaussagen, Entscheidungen, offenen Punkte und nächsten Schritte hervor.',
        primary_required=True, secondary_required=False,
        audiences=['self', 'customer'], formats=['bullets', 'prose'],
        focus=['Kernaussagen', 'Entscheidungen', 'Aufgaben', 'Nächste Schritte', 'Offene Fragen', 'Termine', 'Risiken', 'Zahlen / Fakten'],
        primary_prefix='Die Zusammenfassung soll insbesondere folgendes leisten: ', primary_suffix='.',
        secondary_prefix='Verarbeite dafür folgenden bereitgestellten Inhalt: ',
    ),
    'chat_write': _contract(
        app_code='chat', family='draft',
        intent='Erstelle aus den bereitgestellten Vorgaben einen direkt nutzbaren geschäftlichen Text mit klarer Kernbotschaft, nachvollziehbarer Struktur und professioneller Tonalität.',
        primary_required=True, secondary_required=False,
        audiences=['self', 'customer'], formats=['prose', 'email'],
        focus=['Kernaussage', 'Handlungsaufforderung', 'Verständlichkeit', 'Struktur', 'Argumente', 'Nutzen', 'Einwände', 'Nächste Schritte'],
        primary_prefix='Der konkrete Schreibauftrag lautet: ', primary_suffix='.',
        secondary_prefix='Verwende dabei verbindlich folgende Fakten, Stichpunkte oder Vorgaben: ',
    ),
    'out_reply': _contract(
        app_code='outlook', family='draft',
        intent='Erstelle einen sendefertigen Antwortentwurf auf die aktuell geöffnete bzw. eindeutig ausgewählte E-Mail. Erfasse, was der Absender konkret fragt, mitteilt oder von mir erwartet, und beantworte genau diese Punkte.',
        primary_required=False, secondary_required=False,
        audiences=['customer', 'internal'], formats=['email'],
        focus=['Antwort auf Fragen', 'Offene Punkte', 'Termine', 'Nächste Schritte', 'Verbindlichkeit', 'Kundenorientierung', 'Risiken', 'Anlagen / Unterlagen'],
        primary_prefix='Das konkrete Antwortziel lautet: ', primary_suffix='.',
        secondary_prefix='Berücksichtige zusätzlich verbindlich folgende Fakten oder Vorgaben: ',
    ),
    'out_improve': _contract(
        app_code='outlook', family='draft',
        intent='Überarbeite den aktuell geöffneten bzw. bereitgestellten E-Mail-Entwurf so, dass Aussage, Fakten und Zusagen erhalten bleiben, der Text aber klarer, präziser, professioneller und leichter erfassbar wird.',
        primary_required=False, secondary_required=False,
        audiences=['customer', 'internal'], formats=['email'],
        focus=['Klarheit', 'Kürze', 'Struktur', 'Handlungsaufforderung', 'Tonalität', 'Verbindlichkeit', 'Kundenorientierung', 'Rechtschreibung'],
        primary_prefix='Das konkrete Verbesserungsziel lautet: ', primary_suffix='.',
        secondary_prefix='Folgende Aussagen oder Fakten müssen unverändert erhalten bleiben: ',
    ),
    'out_cal_next': _contract(
        app_code='outlook', family='analysis',
        intent='Ermittle im verfügbaren Outlook-Kalender den nächsten zukünftigen Termin, der zum angegebenen Suchkriterium passt, und gib die relevanten Termindetails eindeutig aus.',
        primary_required=True, secondary_required=False,
        audiences=['self'], formats=['bullets', 'summary'],
        focus=['Datum / Uhrzeit', 'Betreff', 'Teilnehmer', 'Ort / Teams-Link', 'Terminbezug', 'Vorbereitung', 'Konflikte', 'Nächste Schritte'],
        primary_prefix='Suche konkret nach folgendem Terminbezug: ', primary_suffix='.',
        secondary_prefix='Berücksichtige zusätzlich folgende Eingrenzung: ',
    ),
    'out_cal_schedule': _contract(
        app_code='outlook', family='plan',
        intent='Bereite auf Grundlage der angegebenen Terminanforderungen einen konkreten Outlook-Termin vor und berücksichtige Zweck, Teilnehmer, Zeitraum, Dauer sowie erkennbare Konflikte oder Einschränkungen.',
        primary_required=True, secondary_required=False,
        audiences=['self', 'participants'], formats=['schedule', 'bullets'],
        focus=['Teilnehmer', 'Zeitraum', 'Dauer', 'Verfügbarkeit', 'Konflikte', 'Betreff', 'Agenda', 'Ort / Teams'],
        primary_prefix='Die Terminanforderung lautet: ', primary_suffix='.',
        secondary_prefix='Berücksichtige zusätzlich folgende Rahmenbedingungen: ',
    ),
    'out_todo_create': _contract(
        app_code='outlook', family='plan',
        intent='Erstelle aus dem konkret angegebenen Thema oder Vorgang eine handlungsorientierte Aufgabenliste und leite nur solche nächsten Schritte ab, die aus dem verfügbaren Kontext tatsächlich begründet sind.',
        primary_required=True, secondary_required=False,
        audiences=['own_tasks', 'team'], formats=['checklist', 'bullets'],
        focus=['Konkrete Aufgabe', 'Priorität', 'Fälligkeit', 'Verantwortliche', 'Abhängigkeiten', 'Offene Informationen', 'Terminbezug', 'Nächste Schritte'],
        primary_prefix='Die Aufgaben sollen aus folgendem Thema bzw. Vorgang abgeleitet werden: ', primary_suffix='.',
        secondary_prefix='Berücksichtige zusätzlich folgende Vorgaben oder Rahmenbedingungen: ',
    ),
    'out_todo_prioritize': _contract(
        app_code='outlook', family='analysis',
        intent='Priorisiere ausschließlich die angegebenen Aufgaben anhand von Dringlichkeit, geschäftlicher Auswirkung, Fälligkeiten und erkennbaren Abhängigkeiten und begründe die Reihenfolge nachvollziehbar.',
        primary_required=True, secondary_required=False,
        audiences=['own_tasks', 'team'], formats=['priority', 'bullets'],
        focus=['Dringlichkeit', 'Auswirkung', 'Fälligkeit', 'Abhängigkeiten', 'Blockaden', 'Verantwortliche', 'Zeitbedarf', 'Reihenfolge'],
        primary_prefix='Zu priorisieren sind folgende Aufgaben: ', primary_suffix='.',
        secondary_prefix='Verwende zusätzlich folgende Priorisierungskriterien: ',
    ),
    'teams_notes': _contract(
        app_code='teams', family='summarize',
        intent='Erstelle aus den bereitgestellten Besprechungsnotizen eine belastbare Nachbereitung und trenne Sachstände, Entscheidungen, Aufgaben, Verantwortlichkeiten, Termine und offene Punkte klar voneinander.',
        primary_required=True, secondary_required=False,
        audiences=['self', 'team'], formats=['meeting_notes', 'bullets'],
        focus=['Entscheidungen', 'Aufgaben', 'Verantwortliche', 'Termine', 'Offene Fragen', 'Risiken', 'Beschlüsse', 'Nächste Schritte'],
        primary_prefix='Verwende als Grundlage folgende Besprechungsnotizen: ',
        secondary_prefix='Lege dabei besonderen Wert auf: ', secondary_suffix='.',
    ),
    'teams_chat': _contract(
        app_code='teams', family='summarize',
        intent='Fasse den bereitgestellten oder eindeutig referenzierten Teams-Chat so zusammen, dass Verlauf, Ergebnisse, Entscheidungen, offene Fragen und nächste Schritte ohne erneutes Lesen verständlich werden.',
        primary_required=True, secondary_required=False,
        audiences=['self', 'team'], formats=['bullets', 'prose'],
        focus=['Kernaussagen', 'Entscheidungen', 'Offene Fragen', 'Aufgaben', 'Verantwortliche', 'Termine', 'Risiken', 'Nächste Schritte'],
        primary_prefix='Der auszuwertende Teams-Kontext ist: ', primary_suffix='.',
        secondary_prefix='Konzentriere die Zusammenfassung besonders auf: ', secondary_suffix='.',
    ),
    'word_rewrite': _contract(
        app_code='word', family='draft',
        intent='Überarbeite den aktuell markierten bzw. bereitgestellten Word-Text und verbessere Verständlichkeit, Struktur und sprachliche Präzision, ohne fachliche Aussagen, Zahlen, Namen oder verbindliche Inhalte unbeabsichtigt zu verändern.',
        primary_required=False, secondary_required=False,
        audiences=['self', 'customer'], formats=['prose'],
        focus=['Verständlichkeit', 'Kürze', 'Struktur', 'Kernaussage', 'Tonalität', 'Zielgruppenbezug', 'Redundanzen', 'Handlungsaufforderung'],
        primary_prefix='Das konkrete Überarbeitungsziel lautet: ', primary_suffix='.',
        secondary_prefix='Folgende Inhalte müssen unverändert erhalten bleiben: ',
    ),
    'word_sum': _contract(
        app_code='word', family='summarize',
        intent='Fasse das aktuell geöffnete bzw. bereitgestellte Word-Dokument so zusammen, dass die wesentlichen Inhalte, Zahlen, Termine, Entscheidungen, Risiken und offenen Punkte ohne erneutes Lesen nachvollziehbar sind.',
        primary_required=False, secondary_required=False,
        audiences=['self', 'customer'], formats=['bullets', 'prose'],
        focus=['Kernaussagen', 'Aufgaben', 'Termine', 'Kosten', 'Risiken', 'Entscheidungen', 'Offene Punkte', 'Nächste Schritte'],
        primary_prefix='Die Zusammenfassung soll besonders folgendes herausstellen: ', primary_suffix='.',
        secondary_prefix='Berücksichtige zusätzlich folgende Vorgaben: ',
    ),
    'excel_explain': _contract(
        app_code='excel', family='analysis',
        intent='Analysiere die aktuell geöffnete bzw. bereitgestellte Excel-Tabelle und erkläre die wichtigsten erkennbaren Kennzahlen, Muster, Zusammenhänge und Auffälligkeiten verständlich und datenbasiert.',
        primary_required=False, secondary_required=False,
        audiences=['self', 'customer'], formats=['bullets', 'prose'],
        focus=['Kennzahlen', 'Trends', 'Abweichungen', 'Top-/Flop-Werte', 'Kosten', 'Umsatz', 'Datenqualität', 'Auffälligkeiten'],
        primary_prefix='Die konkrete Analysefrage lautet: ', primary_suffix='.',
        secondary_prefix='Berücksichtige besonders folgende Datenbereiche oder Kennzahlen: ',
    ),
    'excel_compare': _contract(
        app_code='excel', family='compare',
        intent='Vergleiche die angegebenen Bereiche oder Werte der aktuellen Excel-Tabelle systematisch, zeige absolute und – soweit mathematisch sinnvoll – prozentuale Veränderungen und trenne den Datenbefund von möglichen Erklärungen.',
        primary_required=True, secondary_required=False,
        audiences=['self', 'customer'], formats=['bullets', 'summary'],
        focus=['Differenzen', 'Prozentänderung', 'Trends', 'Abweichungen', 'Top-/Flop-Werte', 'Kosten', 'Umsatz', 'Erklärungsbedarf'],
        primary_prefix='Verglichen werden sollen konkret: ', primary_suffix='.',
        secondary_prefix='Wende dabei zusätzlich folgende Vergleichskriterien oder Grenzen an: ',
    ),
    'ppt_outline': _contract(
        app_code='powerpoint', family='draft',
        intent='Erstelle auf Grundlage der angegebenen Präsentationsaufgabe eine klare PowerPoint-Gliederung mit nachvollziehbarer Storyline, aussagekräftigen Folientiteln und prägnanten Kernbotschaften.',
        primary_required=True, secondary_required=False,
        audiences=['self', 'customer'], formats=['slide_outline'],
        focus=['Kernaussage', 'Storyline', 'Zielgruppenbezug', 'Zahlen / Fakten', 'Entscheidung', 'Nutzen', 'Risiken', 'Nächste Schritte'],
        primary_prefix='Die konkrete Präsentationsaufgabe lautet: ', primary_suffix='.',
        secondary_prefix='Verwende dabei verbindlich folgende vorhandene Fakten oder Inhalte: ',
    ),
    'ppt_rewrite': _contract(
        app_code='powerpoint', family='draft',
        intent='Überarbeite den ausgewählten bzw. bereitgestellten PowerPoint-Inhalt so, dass er auf Folien schnell erfassbar, prägnant und präsentationstauglich ist, ohne belegte Fakten oder verbindliche Aussagen unbeabsichtigt zu verändern.',
        primary_required=False, secondary_required=False,
        audiences=['self', 'customer'], formats=['slide_text'],
        focus=['Kernaussage', 'Kürze', 'Verständlichkeit', 'Storyline', 'Zahlen / Fakten', 'Redundanzen', 'Zielgruppenbezug', 'Handlungsbedarf'],
        primary_prefix='Das konkrete Überarbeitungsziel lautet: ', primary_suffix='.',
        secondary_prefix='Folgende Inhalte müssen unverändert erhalten bleiben: ',
    ),
}


def _required(value: str, *, field: str, message: str) -> str:
    value = str(value or '').strip()
    if not value:
        raise PromptValidationError(message, field=field, code='required')
    return value


def _choice(value: str, allowed, *, field: str) -> str:
    value = str(value or '').strip()
    if value not in allowed:
        raise PromptValidationError('Ungültige Auswahl.', field=field, code='choice')
    return value


def _grounding(runtime: dict, tier_code: str) -> str:
    if tier_code == 'premium':
        return (
            'Nutze – soweit für mich verfügbar und berechtigt – den relevanten Microsoft-365-Arbeitskontext über Work IQ. '
            + runtime['premium_grounding']
            + ' Trenne belegte Fakten, Schlussfolgerungen und Empfehlungen klar.'
        )
    return runtime['basic_grounding']


def compose_free_legacy(*, contract, microsoft_tier: str, payload: dict) -> dict:
    """Compose Free from the persisted legacy contract, including partial UI state.

    Free 1.2.4 has always rendered an incremental prompt while the user moves
    through the configurator. ready is only true once all required selections
    are complete. This keeps the database contract authoritative without
    regressing the reviewed live interaction.
    """
    if not isinstance(payload, dict):
        raise PromptValidationError('input muss ein Objekt sein.', field='input', code='choice')

    stored = contract.payload if isinstance(contract.payload, dict) else {}
    runtime = stored.get('runtime_contract')
    if not isinstance(runtime, dict):
        raise PromptValidationError(
            'Free-Legacy-Vertrag ist nicht vollständig veröffentlicht.',
            field='task_id',
            code='catalog_not_seeded',
        )

    tier_code = str(microsoft_tier or 'chatbasic').strip()
    if tier_code not in TIER_RANK:
        raise PromptValidationError(
            'Unbekannte Microsoft-Copilot-Stufe.',
            field='microsoft_tier',
            code='choice',
        )
    if TIER_RANK[tier_code] < int(runtime.get('minimum_tier_rank') or 0):
        raise PromptValidationError(
            'Die ausgewählte Microsoft-Copilot-Stufe reicht für diese Anwendung nicht aus.',
            field='microsoft_tier',
            code='tier_required',
        )

    primary = str(payload.get('primary') or '').strip()
    secondary = str(payload.get('secondary') or '').strip()

    def optional_choice(value, allowed, *, field):
        value = str(value or '').strip()
        if not value:
            return ''
        if value not in allowed:
            raise PromptValidationError('Ungültige Auswahl.', field=field, code='choice')
        return value

    audience = optional_choice(
        payload.get('audience'),
        runtime.get('audiences') or [],
        field='audience',
    )
    output = optional_choice(
        payload.get('output'),
        runtime.get('formats') or [],
        field='output',
    )
    detail = optional_choice(payload.get('detail'), DETAIL_RULES, field='detail')
    tone = optional_choice(payload.get('tone'), TONE_RULES, field='tone')

    focus = payload.get('focus') or []
    if not isinstance(focus, list):
        raise PromptValidationError('Ungültige Auswahl.', field='focus', code='choice')
    allowed_focus = set(runtime.get('focus') or [])
    normalized_focus = []
    for item in focus:
        value = str(item or '').strip()
        if value not in allowed_focus:
            raise PromptValidationError('Ungültiger Schwerpunkt.', field='focus', code='choice')
        if value and value not in normalized_focus:
            normalized_focus.append(value)

    family = str(runtime.get('family') or 'analysis')
    method = METHOD_RULES.get(family, METHOD_RULES['analysis'])
    quality = QUALITY_RULES.get(family, QUALITY_RULES['analysis'])

    parts = [str(runtime.get('intent') or '').strip()]
    context_parts = []
    if primary:
        context_parts.append(
            str(runtime.get('primary_prefix') or '')
            + primary
            + str(runtime.get('primary_suffix') or '')
        )
    if secondary:
        context_parts.append(
            str(runtime.get('secondary_prefix') or '')
            + secondary
            + str(runtime.get('secondary_suffix') or '')
        )
    context = ' '.join(part.strip() for part in context_parts if part.strip())
    if context:
        parts.append(context)

    parts.append('Arbeite dabei in folgender Reihenfolge: ' + ' '.join(method))
    if normalized_focus:
        parts.append('Lege besonderes Augenmerk auf ' + ', '.join(normalized_focus) + '.')
    if audience:
        parts.append(AUDIENCE_RULES[audience])

    output_rules = []
    if output:
        output_rules.append(f'Liefere das Ergebnis im Format „{FORMAT_LABELS[output]}“.')
    if detail:
        output_rules.append(DETAIL_RULES[detail])
    if tone:
        output_rules.append(TONE_RULES[tone])
    if output_rules:
        parts.append(' '.join(output_rules))

    parts.append('Als Informationsgrundlage gilt: ' + _grounding(runtime, tier_code))
    parts.append(
        f'Für {runtime["app_name"]} gilt zusätzlich: {runtime["app_rule"]}'
    )
    parts.append(
        'Führe abschließend diese Qualitätsprüfung durch: '
        + quality
        + ' Erfinde keine Fakten, Zahlen, Termine, Personen, Verantwortlichkeiten, Quellen oder Zusagen. '
        + 'Wenn eine notwendige Information fehlt, benenne die konkrete Lücke statt sie stillschweigend zu ergänzen.'
    )

    primary_ok = not runtime.get('primary_required') or bool(primary)
    secondary_ok = not runtime.get('secondary_required') or bool(secondary)
    ready = bool(
        primary_ok
        and secondary_ok
        and audience
        and normalized_focus
        and output
        and detail
        and tone
    )
    progress_steps = [
        True,  # application is implied by the selected legacy contract
        True,  # task is the contract addressed by this request
        primary_ok and secondary_ok,
        bool(audience),
        bool(normalized_focus),
        bool(detail),
        bool(output),
        bool(tone),
    ]
    progress_percent = round(
        sum(1 for step in progress_steps if step) / len(progress_steps) * 100
    )

    prompt = '\n\n'.join(part for part in parts if part)
    return {
        'prompt': prompt,
        'ready': ready,
        'progress_percent': progress_percent,
        'task_id': contract.legacy_id,
        'app_code': runtime['app_code'],
        'policy_version': 'FREE_1_2_4',
        'prompt_version': 'FREE_1_2_4',
        'persisted': False,
        'source': 'PromptLegacyContract',
    }
