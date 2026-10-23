"""Locale-aware, stateless rendering of the validated Free/Pro task context.

The canonical German composer and its approved contracts remain authoritative
for validation, entitlements, ready-state and versioning. This module creates
a localized *instructional rendering* from the validated selection, not a
machine translation of sensitive user-supplied text. User values are retained
verbatim as quoted source material. No translation API or persistence is used.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

SUPPORTED = frozenset(('de', 'en', 'es', 'pt', 'tr', 'ru', 'pl', 'fr', 'it', 'nl'))

# Every value below is authored in the target language. Keep these messages
# separate from task IDs, validated options, and user-supplied source content.
MESSAGES = {
 'en': {
  'task': 'Task', 'app': 'Microsoft Copilot application', 'input': 'User-provided information (retain the original wording)',
  'primary': 'Requested outcome', 'secondary': 'Additional context', 'fields': 'Provided detail',
  'focus': 'Selected priorities', 'audience': 'Intended audience', 'format': 'Requested output format',
  'requirements': 'Instructions', 'method': 'Method', 'quality': 'Final quality check',
  'intro': 'Complete the task using only information that is actually available. Make the result actionable and fit for its intended audience.',
  'scope': 'Use only the current Microsoft Copilot context and the information explicitly provided here. Do not assume access to messages, files, meetings or business data that are not available.',
  'no_fabrication': 'Do not invent facts, dates, numbers, people, responsibilities, sources, access rights or completed actions. Identify missing information and distinguish evidence from assumptions.',
  'output': 'Deliver a clear, structured and directly usable response in English. Preserve the exact meaning of the source information, names, numbers and dates.',
  'summarize': 'Retain the main points, decisions, actions, deadlines and open questions without omitting relevant evidence.',
  'draft': 'Organize the material into a coherent professional draft. Preserve facts and commitments and avoid unnecessary repetition.',
  'analysis': 'Examine the available evidence, distinguish observations from interpretation, and identify constraints and uncertainties.',
  'compare': 'Use consistent comparison criteria, describe similarities and differences, and explain trade-offs on the basis of evidence.',
  'plan': 'Break the task into ordered actions, identify dependencies and open responsibilities, and define verifiable outcomes.',
  'fallback': 'Carry out the requested task using the selected application and the provided information.'
 },
 'fr': {
  'task': 'Tâche', 'app': 'Application Microsoft Copilot', 'input': 'Informations fournies (conserver la formulation originale)',
  'primary': 'Résultat demandé', 'secondary': 'Contexte complémentaire', 'fields': 'Précision fournie',
  'focus': 'Priorités choisies', 'audience': 'Public cible', 'format': 'Format de résultat demandé',
  'requirements': 'Consignes', 'method': 'Méthode', 'quality': 'Contrôle qualité final',
  'intro': 'Exécutez cette tâche uniquement avec les informations réellement disponibles. Produisez un résultat exploitable et adapté au public cible.',
  'scope': 'Utilisez uniquement le contexte Microsoft Copilot actuel et les informations explicitement fournies. Ne supposez aucun accès non confirmé aux messages, fichiers, réunions ou données internes.',
  'no_fabrication': 'N’inventez ni faits, dates, chiffres, personnes, responsabilités, sources, droits d’accès ni actions effectuées. Signalez les informations manquantes et distinguez faits et hypothèses.',
  'output': 'Rédigez une réponse claire, structurée et directement utilisable en français. Préservez exactement le sens des sources, des noms, des chiffres et des dates.',
  'summarize': 'Conservez les points essentiels, décisions, actions, échéances et questions ouvertes, sans écarter les informations pertinentes.',
  'draft': 'Organisez les informations dans un texte professionnel cohérent. Conservez les faits et engagements, sans répétitions inutiles.',
  'analysis': 'Examinez les éléments disponibles, distinguez les observations des interprétations et signalez les limites et incertitudes.',
  'compare': 'Appliquez des critères identiques, montrez les points communs et les différences et expliquez les compromis sur la base des faits.',
  'plan': 'Décomposez la tâche en étapes ordonnées, précisez les dépendances et responsabilités ouvertes et définissez des résultats vérifiables.',
  'fallback': 'Exécutez la tâche demandée dans l’application sélectionnée à partir des informations fournies.'
 },
 'it': {
  'task': 'Attività', 'app': 'Applicazione Microsoft Copilot', 'input': 'Informazioni fornite (mantenere il testo originale)',
  'primary': 'Risultato richiesto', 'secondary': 'Contesto aggiuntivo', 'fields': 'Dettaglio fornito',
  'focus': 'Priorità selezionate', 'audience': 'Destinatari', 'format': 'Formato richiesto',
  'requirements': 'Istruzioni', 'method': 'Metodo', 'quality': 'Controllo qualità finale',
  'intro': 'Svolgi l’attività utilizzando soltanto le informazioni effettivamente disponibili. Fornisci un risultato pratico e adatto ai destinatari.',
  'scope': 'Utilizza solo il contesto Microsoft Copilot corrente e le informazioni esplicitamente fornite. Non presupporre l’accesso a messaggi, file, riunioni o dati aziendali non disponibili.',
  'no_fabrication': 'Non inventare fatti, date, numeri, persone, responsabilità, fonti, diritti di accesso o azioni eseguite. Evidenzia le informazioni mancanti e distingui fatti e ipotesi.',
  'output': 'Produci una risposta chiara, strutturata e immediatamente utilizzabile in italiano. Preserva il significato delle fonti, dei nomi, dei numeri e delle date.',
  'summarize': 'Conserva i punti essenziali, le decisioni, le attività, le scadenze e le questioni aperte, senza tralasciare gli elementi pertinenti.',
  'draft': 'Organizza il materiale in una bozza professionale coerente. Mantieni fatti e impegni ed evita ripetizioni superflue.',
  'analysis': 'Esamina le prove disponibili, distingui osservazioni e interpretazioni e segnala limiti e incertezze.',
  'compare': 'Usa criteri di confronto coerenti, mostra analogie e differenze e spiega i compromessi sulla base dei fatti.',
  'plan': 'Suddividi l’attività in passaggi ordinati, individua dipendenze e responsabilità aperte e definisci risultati verificabili.',
  'fallback': 'Svolgi l’attività richiesta nell’applicazione selezionata utilizzando le informazioni fornite.'
 },
 'es': {
  'task': 'Tarea', 'app': 'Aplicación de Microsoft Copilot', 'input': 'Información proporcionada (conservar el texto original)',
  'primary': 'Resultado solicitado', 'secondary': 'Contexto adicional', 'fields': 'Dato proporcionado',
  'focus': 'Prioridades seleccionadas', 'audience': 'Destinatarios', 'format': 'Formato solicitado',
  'requirements': 'Instrucciones', 'method': 'Método', 'quality': 'Revisión final de calidad',
  'intro': 'Realiza la tarea utilizando solo información realmente disponible. Ofrece un resultado práctico y adecuado para sus destinatarios.',
  'scope': 'Utiliza únicamente el contexto actual de Microsoft Copilot y la información facilitada expresamente. No supongas acceso a mensajes, archivos, reuniones o datos empresariales no disponibles.',
  'no_fabrication': 'No inventes hechos, fechas, cifras, personas, responsabilidades, fuentes, permisos de acceso ni acciones realizadas. Señala los datos faltantes y distingue hechos de suposiciones.',
  'output': 'Entrega una respuesta clara, estructurada y directamente utilizable en español. Conserva el significado exacto de los datos, nombres, cifras y fechas.',
  'summarize': 'Conserva los puntos clave, decisiones, acciones, plazos y asuntos pendientes sin omitir información relevante.',
  'draft': 'Organiza la información en un borrador profesional coherente. Respeta hechos y compromisos y evita repeticiones innecesarias.',
  'analysis': 'Examina las pruebas disponibles, distingue observaciones de interpretaciones y señala limitaciones e incertidumbres.',
  'compare': 'Usa criterios de comparación consistentes, muestra semejanzas y diferencias y explica las compensaciones con base en los hechos.',
  'plan': 'Divide la tarea en pasos ordenados, identifica dependencias y responsabilidades pendientes y define resultados verificables.',
  'fallback': 'Realiza la tarea solicitada en la aplicación seleccionada usando la información proporcionada.'
 },
 'pt': {
  'task': 'Tarefa', 'app': 'Aplicação Microsoft Copilot', 'input': 'Informações fornecidas (preservar a redação original)',
  'primary': 'Resultado pretendido', 'secondary': 'Contexto adicional', 'fields': 'Informação fornecida',
  'focus': 'Prioridades selecionadas', 'audience': 'Público-alvo', 'format': 'Formato pretendido',
  'requirements': 'Instruções', 'method': 'Método', 'quality': 'Verificação final de qualidade',
  'intro': 'Execute a tarefa utilizando apenas informações efetivamente disponíveis. Produza um resultado útil e adequado ao público-alvo.',
  'scope': 'Utilize apenas o contexto atual do Microsoft Copilot e as informações expressamente fornecidas. Não pressuponha acesso a mensagens, ficheiros, reuniões ou dados empresariais indisponíveis.',
  'no_fabrication': 'Não invente factos, datas, números, pessoas, responsabilidades, fontes, permissões de acesso ou ações realizadas. Identifique as informações em falta e distinga factos de hipóteses.',
  'output': 'Forneça uma resposta clara, estruturada e diretamente utilizável em português. Preserve o significado exato das fontes, nomes, números e datas.',
  'summarize': 'Preserve os pontos principais, decisões, ações, prazos e questões pendentes sem omitir informações relevantes.',
  'draft': 'Organize o material num texto profissional coerente. Preserve factos e compromissos e evite repetições desnecessárias.',
  'analysis': 'Analise as evidências disponíveis, distinga observações de interpretações e identifique limitações e incertezas.',
  'compare': 'Aplique critérios consistentes, apresente semelhanças e diferenças e explique os compromissos com base nos factos.',
  'plan': 'Divida a tarefa em etapas ordenadas, identifique dependências e responsabilidades pendentes e defina resultados verificáveis.',
  'fallback': 'Execute a tarefa solicitada na aplicação selecionada com base nas informações fornecidas.'
 },
 'nl': {
  'task': 'Taak', 'app': 'Microsoft Copilot-toepassing', 'input': 'Aangeleverde informatie (oorspronkelijke formulering behouden)',
  'primary': 'Gewenst resultaat', 'secondary': 'Aanvullende context', 'fields': 'Aangeleverd detail',
  'focus': 'Gekozen aandachtspunten', 'audience': 'Doelgroep', 'format': 'Gevraagd uitvoerformaat',
  'requirements': 'Instructies', 'method': 'Werkwijze', 'quality': 'Laatste kwaliteitscontrole',
  'intro': 'Voer de taak uit met uitsluitend informatie die daadwerkelijk beschikbaar is. Lever een bruikbaar resultaat dat past bij de doelgroep.',
  'scope': 'Gebruik alleen de huidige Microsoft Copilot-context en expliciet aangeleverde informatie. Veronderstel geen toegang tot niet-beschikbare berichten, bestanden, vergaderingen of bedrijfsgegevens.',
  'no_fabrication': 'Verzin geen feiten, datums, getallen, personen, verantwoordelijkheden, bronnen, toegangsrechten of uitgevoerde acties. Benoem ontbrekende informatie en scheid feiten van aannames.',
  'output': 'Geef een helder, gestructureerd en direct bruikbaar antwoord in het Nederlands. Behoud de exacte betekenis van bronnen, namen, getallen en datums.',
  'summarize': 'Behoud de kernpunten, besluiten, acties, deadlines en open vragen zonder relevante informatie weg te laten.',
  'draft': 'Orden de informatie tot een samenhangend professioneel concept. Behoud feiten en toezeggingen en vermijd overbodige herhaling.',
  'analysis': 'Onderzoek het beschikbare bewijs, onderscheid waarneming van interpretatie en benoem beperkingen en onzekerheden.',
  'compare': 'Hanteer dezelfde vergelijkingscriteria, toon overeenkomsten en verschillen en licht afwegingen toe op basis van feiten.',
  'plan': 'Deel de taak op in geordende stappen, benoem afhankelijkheden en open verantwoordelijkheden en definieer toetsbare resultaten.',
  'fallback': 'Voer de gevraagde taak uit in de geselecteerde toepassing op basis van de aangeleverde informatie.'
 },
 'pl': {
  'task': 'Zadanie', 'app': 'Aplikacja Microsoft Copilot', 'input': 'Dane przekazane przez użytkownika (zachowaj oryginalne brzmienie)',
  'primary': 'Oczekiwany rezultat', 'secondary': 'Dodatkowy kontekst', 'fields': 'Przekazana informacja',
  'focus': 'Wybrane priorytety', 'audience': 'Odbiorcy', 'format': 'Oczekiwany format',
  'requirements': 'Instrukcje', 'method': 'Metoda', 'quality': 'Końcowa kontrola jakości',
  'intro': 'Wykonaj zadanie wyłącznie na podstawie rzeczywiście dostępnych informacji. Przygotuj praktyczny wynik dostosowany do odbiorców.',
  'scope': 'Korzystaj tylko z bieżącego kontekstu Microsoft Copilot oraz informacji wyraźnie przekazanych. Nie zakładaj dostępu do niedostępnych wiadomości, plików, spotkań ani danych firmy.',
  'no_fabrication': 'Nie wymyślaj faktów, dat, liczb, osób, obowiązków, źródeł, praw dostępu ani wykonanych działań. Wskaż brakujące dane i oddziel fakty od założeń.',
  'output': 'Przygotuj jasną, uporządkowaną i gotową do wykorzystania odpowiedź w języku polskim. Zachowaj dokładne znaczenie źródeł, nazw, liczb i dat.',
  'summarize': 'Zachowaj najważniejsze informacje, decyzje, działania, terminy i otwarte pytania, nie pomijając istotnych dowodów.',
  'draft': 'Uporządkuj informacje w spójny profesjonalny tekst. Zachowaj fakty i zobowiązania, unikaj zbędnych powtórzeń.',
  'analysis': 'Przeanalizuj dostępne dowody, oddziel obserwacje od interpretacji i wskaż ograniczenia oraz niepewności.',
  'compare': 'Stosuj jednakowe kryteria porównania, przedstaw podobieństwa i różnice oraz uzasadnij kompromisy na podstawie faktów.',
  'plan': 'Podziel zadanie na uporządkowane etapy, wskaż zależności i nieustalone odpowiedzialności oraz określ sprawdzalne rezultaty.',
  'fallback': 'Wykonaj wskazane zadanie w wybranej aplikacji, korzystając z przekazanych informacji.'
 },
 'tr': {
  'task': 'Görev', 'app': 'Microsoft Copilot uygulaması', 'input': 'Kullanıcının sağladığı bilgiler (özgün ifadeleri koruyun)',
  'primary': 'İstenen sonuç', 'secondary': 'Ek bağlam', 'fields': 'Sağlanan ayrıntı',
  'focus': 'Seçilen öncelikler', 'audience': 'Hedef kitle', 'format': 'İstenen çıktı biçimi',
  'requirements': 'Talimatlar', 'method': 'Yöntem', 'quality': 'Son kalite kontrolü',
  'intro': 'Görevi yalnızca gerçekten erişilebilir bilgilerle yerine getirin. Hedef kitleye uygun, doğrudan kullanılabilir bir sonuç hazırlayın.',
  'scope': 'Yalnızca mevcut Microsoft Copilot bağlamını ve açıkça sağlanan bilgileri kullanın. Erişilemeyen iletilere, dosyalara, toplantılara veya şirket verilerine erişiminiz olduğunu varsaymayın.',
  'no_fabrication': 'Olgular, tarihler, sayılar, kişiler, sorumluluklar, kaynaklar, erişim hakları veya tamamlanmış işlemler uydurmayın. Eksik bilgileri belirtin ve olguları varsayımlardan ayırın.',
  'output': 'Türkçe, açık, düzenli ve doğrudan kullanılabilir bir yanıt üretin. Kaynakların, adların, sayıların ve tarihlerin anlamını aynen koruyun.',
  'summarize': 'Önemli noktaları, kararları, eylemleri, son tarihleri ve açık soruları ilgili kanıtları atlamadan koruyun.',
  'draft': 'Bilgileri tutarlı ve profesyonel bir taslakta düzenleyin. Olguları ve taahhütleri koruyup gereksiz tekrarlardan kaçının.',
  'analysis': 'Mevcut kanıtları inceleyin, gözlemleri yorumlardan ayırın ve sınırlılıklarla belirsizlikleri belirtin.',
  'compare': 'Tutarlı karşılaştırma ölçütleri kullanın, benzerlik ve farklılıkları gösterin ve tercihleri kanıtlara dayanarak açıklayın.',
  'plan': 'Görevi sıralı adımlara ayırın, bağımlılıkları ve belirlenmemiş sorumlulukları gösterin, doğrulanabilir sonuçlar tanımlayın.',
  'fallback': 'Seçilen uygulamada verilen bilgileri kullanarak istenen görevi yerine getirin.'
 },
 'ru': {
  'task': 'Задача', 'app': 'Приложение Microsoft Copilot', 'input': 'Предоставленные сведения (сохранить исходную формулировку)',
  'primary': 'Желаемый результат', 'secondary': 'Дополнительный контекст', 'fields': 'Предоставленная деталь',
  'focus': 'Выбранные приоритеты', 'audience': 'Целевая аудитория', 'format': 'Требуемый формат',
  'requirements': 'Инструкции', 'method': 'Метод', 'quality': 'Итоговая проверка качества',
  'intro': 'Выполните задачу, используя только действительно доступную информацию. Подготовьте практически применимый результат для целевой аудитории.',
  'scope': 'Используйте только текущий контекст Microsoft Copilot и явно предоставленные сведения. Не предполагайте доступ к недоступным сообщениям, файлам, встречам или корпоративным данным.',
  'no_fabrication': 'Не придумывайте факты, даты, числа, людей, обязанности, источники, права доступа или выполненные действия. Укажите, чего не хватает, и отделяйте факты от предположений.',
  'output': 'Подготовьте понятный, структурированный и пригодный к использованию ответ на русском языке. Точно сохраняйте смысл источников, имена, числа и даты.',
  'summarize': 'Сохраните ключевые мысли, решения, действия, сроки и открытые вопросы, не опуская существенные сведения.',
  'draft': 'Организуйте материал в связный профессиональный текст. Сохраняйте факты и обязательства, избегая лишних повторов.',
  'analysis': 'Изучите имеющиеся доказательства, отличайте наблюдения от интерпретаций и укажите ограничения и неопределённость.',
  'compare': 'Используйте одинаковые критерии, покажите сходства и различия и объясните компромиссы на основе фактов.',
  'plan': 'Разбейте задачу на упорядоченные шаги, определите зависимости и открытые обязанности и задайте проверяемые результаты.',
  'fallback': 'Выполните поставленную задачу в выбранном приложении на основе предоставленных сведений.'
 }
}

def select_prompt_language(request, body: dict) -> str:
    """Explicit request locale, then the language-picker cookie. Fail closed."""
    value = body.get('language') or request.COOKIES.get('promptfinisher_language') or 'de'
    code = str(value).strip().lower().split('-', 1)[0][:12]
    if code not in SUPPORTED:
        raise ValueError('Unsupported prompt language.')
    return code


@lru_cache(maxsize=1)
def _product_dictionary() -> dict:
    """Read only the exact JSON literals shipped with the reviewed product UI."""
    source = (Path(__file__).resolve().parents[2]
              / 'static/js/promptfinisher_product_i18n.20261011.js').read_text(encoding='utf-8')
    match = re.search(r'^\s*const TEXT=(\{[^\n]+\});$', source, flags=re.M)
    if not match:
        raise RuntimeError('Product translation catalog missing')
    translations = json.loads(match.group(1))
    for match in re.finditer(r'^\s*Object\.assign\(TEXT,(\{[^\n]+\})\);, source, flags=re.M):
        translations.update(json.loads(match.group(1)))
    return translations


def _translated(source: str, language: str) -> str:
    """No German fallback for generated foreign-language instructions."""
    if not source:
        return ''
    candidate = _product_dictionary().get(source, {}).get(language)
    return str(candidate).strip() if candidate else ''


def render_localized_prompt(
    *, language: str, result: dict, product: str, task_title: str,
    application: str, family: str, selections: dict, maximum_chars: int | None = None,
) -> dict:
    """Return result with translated instructions, preserving canonical metadata.

    Locale-specific text is composed, not translated from arbitrary user data.
    Missing task-title translations never result in a German instruction.
    """
    if language == 'de':
        return result
    copy = MESSAGES[language]
    title = _translated(task_title, language) or copy['fallback']
    pieces = [
        f"{copy['task']}: {title}",
        f"{copy['app']}: {application}",
        f"{copy['requirements']}: {copy['intro']} {copy['output']}",
    ]
    supplied = []
    raw_fields = selections.get('fields') or {}
    if product == 'FREE':
        raw_fields = {'primary': selections.get('primary'), 'secondary': selections.get('secondary')}
    if isinstance(raw_fields, dict):
        for index, (key, value) in enumerate(raw_fields.items(), 1):
            literal = str(value or '').strip()
            if not literal:
                continue
            role = copy['primary'] if key == 'primary' else copy['secondary'] if key == 'secondary' else f"{copy['fields']} {index}"
            supplied.append(f"{role}: «{literal}»")
    if supplied:
        pieces.append(copy['input'] + ':\n' + '\n'.join(supplied))
    if not maximum_chars:
        focus = selections.get('focus') or []
        if isinstance(focus, list):
            translated = [_translated(str(x), language) for x in focus]
            if translated and all(translated):
                pieces.append(f"{copy['focus']}: " + ', '.join(translated))
        audience = _translated(str(selections.get('audience') or ''), language)
        if audience:
            pieces.append(f"{copy['audience']}: {audience}")
        output = _translated(str(selections.get('output') or ''), language)
        if output:
            pieces.append(f"{copy['format']}: {output}")
        pieces.extend([
            f"{copy['method']}: {copy.get(family, copy['analysis'])}",
            copy['scope'],
            f"{copy['quality']}: {copy['no_fabrication']}",
        ])
    prompt = '\n\n'.join(pieces)
    if maximum_chars and len(prompt) > maximum_chars:
        # Compact-tasks carry stringent output budgets; do not silently
        # truncate user data in a way that would change the task.
        prompt = f"{copy['task']}: {title}"[:maximum_chars]
    return {**result, 'prompt': prompt, 'language': language,
            'localization_mode': 'structured', 'source_values_preserved': True}
, source, flags=re.M):
        translations.update(json.loads(match.group(1)))
    return translations


def _translated(source: str, language: str) -> str:
    """No German fallback for generated foreign-language instructions."""
    if not source:
        return ''
    candidate = _product_dictionary().get(source, {}).get(language)
    return str(candidate).strip() if candidate else ''


def render_localized_prompt(
    *, language: str, result: dict, product: str, task_title: str,
    application: str, family: str, selections: dict, maximum_chars: int | None = None,
) -> dict:
    """Return result with translated instructions, preserving canonical metadata.

    Locale-specific text is composed, not translated from arbitrary user data.
    Missing task-title translations never result in a German instruction.
    """
    if language == 'de':
        return result
    copy = MESSAGES[language]
    title = _translated(task_title, language) or copy['fallback']
    pieces = [
        f"{copy['task']}: {title}",
        f"{copy['app']}: {application}",
        f"{copy['requirements']}: {copy['intro']} {copy['output']}",
    ]
    supplied = []
    raw_fields = selections.get('fields') or {}
    if product == 'FREE':
        raw_fields = {'primary': selections.get('primary'), 'secondary': selections.get('secondary')}
    if isinstance(raw_fields, dict):
        for index, (key, value) in enumerate(raw_fields.items(), 1):
            literal = str(value or '').strip()
            if not literal:
                continue
            role = copy['primary'] if key == 'primary' else copy['secondary'] if key == 'secondary' else f"{copy['fields']} {index}"
            supplied.append(f"{role}: «{literal}»")
    if supplied:
        pieces.append(copy['input'] + ':\n' + '\n'.join(supplied))
    if not maximum_chars:
        focus = selections.get('focus') or []
        if isinstance(focus, list):
            translated = [_translated(str(x), language) for x in focus]
            if translated and all(translated):
                pieces.append(f"{copy['focus']}: " + ', '.join(translated))
        audience = _translated(str(selections.get('audience') or ''), language)
        if audience:
            pieces.append(f"{copy['audience']}: {audience}")
        output = _translated(str(selections.get('output') or ''), language)
        if output:
            pieces.append(f"{copy['format']}: {output}")
        pieces.extend([
            f"{copy['method']}: {copy.get(family, copy['analysis'])}",
            copy['scope'],
            f"{copy['quality']}: {copy['no_fabrication']}",
        ])
    prompt = '\n\n'.join(pieces)
    if maximum_chars and len(prompt) > maximum_chars:
        # Compact-tasks carry stringent output budgets; do not silently
        # truncate user data in a way that would change the task.
        prompt = f"{copy['task']}: {title}"[:maximum_chars]
    return {**result, 'prompt': prompt, 'language': language,
            'localization_mode': 'structured', 'source_values_preserved': True}
