"""Exact early-performance checkbox wording already used by Marketing.

This is an *evidence source*, NOT legal approval of any translation. When a
copy changes, change the ID and subject the new version to legal review.
"""
from apps.legal.models import LegalDocumentTranslation

CLAUSE_ID = 'early-performance-services-2026-v1'
EARLY_PERFORMANCE_STATEMENTS = {
    "de": "Ich verlange ausdrücklich, dass PROMPTFINISHER Pro vor Ablauf der Widerrufsfrist bereitgestellt wird. Mir ist bekannt, dass bei einem Widerruf für bis dahin erbrachte Dienstleistungen Wertersatz anfallen kann.",
    "en": "I expressly request access to PROMPTFINISHER Pro before the withdrawal period ends. I understand that if I withdraw, I may be required to pay a proportionate amount for services provided up to that point.",
    "es": "Solicito expresamente que PROMPTFINISHER Pro se proporcione antes de que finalice el plazo de desistimiento. Entiendo que, si desisto, puede corresponder un pago proporcional por los servicios prestados hasta entonces.",
    "pt": "Solicito expressamente que o PROMPTFINISHER Pro seja disponibilizado antes do fim do prazo de livre resolução. Sei que, se exercer esse direito, poderá ser devido um valor proporcional aos serviços prestados até então.",
    "tr": "PROMPTFINISHER Pro'nun cayma süresi sona ermeden sunulmasını açıkça talep ediyorum. Cayma hakkımı kullanırsam o ana kadar sunulmuş hizmetler için orantılı bedel ödemem gerekebileceğini biliyorum.",
    "ru": "Я прямо прошу предоставить доступ к PROMPTFINISHER Pro до окончания срока отказа от договора. Мне известно, что при отказе может потребоваться пропорциональная оплата уже оказанных услуг.",
    "pl": "Wyraźnie żądam udostępnienia PROMPTFINISHER Pro przed upływem terminu odstąpienia od umowy. Przyjmuję do wiadomości, że w razie odstąpienia może być należna proporcjonalna zapłata za usługi świadczone do tego momentu.",
    "fr": "Je demande expressément l'accès à PROMPTFINISHER Pro avant la fin du délai de rétractation. Je comprends qu'en cas de rétractation, une somme proportionnelle aux services déjà fournis peut être due.",
    "it": "Chiedo espressamente che PROMPTFINISHER Pro venga fornito prima della scadenza del periodo di recesso. Sono consapevole che, in caso di recesso, potrebbe essere dovuto un importo proporzionale per i servizi già erogati.",
    "nl": "Ik verzoek uitdrukkelijk om PROMPTFINISHER Pro vóór afloop van de herroepingstermijn beschikbaar te stellen. Ik begrijp dat bij herroeping een evenredige vergoeding voor reeds geleverde diensten verschuldigd kan zijn."
}


def early_performance_statement(language):
    language = language if language in EARLY_PERFORMANCE_STATEMENTS else 'de'
    text = EARLY_PERFORMANCE_STATEMENTS[language]
    return {
        'statement_id': CLAUSE_ID,
        'language': language,
        'sha256': LegalDocumentTranslation.fingerprint(text),
        'text': text,
    }
