"""Compatibility contract between the visible Free surface and PROMPTFINISHER Pro.

Every task card shown in the reviewed Free 1.2.4 surface must be executable in
PROMPTFINISHER Pro.  The 16 actual Free tasks remain backed by persisted
PromptLegacyContract rows.  The 17 purple Pro-preview cards are explicit
server-side compatibility contracts so the Free marketing surface can never
advertise a task that the paid product does not provide.
"""
from __future__ import annotations


FREE_TO_PRO_APP_CODE = {
    'chat': 'copilot_chat',
    'outlook': 'outlook',
    'teams': 'teams',
    'word': 'word',
    'excel': 'excel',
    'powerpoint': 'powerpoint',
}


AUDIENCE_DISPLAY = {
    'self': 'Eigene Verwendung',
    'customer': 'Kunde / extern',
    'internal': 'Intern / Kolleg:innen',
    'participants': 'Besprechungsteilnehmende',
    'own_tasks': 'Eigene Aufgaben',
    'team': 'Team / Projekt',
}


FREE_INPUT_META = {
    'chat_sum': {
        'primary': 'Was soll die Zusammenfassung leisten?',
        'secondary': 'Welchen Inhalt soll Copilot zusammenfassen?',
    },
    'chat_write': {
        'primary': 'Welchen Text soll Copilot erstellen?',
        'secondary': 'Welche Fakten und Vorgaben müssen berücksichtigt werden?',
    },
    'out_reply': {
        'primary': 'Was soll die Antwort erreichen?',
        'secondary': 'Welche zusätzlichen Fakten oder Vorgaben gelten?',
    },
    'out_improve': {
        'primary': 'Wie soll der E-Mail-Entwurf verbessert werden?',
        'secondary': 'Was muss unverändert erhalten bleiben?',
    },
    'out_cal_next': {
        'primary': 'Welchen Termin suchen Sie?',
        'secondary': 'Gibt es einen relevanten Zeitraum oder weitere Suchkriterien?',
    },
    'out_cal_schedule': {
        'primary': 'Welchen Termin möchten Sie planen?',
        'secondary': 'Welche Terminbedingungen sollen berücksichtigt werden?',
    },
    'out_todo_create': {
        'primary': 'Aus welchem Thema oder Vorgang sollen Aufgaben entstehen?',
        'secondary': 'Welche zusätzlichen Informationen sind für die Aufgaben relevant?',
    },
    'out_todo_prioritize': {
        'primary': 'Welche Aufgaben sollen priorisiert werden?',
        'secondary': 'Welche Priorisierungskriterien gelten?',
    },
    'teams_notes': {
        'primary': 'Welche Besprechungsnotizen sollen nachbereitet werden?',
        'secondary': 'Was soll bei der Nachbereitung besonders berücksichtigt werden?',
    },
    'teams_chat': {
        'primary': 'Welchen Teams-Chat soll Copilot zusammenfassen?',
        'secondary': 'Worauf soll sich die Zusammenfassung konzentrieren?',
    },
    'word_rewrite': {
        'primary': 'Wie soll der Word-Text überarbeitet werden?',
        'secondary': 'Welche Inhalte müssen unverändert bleiben?',
    },
    'word_sum': {
        'primary': 'Was soll die Zusammenfassung besonders herausstellen?',
        'secondary': 'Gibt es besondere Vorgaben zur Zusammenfassung?',
    },
    'excel_explain': {
        'primary': 'Was möchten Sie aus den Daten verstehen?',
        'secondary': 'Welche Datenbereiche oder Kennzahlen sind besonders relevant?',
    },
    'excel_compare': {
        'primary': 'Was genau soll verglichen werden?',
        'secondary': 'Welche Vergleichskriterien oder Grenzen gelten?',
    },
    'ppt_outline': {
        'primary': 'Worum soll es in der Präsentation gehen?',
        'secondary': 'Welche Fakten oder Inhalte müssen verwendet werden?',
    },
    'ppt_rewrite': {
        'primary': 'Wie sollen die Folientexte verbessert werden?',
        'secondary': 'Was muss unverändert erhalten bleiben?',
    },
}


# These are the 17 purple PROMPTFINISHER-Pro cards shown on the Free surface.
# They are deliberately task-specific rather than aliases with hidden semantics.
FREE_SURFACE_PRO_CONTRACTS = {
    'chat_compare': {
        'app_code': 'copilot_chat',
        'title': 'Informationen vergleichen',
        'area': 'Analyse',
        'family': 'compare',
        'intent': 'Vergleiche die angegebenen Informationen systematisch, arbeite Gemeinsamkeiten und Unterschiede heraus und benenne relevante Entscheidungspunkte, Risiken und offene Fragen.',
        'required': ['Zu vergleichende Informationen'],
        'optional': ['Vergleichskriterien', 'Entscheidungsziel'],
        'sources': ['provided', 'webwork'],
        'outputs': ['Vergleich', 'Entscheidungsvorlage'],
        'focus': ['Gemeinsamkeiten', 'Unterschiede', 'Risiken', 'Kosten / Auswirkungen', 'Entscheidungspunkte'],
        'audiences': ['Management', 'Fachbereich', 'Einkauf'],
        'minimum_tier_rank': 0,
    },
    'chat_brief': {
        'app_code': 'copilot_chat',
        'title': 'Management-Briefing',
        'area': 'Analyse',
        'family': 'summarize',
        'intent': 'Erstelle aus den angegebenen Inhalten ein kompaktes Management-Briefing mit Kernaussagen, Auswirkungen, Risiken, offenen Punkten und klaren nächsten Schritten.',
        'required': ['Thema / Informationsgrundlage'],
        'optional': ['Entscheidungsfrage', 'Zeitraum'],
        'sources': ['provided', 'webwork'],
        'outputs': ['Management-Briefing', 'Management Summary'],
        'focus': ['Kernaussagen', 'Risiken', 'Auswirkungen', 'Entscheidungen', 'Nächste Schritte'],
        'audiences': ['Management'],
        'minimum_tier_rank': 0,
    },
    'out_thread': {
        'app_code': 'outlook',
        'title': 'E-Mail-Verlauf analysieren',
        'area': 'E-Mail',
        'family': 'analysis',
        'intent': 'Analysiere den relevanten E-Mail-Verlauf chronologisch und arbeite Kernaussagen, Entscheidungen, offene Fragen, Zusagen und nächste Schritte nachvollziehbar heraus.',
        'required': ['E-Mail-Verlauf / Bezug'],
        'optional': ['Zeitraum', 'konkrete Fragestellung'],
        'sources': ['work'],
        'outputs': ['Threadanalyse', 'Strukturierte Zusammenfassung'],
        'focus': ['Kernaussagen', 'Offene Fragen', 'Zusagen', 'Termine', 'Nächste Schritte'],
        'audiences': ['Eigene Verwendung', 'Management', 'intern'],
        'minimum_tier_rank': 0,
    },
    'out_actions': {
        'app_code': 'outlook',
        'title': 'Aufgaben und Termine extrahieren',
        'area': 'E-Mail',
        'family': 'analysis',
        'intent': 'Extrahiere aus der relevanten Outlook-Kommunikation ausschließlich belegte Aufgaben, Verantwortlichkeiten, Fristen, Termine und offene Abhängigkeiten.',
        'required': ['Kommunikation / Bezug'],
        'optional': ['Zeitraum', 'Beteiligte'],
        'sources': ['work'],
        'outputs': ['Extraktion', 'Aufgabenliste'],
        'focus': ['Aufgaben', 'Verantwortliche', 'Fristen', 'Termine', 'Abhängigkeiten'],
        'audiences': ['Eigene Verwendung', 'Projektleitung', 'intern'],
        'minimum_tier_rank': 0,
    },
    'out_meeting_prep': {
        'app_code': 'outlook',
        'title': 'Besprechung vorbereiten',
        'area': 'Kalender',
        'family': 'analysis',
        'intent': 'Bereite die angegebene Besprechung aus dem verfügbaren Outlook-Arbeitskontext vor und verdichte Ziele, relevante Vorgeschichte, offene Punkte, Entscheidungen und notwendige Vorbereitung.',
        'required': ['Besprechung / Termin'],
        'optional': ['Teilnehmer', 'Vorbereitungsziel'],
        'sources': ['work'],
        'outputs': ['Meeting Briefing', 'Vorbereitungsübersicht'],
        'focus': ['Ziel', 'Vorgeschichte', 'Offene Punkte', 'Teilnehmer', 'Entscheidungen'],
        'audiences': ['Eigene Verwendung', 'Management', 'Projektleitung'],
        'minimum_tier_rank': 0,
    },
    'out_cal_conflicts': {
        'app_code': 'outlook',
        'title': 'Kalender und Konflikte analysieren',
        'area': 'Kalender',
        'family': 'analysis',
        'intent': 'Analysiere die angegebene Terminlage, identifiziere Überschneidungen, Engpässe und erkennbare Konflikte und schlage nachvollziehbare alternative Zeitfenster vor.',
        'required': ['Zeitraum / Terminlage'],
        'optional': ['Beteiligte', 'Prioritäten / Einschränkungen'],
        'sources': ['work'],
        'outputs': ['Kalenderanalyse', 'Alternativvorschläge'],
        'focus': ['Konflikte', 'Verfügbarkeit', 'Prioritäten', 'Pufferzeiten', 'Alternativen'],
        'audiences': ['Eigene Verwendung', 'Besprechungsteilnehmende'],
        'minimum_tier_rank': 0,
    },
    'out_todo_extract': {
        'app_code': 'outlook',
        'title': 'Aufgaben aus Arbeitskontext ableiten',
        'area': 'To Do',
        'family': 'analysis',
        'intent': 'Leite aus dem verfügbaren Outlook-Arbeitskontext konkrete, belegte Aufgaben ab und ordne Verantwortliche, Fristen, Abhängigkeiten und offene Informationen zu.',
        'required': ['Arbeitskontext / Thema'],
        'optional': ['Zeitraum', 'Beteiligte'],
        'sources': ['work'],
        'outputs': ['Aufgabenanalyse', 'Aufgabenliste'],
        'focus': ['Aufgaben', 'Verantwortliche', 'Fristen', 'Abhängigkeiten', 'Offene Informationen'],
        'audiences': ['Eigene Verwendung', 'Team / Projekt'],
        'minimum_tier_rank': 0,
    },
    'out_todo_week': {
        'app_code': 'outlook',
        'title': 'Wochenplanung aus Aufgaben erstellen',
        'area': 'To Do',
        'family': 'plan',
        'intent': 'Überführe die angegebenen Aufgaben und Termine in eine realistische Wochenplanung und berücksichtige Prioritäten, Fristen, Abhängigkeiten, Zeitbedarf und erkennbare Konflikte.',
        'required': ['Aufgaben und Termine'],
        'optional': ['Verfügbare Zeit', 'Prioritäten / Fixtermine'],
        'sources': ['provided', 'work'],
        'outputs': ['Wochenplanung', 'Priorisierte Wochenübersicht'],
        'focus': ['Prioritäten', 'Fristen', 'Zeitbedarf', 'Abhängigkeiten', 'Konflikte'],
        'audiences': ['Eigene Verwendung', 'Team / Projekt'],
        'minimum_tier_rank': 0,
    },
    'out_calendar_rules': {
        'app_code': 'outlook',
        'title': 'Kalenderregeln vorbereiten',
        'area': 'Automatisierung',
        'family': 'plan',
        'intent': 'Strukturiere die gewünschte wiederkehrende Kalender- oder Meetingregel als klare, überprüfbare Anweisung mit Auslösern, Bedingungen, Aktionen und Ausnahmen, ohne eine Ausführung zu behaupten.',
        'required': ['Gewünschte Kalenderregel'],
        'optional': ['Ausnahmen', 'Zeitraum / Wiederholung'],
        'sources': ['provided', 'work'],
        'outputs': ['Automatisierung', 'Regelbeschreibung'],
        'focus': ['Auslöser', 'Bedingungen', 'Aktionen', 'Ausnahmen', 'Kontrollpunkte'],
        'audiences': ['Eigene Verwendung', 'IT'],
        'minimum_tier_rank': 0,
    },
    'teams_meeting': {
        'app_code': 'teams',
        'title': 'Besprechung analysieren',
        'area': 'Meeting',
        'family': 'analysis',
        'intent': 'Analysiere die angegebene Teams-Besprechung und trenne Sachstände, Entscheidungen, Aufgaben, Verantwortlichkeiten, Termine, Risiken und offene Punkte klar voneinander.',
        'required': ['Besprechung / Transkript / Notizen'],
        'optional': ['Analyseziel'],
        'sources': ['work'],
        'outputs': ['Meetinganalyse', 'Strukturierte Nachbereitung'],
        'focus': ['Entscheidungen', 'Aufgaben', 'Verantwortliche', 'Termine', 'Risiken'],
        'audiences': ['Team / Projekt', 'Management'],
        'minimum_tier_rank': 2,
    },
    'teams_mgmt': {
        'app_code': 'teams',
        'title': 'Management-Recap',
        'area': 'Meeting',
        'family': 'summarize',
        'intent': 'Verdichte die angegebene Teams-Besprechung zu einem Management-Recap mit Ergebnissen, Entscheidungen, Auswirkungen, Risiken, offenen Punkten und erforderlichen nächsten Schritten.',
        'required': ['Besprechung / Transkript / Notizen'],
        'optional': ['Entscheidungsfokus'],
        'sources': ['work'],
        'outputs': ['Management Recap', 'Management Summary'],
        'focus': ['Ergebnisse', 'Entscheidungen', 'Auswirkungen', 'Risiken', 'Nächste Schritte'],
        'audiences': ['Management'],
        'minimum_tier_rank': 2,
    },
    'word_report': {
        'app_code': 'word',
        'title': 'Strukturierten Bericht erstellen',
        'area': 'Dokument',
        'family': 'draft',
        'intent': 'Erstelle aus den angegebenen Word-Inhalten einen klar gegliederten, direkt nutzbaren Bericht mit nachvollziehbarer Struktur, Kernaussagen, Belegen und nächsten Schritten.',
        'required': ['Dokumentinhalt / Berichtsthema'],
        'optional': ['Gliederungsvorgaben', 'Ziel / Umfang'],
        'sources': ['provided', 'work'],
        'outputs': ['Bericht', 'Strukturierter Bericht'],
        'focus': ['Kernaussagen', 'Struktur', 'Belege', 'Risiken', 'Nächste Schritte'],
        'audiences': ['Management', 'Fachbereich', 'Kunde'],
        'minimum_tier_rank': 1,
    },
    'word_risk': {
        'app_code': 'word',
        'title': 'Risiken und Lücken analysieren',
        'area': 'Analyse',
        'family': 'analysis',
        'intent': 'Prüfe den angegebenen Word-Inhalt auf Risiken, Informationslücken, Widersprüche, unklare Aussagen und fehlende Belege und trenne Befund und Empfehlung.',
        'required': ['Dokument / Inhalt'],
        'optional': ['Prüffokus'],
        'sources': ['provided', 'work'],
        'outputs': ['Analyse', 'Risiko- und Lückenbericht'],
        'focus': ['Risiken', 'Informationslücken', 'Widersprüche', 'Unklare Aussagen', 'Belege'],
        'audiences': ['Management', 'Fachbereich', 'IT'],
        'minimum_tier_rank': 1,
    },
    'excel_trends': {
        'app_code': 'excel',
        'title': 'Trends und Auffälligkeiten',
        'area': 'Analyse',
        'family': 'data',
        'intent': 'Analysiere die angegebenen Excel-Daten auf Trends, Ausreißer, relevante Abweichungen und auffällige Entwicklungen und trenne Datenbefund von Interpretation.',
        'required': ['Datenbereich / Kennzahlen'],
        'optional': ['Zeitraum', 'Vergleichsbasis'],
        'sources': ['data', 'work'],
        'outputs': ['Analyse', 'Trendübersicht'],
        'focus': ['Trends', 'Ausreißer', 'Abweichungen', 'Top-/Flop-Werte', 'Datenqualität'],
        'audiences': ['Management', 'Controlling', 'Fachbereich'],
        'minimum_tier_rank': 1,
    },
    'excel_mgmt': {
        'app_code': 'excel',
        'title': 'Management-Auswertung',
        'area': 'Analyse',
        'family': 'data',
        'intent': 'Verdichte die angegebenen Excel-Daten zu einer Management-Auswertung mit relevanten Kennzahlen, Abweichungen, wirtschaftlichen Auswirkungen, Risiken und Handlungsbedarf.',
        'required': ['Datenbereich / Kennzahlen'],
        'optional': ['Zielwerte / Vergleich', 'Zeitraum'],
        'sources': ['data', 'work'],
        'outputs': ['Managementanalyse', 'Management Summary'],
        'focus': ['Kennzahlen', 'Abweichungen', 'Kosten', 'Umsatz', 'Risiken', 'Handlungsbedarf'],
        'audiences': ['Management', 'Controlling'],
        'minimum_tier_rank': 1,
    },
    'ppt_analyze': {
        'app_code': 'powerpoint',
        'title': 'Präsentation analysieren',
        'area': 'Analyse',
        'family': 'analysis',
        'intent': 'Analysiere die angegebene Präsentation auf Redundanzen, unklare Kernaussagen, fehlende Belege, Zielgruppenfit, Storyline und konkretes Verbesserungspotenzial.',
        'required': ['Präsentation / Folieninhalt'],
        'optional': ['Ziel / Zielgruppe'],
        'sources': ['provided', 'work'],
        'outputs': ['Analyse', 'Verbesserungsbericht'],
        'focus': ['Redundanzen', 'Kernaussagen', 'Storyline', 'Zielgruppenfit', 'Verbesserungspotenzial'],
        'audiences': ['Management', 'Fachbereich', 'Kunde'],
        'minimum_tier_rank': 1,
    },
    'ppt_exec': {
        'app_code': 'powerpoint',
        'title': 'Executive Summary',
        'area': 'Analyse',
        'family': 'summarize',
        'intent': 'Verdichte die angegebene Präsentation zu einer Executive Summary mit zentralen Aussagen, Kennzahlen, Entscheidungen, Risiken und erforderlichen nächsten Schritten.',
        'required': ['Präsentation / Folieninhalt'],
        'optional': ['Entscheidungsfrage'],
        'sources': ['provided', 'work'],
        'outputs': ['Executive Summary', 'Management Summary'],
        'focus': ['Kernaussagen', 'Kennzahlen', 'Entscheidungen', 'Risiken', 'Nächste Schritte'],
        'audiences': ['Management'],
        'minimum_tier_rank': 1,
    },
}


FREE_PRO_PREVIEW_IDS = frozenset(FREE_SURFACE_PRO_CONTRACTS)
FREE_ACTUAL_IDS = frozenset(FREE_INPUT_META)
FREE_SURFACE_IDS = FREE_ACTUAL_IDS | FREE_PRO_PREVIEW_IDS

# Free-surface functions that are already provided by an existing canonical
# PM20 task in Pro. These aliases MUST NOT be inserted as a second Pro card.
# The mapping is intentionally conservative: only clearly equivalent functions
# are collapsed; broader/specialized Free-surface functions stay distinct.
FREE_SURFACE_ALIAS_TO_PRO_ID = {
    'chat_sum': 'PM20-003',
    'chat_write': 'PM20-004',
    'out_reply': 'PM20-007',
    'teams_notes': 'PM20-012',
    'teams_chat': 'PM20-011',
    'word_rewrite': 'PM20-017',
    'word_sum': 'PM20-018',
    'chat_compare': 'PM20-002',
    'out_thread': 'PM20-008',
    'out_actions': 'PM20-009',
    'out_meeting_prep': 'PM20-010',
    'word_risk': 'PM20-019',
}

# The single canonical Pro card for each deduplicated alias must keep the exact
# user-visible Free title.  This makes Free visibly a strict subset of Pro
# without creating duplicate cards or duplicate prompt implementations.
FREE_SURFACE_ALIAS_TITLES = {
    'chat_sum': 'Inhalt zusammenfassen',
    'chat_write': 'Text erstellen',
    'out_reply': 'E-Mail-Antwort vorbereiten',
    'teams_notes': 'Nachbereitung formulieren',
    'teams_chat': 'Chat zusammenfassen',
    'word_rewrite': 'Text verbessern',
    'word_sum': 'Dokument zusammenfassen',
    'chat_compare': 'Informationen vergleichen',
    'out_thread': 'E-Mail-Verlauf analysieren',
    'out_actions': 'Aufgaben und Termine extrahieren',
    'out_meeting_prep': 'Besprechung vorbereiten',
    'word_risk': 'Risiken und Lücken analysieren',
}

if set(FREE_SURFACE_ALIAS_TITLES) != set(FREE_SURFACE_ALIAS_TO_PRO_ID):
    raise RuntimeError('Free→Pro alias title contract is incomplete.')

FREE_SURFACE_ALIAS_IDS = frozenset(FREE_SURFACE_ALIAS_TO_PRO_ID)
FREE_SURFACE_UNIQUE_IDS = FREE_SURFACE_IDS - FREE_SURFACE_ALIAS_IDS
FREE_ACTUAL_UNIQUE_IDS = FREE_ACTUAL_IDS - FREE_SURFACE_ALIAS_IDS
FREE_PRO_PREVIEW_UNIQUE_IDS = FREE_PRO_PREVIEW_IDS - FREE_SURFACE_ALIAS_IDS
