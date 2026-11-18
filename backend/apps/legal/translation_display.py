"""Fail-closed public display of legally reviewed document translations.

The canonical German LegalDocument and all existing acceptance records stay intact.
No machine translations, draft texts or unapproved variants are published.
"""
from .models import LegalDocumentTranslation


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


def resolve_public_legal_text(document, language, *, translations_enabled=False):
    """Return (body, language, notice, fingerprint), never an unapproved body."""
    language = (language or 'de').lower().split('-', 1)[0]
    source_hash = LegalDocumentTranslation.fingerprint(document.content)
    if language == 'de':
        return document.content, 'de', '', source_hash

    if translations_enabled and language in FALLBACK_NOTICES:
        translation = document.translations.filter(
            language=language, status='approved',
        ).first()
        if translation and translation.is_publishable():
            return (
                translation.content, language, '',
                translation.content_sha256,
            )

    # German remains the actual rendered language, even if UI uses another.
    return document.content, 'de', FALLBACK_NOTICES.get(language, FALLBACK_NOTICES['en']), source_hash
