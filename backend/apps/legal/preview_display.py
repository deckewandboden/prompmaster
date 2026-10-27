"""Public preview: transparent language disclosure for canonical German law.

No translated legal document bodies are published or approved by this module.
Keep exact notices consistent with the isolated legal integration branch.
"""

FALLBACK_NOTICES = {
    'en': 'This legal document is currently available only in German. No approved translation is published for the selected language.',
    'es': 'Este documento legal está disponible actualmente solo en alemán. No se ha publicado ninguna traducción aprobada para el idioma seleccionado.',
    'pt': 'Este documento jurídico está atualmente disponível apenas em alemão. Não foi publicada nenhuma tradução aprovada para o idioma selecionado.',
    'tr': 'Bu hukuki belge şu anda yalnızca Almanca olarak sunulmaktadır. Seçilen dil için onaylanmış bir çeviri yayımlanmamıştır.',
    'ru': 'Этот юридический документ пока доступен только на немецком языке. Утверждённый перевод на выбранный язык не опубликован.',
    'pl': 'Ten dokument prawny jest obecnie dostępny tylko w języku niemieckim. Nie opublikowano zatwierdzonego tłumaczenia na wybrany język.',
    'fr': 'Ce document juridique est actuellement disponible uniquement en allemand. Aucune traduction approuvée n’a été publiée dans la langue sélectionnée.',
    'it': 'Questo documento legale è attualmente disponibile solo in tedesco. Non è stata pubblicata una traduzione approvata nella lingua selezionata.',
    'nl': 'Dit juridische document is momenteel alleen in het Duits beschikbaar. Er is geen goedgekeurde vertaling gepubliceerd voor de geselecteerde taal.',
}


def legal_preview_notice(language):
    """Return a clear disclosure whenever UI language differs from DE."""
    lang = (language or 'de').strip().lower().split('-', 1)[0]
    if lang == 'de':
        return ''
    return FALLBACK_NOTICES.get(lang, FALLBACK_NOTICES['en'])
