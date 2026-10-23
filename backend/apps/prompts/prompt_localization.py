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

# Reviewed task labels for the 16 unchanged Free legacy contracts.
FREE_TASK_TITLES = {
 "chat_sum": {
  "en": "Summarize content",
  "fr": "Résumer le contenu",
  "it": "Riassumere il contenuto",
  "es": "Resumir contenido",
  "pt": "Resumir conteúdo",
  "nl": "Inhoud samenvatten",
  "pl": "Podsumować treść",
  "tr": "İçeriği özetle",
  "ru": "Суммировать содержание"
 },
 "chat_write": {
  "en": "Draft a text",
  "fr": "Rédiger un texte",
  "it": "Redigere un testo",
  "es": "Redactar un texto",
  "pt": "Redigir um texto",
  "nl": "Tekst opstellen",
  "pl": "Przygotować tekst",
  "tr": "Metin hazırla",
  "ru": "Составить текст"
 },
 "out_reply": {
  "en": "Prepare an email reply",
  "fr": "Préparer une réponse par e-mail",
  "it": "Preparare una risposta e-mail",
  "es": "Preparar respuesta de correo",
  "pt": "Preparar resposta por e-mail",
  "nl": "E-mailantwoord opstellen",
  "pl": "Przygotować odpowiedź e-mail",
  "tr": "E-posta yanıtı hazırla",
  "ru": "Подготовить ответ на письмо"
 },
 "out_improve": {
  "en": "Improve an email",
  "fr": "Améliorer un e-mail",
  "it": "Migliorare un'e-mail",
  "es": "Mejorar correo electrónico",
  "pt": "Melhorar e-mail",
  "nl": "E-mail verbeteren",
  "pl": "Ulepszyć e-mail",
  "tr": "E-postayı iyileştir",
  "ru": "Улучшить письмо"
 },
 "out_cal_next": {
  "en": "Find the next appointment",
  "fr": "Trouver le prochain rendez-vous",
  "it": "Individuare il prossimo appuntamento",
  "es": "Buscar la próxima cita",
  "pt": "Encontrar o próximo compromisso",
  "nl": "Volgende afspraak vinden",
  "pl": "Znaleźć następne spotkanie",
  "tr": "Sonraki randevuyu bul",
  "ru": "Найти ближайшую встречу"
 },
 "out_cal_schedule": {
  "en": "Plan an appointment",
  "fr": "Planifier un rendez-vous",
  "it": "Pianificare un appuntamento",
  "es": "Planificar una cita",
  "pt": "Planear um compromisso",
  "nl": "Afspraak plannen",
  "pl": "Zaplanować spotkanie",
  "tr": "Randevu planla",
  "ru": "Запланировать встречу"
 },
 "out_todo_create": {
  "en": "Create a task list",
  "fr": "Créer une liste de tâches",
  "it": "Creare un elenco di attività",
  "es": "Crear lista de tareas",
  "pt": "Criar lista de tarefas",
  "nl": "Takenlijst maken",
  "pl": "Utworzyć listę zadań",
  "tr": "Görev listesi oluştur",
  "ru": "Создать список задач"
 },
 "out_todo_prioritize": {
  "en": "Prioritize tasks",
  "fr": "Hiérarchiser les tâches",
  "it": "Dare priorità alle attività",
  "es": "Priorizar tareas",
  "pt": "Priorizar tarefas",
  "nl": "Taken prioriteren",
  "pl": "Ustalić priorytety zadań",
  "tr": "Görevleri önceliklendir",
  "ru": "Расставить приоритеты задач"
 },
 "teams_notes": {
  "en": "Prepare a meeting follow-up",
  "fr": "Préparer le compte rendu de réunion",
  "it": "Preparare un resoconto della riunione",
  "es": "Preparar seguimiento de reunión",
  "pt": "Preparar o seguimento da reunião",
  "nl": "Vergaderopvolging opstellen",
  "pl": "Przygotować podsumowanie spotkania",
  "tr": "Toplantı sonrası özeti hazırla",
  "ru": "Подготовить итоги встречи"
 },
 "teams_chat": {
  "en": "Summarize a chat",
  "fr": "Résumer une conversation",
  "it": "Riassumere una chat",
  "es": "Resumir un chat",
  "pt": "Resumir uma conversa",
  "nl": "Chat samenvatten",
  "pl": "Podsumować rozmowę",
  "tr": "Sohbeti özetle",
  "ru": "Суммировать чат"
 },
 "word_rewrite": {
  "en": "Improve a text",
  "fr": "Améliorer un texte",
  "it": "Migliorare un testo",
  "es": "Mejorar un texto",
  "pt": "Melhorar um texto",
  "nl": "Tekst verbeteren",
  "pl": "Ulepszyć tekst",
  "tr": "Metni iyileştir",
  "ru": "Улучшить текст"
 },
 "word_sum": {
  "en": "Summarize a document",
  "fr": "Résumer un document",
  "it": "Riassumere un documento",
  "es": "Resumir documento",
  "pt": "Resumir documento",
  "nl": "Document samenvatten",
  "pl": "Podsumować dokument",
  "tr": "Belgeyi özetle",
  "ru": "Суммировать документ"
 },
 "excel_explain": {
  "en": "Explain data",
  "fr": "Expliquer les données",
  "it": "Spiegare i dati",
  "es": "Explicar datos",
  "pt": "Explicar dados",
  "nl": "Gegevens uitleggen",
  "pl": "Wyjaśnić dane",
  "tr": "Verileri açıkla",
  "ru": "Объяснить данные"
 },
 "excel_compare": {
  "en": "Compare values",
  "fr": "Comparer des valeurs",
  "it": "Confrontare valori",
  "es": "Comparar valores",
  "pt": "Comparar valores",
  "nl": "Waarden vergelijken",
  "pl": "Porównać wartości",
  "tr": "Değerleri karşılaştır",
  "ru": "Сравнить значения"
 },
 "ppt_outline": {
  "en": "Prepare slide content",
  "fr": "Préparer le contenu des diapositives",
  "it": "Preparare il contenuto delle diapositive",
  "es": "Preparar contenido de diapositivas",
  "pt": "Preparar conteúdo de diapositivos",
  "nl": "Dia-inhoud voorbereiden",
  "pl": "Przygotować treść slajdów",
  "tr": "Slayt içeriğini hazırla",
  "ru": "Подготовить содержимое слайдов"
 },
 "ppt_rewrite": {
  "en": "Improve slide text",
  "fr": "Améliorer le texte des diapositives",
  "it": "Migliorare il testo delle diapositive",
  "es": "Mejorar texto de diapositivas",
  "pt": "Melhorar texto dos diapositivos",
  "nl": "Diatekst verbeteren",
  "pl": "Ulepszyć tekst slajdów",
  "tr": "Slayt metnini iyileştir",
  "ru": "Улучшить текст слайдов"
 }
}


# Selection values are stable API codes; their display text is translated here.
CHOICE_LABELS = {
 "Kernaussagen": {
  "en": "Key points",
  "fr": "Points essentiels",
  "it": "Punti chiave",
  "es": "Puntos clave",
  "pt": "Pontos principais",
  "nl": "Kernpunten",
  "pl": "Najważniejsze informacje",
  "tr": "Ana noktalar",
  "ru": "Ключевые положения"
 },
 "Entscheidungen": {
  "en": "Decisions",
  "fr": "Décisions",
  "it": "Decisioni",
  "es": "Decisiones",
  "pt": "Decisões",
  "nl": "Besluiten",
  "pl": "Decyzje",
  "tr": "Kararlar",
  "ru": "Решения"
 },
 "Aufgaben": {
  "en": "Tasks",
  "fr": "Tâches",
  "it": "Attività",
  "es": "Tareas",
  "pt": "Tarefas",
  "nl": "Taken",
  "pl": "Zadania",
  "tr": "Görevler",
  "ru": "Задачи"
 },
 "Nächste Schritte": {
  "en": "Next steps",
  "fr": "Prochaines étapes",
  "it": "Passaggi successivi",
  "es": "Próximos pasos",
  "pt": "Próximos passos",
  "nl": "Volgende stappen",
  "pl": "Kolejne kroki",
  "tr": "Sonraki adımlar",
  "ru": "Следующие шаги"
 },
 "Offene Fragen": {
  "en": "Open questions",
  "fr": "Questions ouvertes",
  "it": "Questioni aperte",
  "es": "Preguntas abiertas",
  "pt": "Questões em aberto",
  "nl": "Open vragen",
  "pl": "Otwarte pytania",
  "tr": "Açık sorular",
  "ru": "Открытые вопросы"
 },
 "Termine": {
  "en": "Deadlines",
  "fr": "Échéances",
  "it": "Scadenze",
  "es": "Plazos",
  "pt": "Prazos",
  "nl": "Termijnen",
  "pl": "Terminy",
  "tr": "Son tarihler",
  "ru": "Сроки"
 },
 "Risiken": {
  "en": "Risks",
  "fr": "Risques",
  "it": "Rischi",
  "es": "Riesgos",
  "pt": "Riscos",
  "nl": "Risico's",
  "pl": "Ryzyka",
  "tr": "Riskler",
  "ru": "Риски"
 },
 "Dringlichkeit": {
  "en": "Urgency",
  "fr": "Urgence",
  "it": "Urgenza",
  "es": "Urgencia",
  "pt": "Urgência",
  "nl": "Urgentie",
  "pl": "Pilność",
  "tr": "Aciliyet",
  "ru": "Срочность"
 },
 "Auswirkung": {
  "en": "Impact",
  "fr": "Impact",
  "it": "Impatto",
  "es": "Impacto",
  "pt": "Impacto",
  "nl": "Impact",
  "pl": "Wpływ",
  "tr": "Etki",
  "ru": "Влияние"
 },
 "Fälligkeit": {
  "en": "Due date",
  "fr": "Date d'échéance",
  "it": "Scadenza",
  "es": "Fecha límite",
  "pt": "Prazo",
  "nl": "Vervaldatum",
  "pl": "Termin wykonania",
  "tr": "Son tarih",
  "ru": "Срок исполнения"
 },
 "Abhängigkeiten": {
  "en": "Dependencies",
  "fr": "Dépendances",
  "it": "Dipendenze",
  "es": "Dependencias",
  "pt": "Dependências",
  "nl": "Afhankelijkheden",
  "pl": "Zależności",
  "tr": "Bağımlılıklar",
  "ru": "Зависимости"
 },
 "Priorität": {
  "en": "Priority",
  "fr": "Priorité",
  "it": "Priorità",
  "es": "Prioridad",
  "pt": "Prioridade",
  "nl": "Prioriteit",
  "pl": "Priorytet",
  "tr": "Öncelik",
  "ru": "Приоритет"
 },
 "Kernaussage": {
  "en": "Core message",
  "fr": "Message essentiel",
  "it": "Messaggio chiave",
  "es": "Mensaje central",
  "pt": "Mensagem principal",
  "nl": "Kernboodschap",
  "pl": "Główny przekaz",
  "tr": "Ana mesaj",
  "ru": "Главная мысль"
 },
 "Klarheit": {
  "en": "Clarity",
  "fr": "Clarté",
  "it": "Chiarezza",
  "es": "Claridad",
  "pt": "Clareza",
  "nl": "Helderheid",
  "pl": "Jasność",
  "tr": "Açıklık",
  "ru": "Ясность"
 },
 "Struktur": {
  "en": "Structure",
  "fr": "Structure",
  "it": "Struttura",
  "es": "Estructura",
  "pt": "Estrutura",
  "nl": "Structuur",
  "pl": "Struktura",
  "tr": "Yapı",
  "ru": "Структура"
 },
 "bullets": {
  "en": "Bullet points",
  "fr": "Liste à puces",
  "it": "Elenco puntato",
  "es": "Viñetas",
  "pt": "Lista com marcadores",
  "nl": "Opsommingstekens",
  "pl": "Punkty",
  "tr": "Madde işaretleri",
  "ru": "Маркированный список"
 },
 "meeting_notes": {
  "en": "Meeting follow-up",
  "fr": "Compte rendu de réunion",
  "it": "Resoconto della riunione",
  "es": "Resumen de reunión",
  "pt": "Resumo da reunião",
  "nl": "Vergaderverslag",
  "pl": "Podsumowanie spotkania",
  "tr": "Toplantı özeti",
  "ru": "Итоги встречи"
 },
 "prose": {
  "en": "Continuous text",
  "fr": "Texte suivi",
  "it": "Testo continuo",
  "es": "Texto corrido",
  "pt": "Texto corrido",
  "nl": "Doorlopende tekst",
  "pl": "Tekst ciągły",
  "tr": "Düz metin",
  "ru": "Связный текст"
 },
 "email": {
  "en": "Email draft",
  "fr": "Brouillon d'e-mail",
  "it": "Bozza e-mail",
  "es": "Borrador de correo",
  "pt": "Rascunho de e-mail",
  "nl": "E-mailconcept",
  "pl": "Szkic e-maila",
  "tr": "E-posta taslağı",
  "ru": "Черновик письма"
 },
 "checklist": {
  "en": "Checklist",
  "fr": "Liste de vérification",
  "it": "Lista di controllo",
  "es": "Lista de verificación",
  "pt": "Lista de verificação",
  "nl": "Checklist",
  "pl": "Lista kontrolna",
  "tr": "Kontrol listesi",
  "ru": "Контрольный список"
 },
 "priority": {
  "en": "Prioritized list",
  "fr": "Liste hiérarchisée",
  "it": "Elenco per priorità",
  "es": "Lista priorizada",
  "pt": "Lista por prioridades",
  "nl": "Lijst met prioriteiten",
  "pl": "Lista priorytetowa",
  "tr": "Öncelik listesi",
  "ru": "Список приоритетов"
 },
 "summary": {
  "en": "Short summary",
  "fr": "Résumé succinct",
  "it": "Riepilogo breve",
  "es": "Resumen breve",
  "pt": "Resumo curto",
  "nl": "Korte samenvatting",
  "pl": "Krótkie podsumowanie",
  "tr": "Kısa özet",
  "ru": "Краткое резюме"
 },
 "schedule": {
  "en": "Appointment proposal",
  "fr": "Proposition de rendez-vous",
  "it": "Proposta di appuntamento",
  "es": "Propuesta de cita",
  "pt": "Proposta de compromisso",
  "nl": "Afspraakvoorstel",
  "pl": "Propozycja spotkania",
  "tr": "Randevu önerisi",
  "ru": "Предложение встречи"
 },
 "slide_outline": {
  "en": "Slide outline",
  "fr": "Plan des diapositives",
  "it": "Scaletta delle diapositive",
  "es": "Esquema de diapositivas",
  "pt": "Esboço de diapositivos",
  "nl": "Diaoverzicht",
  "pl": "Konspekt slajdów",
  "tr": "Slayt taslağı",
  "ru": "План слайдов"
 },
 "slide_text": {
  "en": "Slide text",
  "fr": "Texte de diapositive",
  "it": "Testo delle diapositive",
  "es": "Texto de diapositivas",
  "pt": "Texto dos diapositivos",
  "nl": "Diatekst",
  "pl": "Tekst slajdów",
  "tr": "Slayt metni",
  "ru": "Текст слайдов"
 },
 "self": {
  "en": "Me as the user",
  "fr": "Moi, l'utilisateur",
  "it": "Me come utente",
  "es": "Yo como usuario",
  "pt": "Eu como utilizador",
  "nl": "Mij als gebruiker",
  "pl": "Ja jako użytkownik",
  "tr": "Kullanıcı olarak ben",
  "ru": "Я как пользователь"
 },
 "customer": {
  "en": "External customer",
  "fr": "Client externe",
  "it": "Cliente esterno",
  "es": "Cliente externo",
  "pt": "Cliente externo",
  "nl": "Externe klant",
  "pl": "Klient zewnętrzny",
  "tr": "Harici müşteri",
  "ru": "Внешний клиент"
 },
 "internal": {
  "en": "Internal colleagues",
  "fr": "Collègues internes",
  "it": "Colleghi interni",
  "es": "Compañeros internos",
  "pt": "Colegas internos",
  "nl": "Interne collega's",
  "pl": "Współpracownicy",
  "tr": "İç ekip arkadaşları",
  "ru": "Внутренние коллеги"
 },
 "team": {
  "en": "Internal team",
  "fr": "Équipe interne",
  "it": "Team interno",
  "es": "Equipo interno",
  "pt": "Equipa interna",
  "nl": "Intern team",
  "pl": "Zespół wewnętrzny",
  "tr": "İç ekip",
  "ru": "Внутренняя команда"
 },
 "participants": {
  "en": "Meeting participants",
  "fr": "Participants à la réunion",
  "it": "Partecipanti alla riunione",
  "es": "Participantes de la reunión",
  "pt": "Participantes na reunião",
  "nl": "Deelnemers aan vergadering",
  "pl": "Uczestnicy spotkania",
  "tr": "Toplantı katılımcıları",
  "ru": "Участники встречи"
 },
 "own_tasks": {
  "en": "Personal task planning",
  "fr": "Planification personnelle",
  "it": "Pianificazione personale",
  "es": "Planificación personal",
  "pt": "Planeamento pessoal",
  "nl": "Persoonlijke taakplanning",
  "pl": "Własny plan zadań",
  "tr": "Kişisel görev planlama",
  "ru": "Планирование собственных задач"
 },
 "Abweichungen": {
  "en": "Deviations",
  "fr": "Écarts",
  "it": "Scostamenti",
  "es": "Desviaciones",
  "pt": "Desvios",
  "nl": "Afwijkingen",
  "pl": "Odchylenia",
  "tr": "Sapmalar",
  "ru": "Отклонения"
 },
 "Agenda": {
  "en": "Agenda",
  "fr": "Ordre du jour",
  "it": "Ordine del giorno",
  "es": "Orden del día",
  "pt": "Ordem do dia",
  "nl": "Agenda",
  "pl": "Porządek obrad",
  "tr": "Gündem",
  "ru": "Повестка дня"
 },
 "Aktualität": {
  "en": "Recency",
  "fr": "Actualité",
  "it": "Attualità",
  "es": "Actualidad",
  "pt": "Atualidade",
  "nl": "Actualiteit",
  "pl": "Aktualność",
  "tr": "Güncellik",
  "ru": "Актуальность"
 },
 "Anlagen / Unterlagen": {
  "en": "Attachments / documents",
  "fr": "Pièces jointes / documents",
  "it": "Allegati / documenti",
  "es": "Adjuntos / documentos",
  "pt": "Anexos / documentos",
  "nl": "Bijlagen / documenten",
  "pl": "Załączniki / dokumenty",
  "tr": "Ekler / belgeler",
  "ru": "Вложения / документы"
 },
 "Annahmen": {
  "en": "Assumptions",
  "fr": "Hypothèses",
  "it": "Ipotesi",
  "es": "Suposiciones",
  "pt": "Pressupostos",
  "nl": "Aannames",
  "pl": "Założenia",
  "tr": "Varsayımlar",
  "ru": "Предположения"
 },
 "Antwort auf Fragen": {
  "en": "Answers to questions",
  "fr": "Réponses aux questions",
  "it": "Risposte alle domande",
  "es": "Respuestas a preguntas",
  "pt": "Respostas a perguntas",
  "nl": "Antwoorden op vragen",
  "pl": "Odpowiedzi na pytania",
  "tr": "Sorulara yanıtlar",
  "ru": "Ответы на вопросы"
 },
 "Argumente": {
  "en": "Arguments",
  "fr": "Arguments",
  "it": "Argomentazioni",
  "es": "Argumentos",
  "pt": "Argumentos",
  "nl": "Argumenten",
  "pl": "Argumenty",
  "tr": "Argümanlar",
  "ru": "Аргументы"
 },
 "Auffälligkeiten": {
  "en": "Anomalies",
  "fr": "Anomalies",
  "it": "Anomalie",
  "es": "Anomalías",
  "pt": "Anomalias",
  "nl": "Afwijkende bevindingen",
  "pl": "Nieprawidłowości",
  "tr": "Anormallikler",
  "ru": "Аномалии"
 },
 "Bedingungen": {
  "en": "Conditions",
  "fr": "Conditions",
  "it": "Condizioni",
  "es": "Condiciones",
  "pt": "Condições",
  "nl": "Voorwaarden",
  "pl": "Warunki",
  "tr": "Koşullar",
  "ru": "Условия"
 },
 "Belege": {
  "en": "Evidence",
  "fr": "Justificatifs",
  "it": "Prove",
  "es": "Pruebas",
  "pt": "Comprovativos",
  "nl": "Bewijsstukken",
  "pl": "Dowody",
  "tr": "Kanıtlar",
  "ru": "Доказательства"
 },
 "Berechtigungen": {
  "en": "Permissions",
  "fr": "Autorisations",
  "it": "Autorizzazioni",
  "es": "Permisos",
  "pt": "Permissões",
  "nl": "Machtigingen",
  "pl": "Uprawnienia",
  "tr": "İzinler",
  "ru": "Разрешения"
 },
 "Beschlüsse": {
  "en": "Resolutions",
  "fr": "Résolutions",
  "it": "Delibere",
  "es": "Acuerdos adoptados",
  "pt": "Deliberações",
  "nl": "Besluiten",
  "pl": "Uchwały",
  "tr": "Alınan kararlar",
  "ru": "Принятые решения"
 },
 "Bestätigung": {
  "en": "Confirmation",
  "fr": "Confirmation",
  "it": "Conferma",
  "es": "Confirmación",
  "pt": "Confirmação",
  "nl": "Bevestiging",
  "pl": "Potwierdzenie",
  "tr": "Onay",
  "ru": "Подтверждение"
 },
 "Betreff": {
  "en": "Subject",
  "fr": "Objet",
  "it": "Oggetto",
  "es": "Asunto",
  "pt": "Assunto",
  "nl": "Onderwerp",
  "pl": "Temat",
  "tr": "Konu",
  "ru": "Тема"
 },
 "Betroffene Assets": {
  "en": "Affected assets",
  "fr": "Actifs concernés",
  "it": "Risorse interessate",
  "es": "Activos afectados",
  "pt": "Ativos afetados",
  "nl": "Betrokken middelen",
  "pl": "Zasoby objęte problemem",
  "tr": "Etkilenen varlıklar",
  "ru": "Затронутые активы"
 },
 "Blockaden": {
  "en": "Blockers",
  "fr": "Blocages",
  "it": "Impedimenti",
  "es": "Bloqueos",
  "pt": "Bloqueios",
  "nl": "Blokkades",
  "pl": "Przeszkody",
  "tr": "Engeller",
  "ru": "Препятствия"
 },
 "Call-to-Action": {
  "en": "Call to action",
  "fr": "Appel à l'action",
  "it": "Invito all'azione",
  "es": "Llamada a la acción",
  "pt": "Apelo à ação",
  "nl": "Oproep tot actie",
  "pl": "Wezwanie do działania",
  "tr": "Eylem çağrısı",
  "ru": "Призыв к действию"
 },
 "Daten": {
  "en": "Data",
  "fr": "Données",
  "it": "Dati",
  "es": "Datos",
  "pt": "Dados",
  "nl": "Gegevens",
  "pl": "Dane",
  "tr": "Veriler",
  "ru": "Данные"
 },
 "Datenqualität": {
  "en": "Data quality",
  "fr": "Qualité des données",
  "it": "Qualità dei dati",
  "es": "Calidad de datos",
  "pt": "Qualidade dos dados",
  "nl": "Gegevenskwaliteit",
  "pl": "Jakość danych",
  "tr": "Veri kalitesi",
  "ru": "Качество данных"
 },
 "Datum / Uhrzeit": {
  "en": "Date / time",
  "fr": "Date / heure",
  "it": "Data / ora",
  "es": "Fecha / hora",
  "pt": "Data / hora",
  "nl": "Datum / tijd",
  "pl": "Data / godzina",
  "tr": "Tarih / saat",
  "ru": "Дата / время"
 },
 "Dauer": {
  "en": "Duration",
  "fr": "Durée",
  "it": "Durata",
  "es": "Duración",
  "pt": "Duração",
  "nl": "Duur",
  "pl": "Czas trwania",
  "tr": "Süre",
  "ru": "Продолжительность"
 },
 "Differenzen": {
  "en": "Differences",
  "fr": "Différences",
  "it": "Differenze",
  "es": "Diferencias",
  "pt": "Diferenças",
  "nl": "Verschillen",
  "pl": "Różnice",
  "tr": "Farklar",
  "ru": "Различия"
 },
 "Doppelverarbeitung": {
  "en": "Duplicate processing",
  "fr": "Traitement en double",
  "it": "Elaborazione duplicata",
  "es": "Procesamiento duplicado",
  "pt": "Processamento duplicado",
  "nl": "Dubbele verwerking",
  "pl": "Podwójne przetwarzanie",
  "tr": "Mükerrer işleme",
  "ru": "Повторная обработка"
 },
 "Einwände": {
  "en": "Objections",
  "fr": "Objections",
  "it": "Obiezioni",
  "es": "Objeciones",
  "pt": "Objeções",
  "nl": "Bezwaren",
  "pl": "Zastrzeżenia",
  "tr": "İtirazlar",
  "ru": "Возражения"
 },
 "Empfehlung": {
  "en": "Recommendation",
  "fr": "Recommandation",
  "it": "Raccomandazione",
  "es": "Recomendación",
  "pt": "Recomendação",
  "nl": "Aanbeveling",
  "pl": "Rekomendacja",
  "tr": "Öneri",
  "ru": "Рекомендация"
 },
 "Erfolgskriterium": {
  "en": "Success criterion",
  "fr": "Critère de réussite",
  "it": "Criterio di successo",
  "es": "Criterio de éxito",
  "pt": "Critério de sucesso",
  "nl": "Succescriterium",
  "pl": "Kryterium sukcesu",
  "tr": "Başarı ölçütü",
  "ru": "Критерий успеха"
 },
 "Erklärungsbedarf": {
  "en": "Need for explanation",
  "fr": "Besoin d'explication",
  "it": "Necessità di chiarimenti",
  "es": "Necesidad de explicación",
  "pt": "Necessidade de esclarecimento",
  "nl": "Behoefte aan uitleg",
  "pl": "Potrzeba wyjaśnień",
  "tr": "Açıklama ihtiyacı",
  "ru": "Необходимость пояснений"
 },
 "Evidenz": {
  "en": "Evidence",
  "fr": "Éléments probants",
  "it": "Evidenze",
  "es": "Evidencia",
  "pt": "Evidências",
  "nl": "Bewijs",
  "pl": "Dowody",
  "tr": "Kanıt",
  "ru": "Доказательства"
 },
 "Fehlerbehandlung": {
  "en": "Error handling",
  "fr": "Gestion des erreurs",
  "it": "Gestione degli errori",
  "es": "Gestión de errores",
  "pt": "Tratamento de erros",
  "nl": "Foutafhandeling",
  "pl": "Obsługa błędów",
  "tr": "Hata yönetimi",
  "ru": "Обработка ошибок"
 },
 "Fehlerfälle": {
  "en": "Failure cases",
  "fr": "Cas d'erreur",
  "it": "Casi di errore",
  "es": "Casos de error",
  "pt": "Casos de erro",
  "nl": "Foutgevallen",
  "pl": "Przypadki błędów",
  "tr": "Hata durumları",
  "ru": "Ошибочные сценарии"
 },
 "Format": {
  "en": "Format",
  "fr": "Format",
  "it": "Formato",
  "es": "Formato",
  "pt": "Formato",
  "nl": "Formaat",
  "pl": "Format",
  "tr": "Biçim",
  "ru": "Формат"
 },
 "Fristen": {
  "en": "Deadlines",
  "fr": "Délais",
  "it": "Scadenze",
  "es": "Plazos",
  "pt": "Prazos",
  "nl": "Termijnen",
  "pl": "Terminy",
  "tr": "Son tarihler",
  "ru": "Сроки"
 },
 "Governance": {
  "en": "Governance",
  "fr": "Gouvernance",
  "it": "Governance",
  "es": "Gobernanza",
  "pt": "Governação",
  "nl": "Governance",
  "pl": "Ład organizacyjny",
  "tr": "Yönetişim",
  "ru": "Управление"
 },
 "Grenzen": {
  "en": "Limits",
  "fr": "Limites",
  "it": "Limiti",
  "es": "Límites",
  "pt": "Limites",
  "nl": "Grenzen",
  "pl": "Ograniczenia",
  "tr": "Sınırlar",
  "ru": "Ограничения"
 },
 "Handlungsaufforderung": {
  "en": "Call to action",
  "fr": "Appel à l'action",
  "it": "Invito all'azione",
  "es": "Llamada a la acción",
  "pt": "Apelo à ação",
  "nl": "Oproep tot actie",
  "pl": "Wezwanie do działania",
  "tr": "Eylem çağrısı",
  "ru": "Призыв к действию"
 },
 "Handlungsbedarf": {
  "en": "Action required",
  "fr": "Actions nécessaires",
  "it": "Interventi necessari",
  "es": "Acciones necesarias",
  "pt": "Ações necessárias",
  "nl": "Benodigde actie",
  "pl": "Wymagane działania",
  "tr": "Gerekli adımlar",
  "ru": "Необходимые действия"
 },
 "Kennzahlen": {
  "en": "Key figures",
  "fr": "Indicateurs clés",
  "it": "Indicatori chiave",
  "es": "Indicadores clave",
  "pt": "Indicadores-chave",
  "nl": "Kerncijfers",
  "pl": "Wskaźniki",
  "tr": "Temel göstergeler",
  "ru": "Ключевые показатели"
 },
 "Konkrete Aufgabe": {
  "en": "Specific task",
  "fr": "Tâche précise",
  "it": "Attività specifica",
  "es": "Tarea concreta",
  "pt": "Tarefa concreta",
  "nl": "Concrete taak",
  "pl": "Konkretne zadanie",
  "tr": "Somut görev",
  "ru": "Конкретная задача"
 },
 "Korrektheit": {
  "en": "Correctness",
  "fr": "Exactitude",
  "it": "Correttezza",
  "es": "Corrección",
  "pt": "Correção",
  "nl": "Juistheid",
  "pl": "Poprawność",
  "tr": "Doğruluk",
  "ru": "Корректность"
 },
 "Kosten": {
  "en": "Costs",
  "fr": "Coûts",
  "it": "Costi",
  "es": "Costes",
  "pt": "Custos",
  "nl": "Kosten",
  "pl": "Koszty",
  "tr": "Maliyetler",
  "ru": "Затраты"
 },
 "Kosten / Auswirkungen": {
  "en": "Costs / impact",
  "fr": "Coûts / impacts",
  "it": "Costi / impatto",
  "es": "Costes / impacto",
  "pt": "Custos / impacto",
  "nl": "Kosten / gevolgen",
  "pl": "Koszty / wpływ",
  "tr": "Maliyetler / etkiler",
  "ru": "Затраты / влияние"
 },
 "Kriterien": {
  "en": "Criteria",
  "fr": "Critères",
  "it": "Criteri",
  "es": "Criterios",
  "pt": "Critérios",
  "nl": "Criteria",
  "pl": "Kryteria",
  "tr": "Ölçütler",
  "ru": "Критерии"
 },
 "Kundenorientierung": {
  "en": "Customer focus",
  "fr": "Orientation client",
  "it": "Orientamento al cliente",
  "es": "Orientación al cliente",
  "pt": "Foco no cliente",
  "nl": "Klantgerichtheid",
  "pl": "Orientacja na klienta",
  "tr": "Müşteri odaklılık",
  "ru": "Ориентация на клиента"
 },
 "Kürze": {
  "en": "Brevity",
  "fr": "Concision",
  "it": "Concisione",
  "es": "Brevedad",
  "pt": "Concisão",
  "nl": "Beknoptheid",
  "pl": "Zwięzłość",
  "tr": "Kısalık",
  "ru": "Краткость"
 },
 "Lern- / Entwicklungsschritt": {
  "en": "Learning / development step",
  "fr": "Étape d'apprentissage / développement",
  "it": "Fase di apprendimento / sviluppo",
  "es": "Etapa de aprendizaje / desarrollo",
  "pt": "Etapa de aprendizagem / desenvolvimento",
  "nl": "Leer- / ontwikkelstap",
  "pl": "Etap nauki / rozwoju",
  "tr": "Öğrenme / gelişim adımı",
  "ru": "Этап обучения / развития"
 },
 "Meilensteine": {
  "en": "Milestones",
  "fr": "Jalons",
  "it": "Pietre miliari",
  "es": "Hitos",
  "pt": "Marcos",
  "nl": "Mijlpalen",
  "pl": "Kamienie milowe",
  "tr": "Kilometre taşları",
  "ru": "Контрольные точки"
 },
 "Nutzen": {
  "en": "Benefits",
  "fr": "Avantages",
  "it": "Vantaggi",
  "es": "Beneficios",
  "pt": "Benefícios",
  "nl": "Voordelen",
  "pl": "Korzyści",
  "tr": "Faydalar",
  "ru": "Польза"
 },
 "Offene Informationen": {
  "en": "Missing information",
  "fr": "Informations manquantes",
  "it": "Informazioni mancanti",
  "es": "Información pendiente",
  "pt": "Informações em falta",
  "nl": "Ontbrekende informatie",
  "pl": "Brakujące informacje",
  "tr": "Eksik bilgiler",
  "ru": "Недостающие сведения"
 },
 "Offene Punkte": {
  "en": "Open items",
  "fr": "Points en suspens",
  "it": "Punti aperti",
  "es": "Puntos pendientes",
  "pt": "Pontos em aberto",
  "nl": "Openstaande punten",
  "pl": "Otwarte kwestie",
  "tr": "Açık konular",
  "ru": "Открытые вопросы"
 },
 "Ort / Teams": {
  "en": "Location / Teams",
  "fr": "Lieu / Teams",
  "it": "Luogo / Teams",
  "es": "Lugar / Teams",
  "pt": "Local / Teams",
  "nl": "Locatie / Teams",
  "pl": "Miejsce / Teams",
  "tr": "Konum / Teams",
  "ru": "Место / Teams"
 },
 "Ort / Teams-Link": {
  "en": "Location / Teams link",
  "fr": "Lieu / lien Teams",
  "it": "Luogo / collegamento Teams",
  "es": "Lugar / enlace Teams",
  "pt": "Local / ligação Teams",
  "nl": "Locatie / Teams-link",
  "pl": "Miejsce / link Teams",
  "tr": "Konum / Teams bağlantısı",
  "ru": "Место / ссылка Teams"
 }
}


# The Free-to-Pro compatibility tasks have distinct titles not present in the
# regular product UI dictionary. Never replace them with a generic fallback.
SURFACE_TASK_TITLES = {
 "Informationen vergleichen": {
  "en": "Compare information",
  "fr": "Comparer des informations",
  "it": "Confrontare informazioni",
  "es": "Comparar información",
  "pt": "Comparar informações",
  "nl": "Informatie vergelijken",
  "pl": "Porównać informacje",
  "tr": "Bilgileri karşılaştır",
  "ru": "Сравнить сведения"
 },
 "Management-Briefing": {
  "en": "Management briefing",
  "fr": "Note de synthèse pour la direction",
  "it": "Briefing per la direzione",
  "es": "Informe para la dirección",
  "pt": "Briefing para a direção",
  "nl": "Managementbriefing",
  "pl": "Informacja dla kierownictwa",
  "tr": "Yönetim bilgilendirmesi",
  "ru": "Справка для руководства"
 },
 "Besprechung analysieren": {
  "en": "Analyze a meeting",
  "fr": "Analyser une réunion",
  "it": "Analizzare una riunione",
  "es": "Analizar una reunión",
  "pt": "Analisar uma reunião",
  "nl": "Vergadering analyseren",
  "pl": "Przeanalizować spotkanie",
  "tr": "Toplantıyı analiz et",
  "ru": "Проанализировать встречу"
 },
 "Management-Recap": {
  "en": "Management recap",
  "fr": "Récapitulatif pour la direction",
  "it": "Riepilogo per la direzione",
  "es": "Resumen para la dirección",
  "pt": "Resumo para a direção",
  "nl": "Managementsamenvatting",
  "pl": "Podsumowanie dla kierownictwa",
  "tr": "Yönetim özeti",
  "ru": "Сводка для руководства"
 },
 "Strukturierten Bericht erstellen": {
  "en": "Create a structured report",
  "fr": "Créer un rapport structuré",
  "it": "Creare un rapporto strutturato",
  "es": "Crear un informe estructurado",
  "pt": "Criar um relatório estruturado",
  "nl": "Gestructureerd rapport opstellen",
  "pl": "Utworzyć raport strukturalny",
  "tr": "Yapılandırılmış rapor oluştur",
  "ru": "Подготовить структурированный отчёт"
 },
 "Risiken und Lücken analysieren": {
  "en": "Analyze risks and gaps",
  "fr": "Analyser les risques et les lacunes",
  "it": "Analizzare rischi e lacune",
  "es": "Analizar riesgos y lagunas",
  "pt": "Analisar riscos e lacunas",
  "nl": "Risico's en hiaten analyseren",
  "pl": "Przeanalizować ryzyka i luki",
  "tr": "Riskleri ve eksikleri analiz et",
  "ru": "Проанализировать риски и пробелы"
 },
 "Trends und Auffälligkeiten": {
  "en": "Trends and anomalies",
  "fr": "Tendances et anomalies",
  "it": "Tendenze e anomalie",
  "es": "Tendencias y anomalías",
  "pt": "Tendências e anomalias",
  "nl": "Trends en afwijkingen",
  "pl": "Trendy i nieprawidłowości",
  "tr": "Eğilimler ve anormallikler",
  "ru": "Тенденции и отклонения"
 },
 "Management-Auswertung": {
  "en": "Management analysis",
  "fr": "Analyse pour la direction",
  "it": "Analisi per la direzione",
  "es": "Análisis para la dirección",
  "pt": "Análise para a direção",
  "nl": "Managementanalyse",
  "pl": "Analiza dla kierownictwa",
  "tr": "Yönetim analizi",
  "ru": "Аналитика для руководства"
 },
 "Präsentation analysieren": {
  "en": "Analyze a presentation",
  "fr": "Analyser une présentation",
  "it": "Analizzare una presentazione",
  "es": "Analizar una presentación",
  "pt": "Analisar uma apresentação",
  "nl": "Presentatie analyseren",
  "pl": "Przeanalizować prezentację",
  "tr": "Sunumu analiz et",
  "ru": "Проанализировать презентацию"
 },
 "Executive Summary": {
  "en": "Executive summary",
  "fr": "Synthèse de direction",
  "it": "Sintesi direzionale",
  "es": "Resumen ejecutivo",
  "pt": "Resumo executivo",
  "nl": "Managementsamenvatting",
  "pl": "Streszczenie dla kierownictwa",
  "tr": "Yönetici özeti",
  "ru": "Резюме для руководства"
 }
}


# Context-sensitive native-language methods for all PM20 task families.
FAMILY_METHODS = {
 "research": {
  "en": "Verify the question using available reliable evidence. Cite sources when available, compare conflicting claims, and state uncertainty and currency of the evidence.",
  "fr": "Vérifiez la question avec des sources fiables disponibles. Citez les sources, confrontez les affirmations contradictoires et signalez les incertitudes et l'actualité des données.",
  "it": "Verifica la domanda con fonti affidabili disponibili. Cita le fonti, confronta affermazioni contrastanti e indica incertezze e attualità dei dati.",
  "es": "Verifica la cuestión con fuentes fiables disponibles. Cita las fuentes, compara afirmaciones contradictorias e indica incertidumbres y vigencia de los datos.",
  "pt": "Verifique a questão com fontes fiáveis disponíveis. Cite as fontes, confronte afirmações divergentes e indique incertezas e atualidade dos dados.",
  "nl": "Onderzoek de vraag aan de hand van beschikbare betrouwbare bronnen. Vermeld bronnen, vergelijk tegenstrijdige claims en benoem onzekerheden en actualiteit.",
  "pl": "Zweryfikuj zagadnienie na podstawie dostępnych wiarygodnych źródeł. Cytuj źródła, porównuj sprzeczne twierdzenia i wskaż niepewności oraz aktualność danych.",
  "tr": "Soruyu mevcut güvenilir kanıtlarla doğrulayın. Kaynakları belirtin, çelişkili iddiaları karşılaştırın ve belirsizlikleri ve bilgilerin güncelliğini açıklayın.",
  "ru": "Проверьте вопрос по доступным надёжным источникам. Указывайте источники, сопоставляйте противоречивые сведения и отмечайте неопределённость и актуальность данных."
 },
 "data": {
  "en": "Check data scope, types, quality and missing values before calculating. Explain formulas, units, trends and outliers, and distinguish correlation from causation.",
  "fr": "Vérifiez le périmètre, les types, la qualité et les valeurs manquantes avant tout calcul. Expliquez les formules, unités, tendances et anomalies, sans confondre corrélation et causalité.",
  "it": "Prima dei calcoli verifica ambito, tipi, qualità e valori mancanti. Spiega formule, unità, tendenze e anomalie, distinguendo correlazione e causalità.",
  "es": "Comprueba alcance, tipos, calidad y valores ausentes antes de calcular. Explica fórmulas, unidades, tendencias y anomalías; distingue correlación y causalidad.",
  "pt": "Verifique o âmbito, tipos, qualidade e valores em falta antes de calcular. Explique fórmulas, unidades, tendências e anomalias; distinga correlação de causalidade.",
  "nl": "Controleer gegevensbereik, typen, kwaliteit en ontbrekende waarden vóór berekeningen. Leg formules, eenheden, trends en afwijkingen uit; onderscheid correlatie van causaliteit.",
  "pl": "Sprawdź zakres, typy, jakość danych i braki przed obliczeniami. Wyjaśnij wzory, jednostki, trendy i odstępstwa, odróżniając korelację od przyczynowości.",
  "tr": "Hesaplamadan önce veri kapsamını, türlerini, kalitesini ve eksik değerleri kontrol edin. Formülleri, birimleri, eğilimleri ve aykırı değerleri açıklayın; korelasyonla nedenselliği ayırın.",
  "ru": "До расчётов проверьте объём, типы, качество и пропущенные значения данных. Объясните формулы, единицы, тенденции и выбросы; отличайте корреляцию от причинности."
 },
 "code": {
  "en": "Clarify the required behaviour, runtime, interfaces and constraints. Propose safe, runnable changes with error handling, tests and explicit assumptions; do not claim execution without evidence.",
  "fr": "Précisez le comportement attendu, l'environnement, les interfaces et contraintes. Proposez des modifications exécutables, des contrôles d'erreur et des tests ; ne prétendez pas avoir exécuté le code sans preuve.",
  "it": "Chiarisci il comportamento richiesto, l'ambiente, le interfacce e i vincoli. Proponi modifiche eseguibili, gestione degli errori e test; non dichiarare esecuzioni non verificate.",
  "es": "Aclara comportamiento, entorno, interfaces y restricciones. Propón cambios ejecutables con manejo de errores y pruebas; no afirmes haberlos ejecutado sin pruebas.",
  "pt": "Esclareça o comportamento, ambiente, interfaces e restrições. Proponha alterações executáveis, tratamento de erros e testes; não alegue execução sem evidências.",
  "nl": "Verduidelijk verwacht gedrag, runtime, interfaces en randvoorwaarden. Stel uitvoerbare wijzigingen, foutafhandeling en tests voor; claim geen uitvoering zonder bewijs.",
  "pl": "Wyjaśnij oczekiwane działanie, środowisko, interfejsy i ograniczenia. Zaproponuj wykonalne zmiany, obsługę błędów i testy; nie deklaruj wykonania bez dowodów.",
  "tr": "Beklenen davranışı, çalışma ortamını, arayüzleri ve kısıtları netleştirin. Hata yönetimi ve testler içeren çalıştırılabilir değişiklikler önerin; kanıt olmadan çalıştırıldığını söylemeyin.",
  "ru": "Уточните требуемое поведение, среду, интерфейсы и ограничения. Предложите исполнимые изменения с обработкой ошибок и тестами; не заявляйте об исполнении без доказательств."
 },
 "agent": {
  "en": "Define the agent's objective, permissions, available tools, triggers, stop conditions and approval boundaries. Sequence steps and include human review for consequential actions.",
  "fr": "Définissez l'objectif de l'agent, ses droits, outils, déclencheurs, conditions d'arrêt et validations requises. Organisez les étapes et prévoyez une revue humaine pour les actions importantes.",
  "it": "Definisci obiettivo, permessi, strumenti, attivatori, condizioni di arresto e approvazioni dell'agente. Ordina i passaggi e prevedi verifiche umane per le azioni rilevanti.",
  "es": "Define objetivo, permisos, herramientas, activadores, condiciones de parada y aprobaciones del agente. Ordena los pasos y prevé revisión humana para acciones importantes.",
  "pt": "Defina objetivo, permissões, ferramentas, acionadores, condições de paragem e aprovações do agente. Ordene os passos e inclua revisão humana para ações importantes.",
  "nl": "Definieer doel, rechten, tools, triggers, stopvoorwaarden en goedkeuringsgrenzen van de agent. Orden stappen en vereis menselijke controle voor belangrijke acties.",
  "pl": "Określ cel agenta, uprawnienia, narzędzia, wyzwalacze, warunki zakończenia i zgody. Uporządkuj kroki i uwzględnij kontrolę człowieka przy istotnych działaniach.",
  "tr": "Ajanın hedefini, izinlerini, araçlarını, tetikleyicilerini, durma koşullarını ve onay sınırlarını belirleyin. Adımları sıralayın; önemli işlemlerde insan denetimi sağlayın.",
  "ru": "Определите цель агента, разрешения, инструменты, триггеры, условия остановки и границы согласования. Упорядочите шаги и добавьте проверку человеком для значимых действий."
 },
 "build": {
  "en": "Define deliverables, prerequisites and acceptance criteria. Provide reproducible implementation steps, dependencies and validation checks without assuming resources not supplied.",
  "fr": "Définissez les livrables, prérequis et critères de réception. Donnez des étapes reproductibles, dépendances et contrôles sans supposer de ressources absentes.",
  "it": "Definisci risultati, prerequisiti e criteri di accettazione. Fornisci passaggi riproducibili, dipendenze e verifiche senza presupporre risorse non disponibili.",
  "es": "Define entregables, requisitos previos y criterios de aceptación. Detalla pasos reproducibles, dependencias y comprobaciones sin suponer recursos no disponibles.",
  "pt": "Defina entregáveis, pré-requisitos e critérios de aceitação. Indique etapas reproduzíveis, dependências e verificações sem pressupor recursos indisponíveis.",
  "nl": "Definieer opleveringen, voorwaarden en acceptatiecriteria. Geef reproduceerbare stappen, afhankelijkheden en controles zonder ontbrekende middelen te veronderstellen.",
  "pl": "Zdefiniuj wyniki, wymagania wstępne i kryteria akceptacji. Podaj powtarzalne kroki, zależności i testy bez zakładania niedostępnych zasobów.",
  "tr": "Teslimatları, ön koşulları ve kabul ölçütlerini tanımlayın. Bulunmayan kaynakları varsaymadan tekrarlanabilir adımları, bağımlılıkları ve testleri açıklayın.",
  "ru": "Определите результаты, предпосылки и критерии приёмки. Укажите воспроизводимые шаги, зависимости и проверки без предположений о недоступных ресурсах."
 },
 "design": {
  "en": "Identify users, goals, constraints and accessibility needs. Explain structure, interaction, alternatives and validation criteria while keeping branding consistent.",
  "fr": "Identifiez les utilisateurs, objectifs, contraintes et besoins d'accessibilité. Expliquez la structure, les interactions, les options et les critères de vérification en respectant la marque.",
  "it": "Individua utenti, obiettivi, vincoli e accessibilità. Spiega struttura, interazioni, alternative e criteri di verifica mantenendo il marchio coerente.",
  "es": "Identifica usuarios, objetivos, restricciones y accesibilidad. Explica estructura, interacción, alternativas y criterios de validación respetando la marca.",
  "pt": "Identifique utilizadores, objetivos, restrições e acessibilidade. Explique estrutura, interação, alternativas e critérios de validação respeitando a marca.",
  "nl": "Breng gebruikers, doelen, beperkingen en toegankelijkheid in kaart. Leg structuur, interacties, alternatieven en toetsingscriteria uit met behoud van de huisstijl.",
  "pl": "Określ użytkowników, cele, ograniczenia i dostępność. Wyjaśnij strukturę, interakcje, warianty i kryteria weryfikacji przy zachowaniu identyfikacji marki.",
  "tr": "Kullanıcıları, hedefleri, kısıtları ve erişilebilirliği belirleyin. Marka tutarlılığını koruyarak yapıyı, etkileşimleri, seçenekleri ve doğrulama ölçütlerini açıklayın.",
  "ru": "Определите пользователей, цели, ограничения и доступность. Объясните структуру, взаимодействия, варианты и критерии проверки с учётом бренда."
 },
 "operation": {
  "en": "Review operating state, dependencies and indicators. Separate observed issues from hypotheses, prioritize remediation and specify monitoring and rollback checks.",
  "fr": "Examinez l'état opérationnel, les dépendances et indicateurs. Distinguez les problèmes observés des hypothèses, hiérarchisez les corrections et prévoyez suivi et retour arrière.",
  "it": "Esamina stato operativo, dipendenze e indicatori. Distingui problemi osservati da ipotesi, dai priorità agli interventi e definisci monitoraggio e ripristino.",
  "es": "Revisa estado operativo, dependencias e indicadores. Separa incidencias observadas de hipótesis, prioriza correcciones y establece supervisión y reversión.",
  "pt": "Analise o estado operacional, dependências e indicadores. Distinga problemas observados de hipóteses, priorize correções e defina monitorização e reversão.",
  "nl": "Beoordeel operationele status, afhankelijkheden en indicatoren. Scheid waargenomen problemen van aannames, prioriteer herstel en definieer monitoring en terugval.",
  "pl": "Oceń stan operacyjny, zależności i wskaźniki. Oddziel obserwacje od hipotez, ustal priorytety napraw i zasady monitoringu oraz wycofania zmian.",
  "tr": "Operasyon durumunu, bağımlılıkları ve göstergeleri inceleyin. Gözlenen sorunları varsayımlardan ayırın, düzeltmeleri önceliklendirin, izleme ve geri alma kontrollerini tanımlayın.",
  "ru": "Оцените рабочее состояние, зависимости и показатели. Отделите наблюдаемые проблемы от гипотез, расставьте приоритеты исправлений и задайте мониторинг и откат."
 },
 "automation": {
  "en": "Specify triggers, inputs, transformations, outputs, credentials and failure handling. Define idempotency, retries, logging, permissions and safe rollback.",
  "fr": "Définissez déclencheurs, entrées, traitements, sorties, identifiants et gestion des erreurs. Précisez idempotence, nouvelles tentatives, journaux, droits et retour arrière sécurisé.",
  "it": "Specifica attivatori, input, trasformazioni, output, credenziali e gestione degli errori. Definisci idempotenza, tentativi, log, permessi e ripristino sicuro.",
  "es": "Especifica activadores, entradas, transformaciones, salidas, credenciales y manejo de fallos. Define idempotencia, reintentos, registros, permisos y reversión segura.",
  "pt": "Especifique acionadores, entradas, transformações, saídas, credenciais e tratamento de falhas. Defina idempotência, novas tentativas, registos, permissões e reversão segura.",
  "nl": "Specificeer triggers, invoer, bewerkingen, uitvoer, inloggegevens en foutafhandeling. Definieer idempotentie, herhaalpogingen, logging, rechten en veilige terugval.",
  "pl": "Określ wyzwalacze, dane wejściowe, przekształcenia, wyniki, dane dostępowe i obsługę błędów. Uwzględnij idempotencję, ponawianie, logi, prawa i bezpieczne wycofanie.",
  "tr": "Tetikleyicileri, girdileri, dönüşümleri, çıktıları, kimlik bilgilerini ve hata yönetimini belirtin. Tekrarlanabilirlik, yeniden deneme, günlük, izin ve güvenli geri alma kurallarını tanımlayın.",
  "ru": "Определите триггеры, входы, преобразования, выходы, учётные данные и обработку ошибок. Укажите идемпотентность, повторы, журналы, права и безопасный откат."
 },
 "security": {
  "en": "Identify assets, threat scenarios and trust boundaries. Prioritize realistic risks, mitigations and verification, and never imply a vulnerability has been fixed without evidence.",
  "fr": "Identifiez les actifs, menaces et frontières de confiance. Hiérarchisez risques, mesures et vérifications ; ne déclarez pas une faille corrigée sans preuve.",
  "it": "Individua risorse, minacce e confini di fiducia. Dai priorità a rischi, mitigazioni e verifiche senza dichiarare corretta una vulnerabilità senza prova.",
  "es": "Identifica activos, amenazas y límites de confianza. Prioriza riesgos, mitigaciones y comprobaciones; no afirmes que una vulnerabilidad se haya corregido sin pruebas.",
  "pt": "Identifique ativos, ameaças e fronteiras de confiança. Priorize riscos, mitigação e verificação; não afirme correções de vulnerabilidades sem evidência.",
  "nl": "Inventariseer bedrijfsmiddelen, dreigingen en vertrouwensgrenzen. Prioriteer risico's, maatregelen en controles; claim geen opgelost beveiligingslek zonder bewijs.",
  "pl": "Określ zasoby, zagrożenia i granice zaufania. Ustal priorytety ryzyk, zabezpieczeń i testów; nie deklaruj usunięcia luki bez dowodu.",
  "tr": "Varlıkları, tehditleri ve güven sınırlarını belirleyin. Riskleri, önlemleri ve doğrulamayı önceliklendirin; kanıt olmadan açığın giderildiğini iddia etmeyin.",
  "ru": "Определите активы, угрозы и границы доверия. Расставьте приоритеты рисков, мер защиты и проверок; не заявляйте об устранении уязвимостей без доказательств."
 },
 "search": {
  "en": "Define search terms, scope and filters. Collect relevant available results, identify duplicates, rank by evidence and clearly cite sources.",
  "fr": "Définissez termes, périmètre et filtres. Recueillez les résultats accessibles, éliminez les doublons, classez les preuves et citez les sources.",
  "it": "Definisci termini, ambito e filtri. Raccogli i risultati disponibili, elimina duplicati, classifica per rilevanza e cita le fonti.",
  "es": "Define términos, alcance y filtros. Recopila resultados disponibles, elimina duplicados, ordénalos por evidencia y cita las fuentes.",
  "pt": "Defina termos, âmbito e filtros. Recolha resultados disponíveis, elimine duplicados, ordene por evidência e cite fontes.",
  "nl": "Bepaal zoektermen, bereik en filters. Verzamel beschikbare resultaten, verwijder dubbelen, rangschik op bewijs en vermeld bronnen.",
  "pl": "Określ frazy, zakres i filtry. Zbierz dostępne wyniki, usuń duplikaty, uszereguj według dowodów i podaj źródła.",
  "tr": "Arama terimlerini, kapsamı ve filtreleri belirleyin. Mevcut sonuçları toplayın, tekrarları kaldırın, kanıta göre sıralayın ve kaynakları belirtin.",
  "ru": "Определите запросы, охват и фильтры. Соберите доступные результаты, удалите дубликаты, отсортируйте по доказательствам и укажите источники."
 },
 "coaching": {
  "en": "Assess the current skill level and goal. Explain one step at a time, include practical exercises, check comprehension and adapt difficulty without inventing feedback.",
  "fr": "Évaluez le niveau et l'objectif. Expliquez pas à pas, proposez des exercices, vérifiez la compréhension et adaptez la difficulté sans inventer de retours.",
  "it": "Valuta livello e obiettivo. Spiega passo dopo passo, proponi esercizi, verifica la comprensione e adatta la difficoltà senza inventare riscontri.",
  "es": "Evalúa nivel y objetivo. Explica paso a paso, incluye ejercicios, comprueba comprensión y adapta dificultad sin inventar respuestas.",
  "pt": "Avalie nível e objetivo. Explique por etapas, inclua exercícios, verifique a compreensão e ajuste a dificuldade sem inventar respostas.",
  "nl": "Beoordeel niveau en doel. Leg stapsgewijs uit, geef oefeningen, controleer begrip en pas moeilijkheid aan zonder feedback te verzinnen.",
  "pl": "Oceń poziom i cel. Wyjaśniaj krok po kroku, proponuj ćwiczenia, sprawdzaj zrozumienie i dostosuj trudność bez zmyślania informacji zwrotnych.",
  "tr": "Mevcut seviyeyi ve hedefi değerlendirin. Adım adım açıklayın, uygulama çalışmaları verin, kavrayışı kontrol edin ve geri bildirim uydurmadan zorluğu ayarlayın.",
  "ru": "Оцените уровень и цель. Объясняйте по шагам, предлагайте упражнения, проверяйте понимание и адаптируйте сложность без выдуманных отзывов."
 }
}


# Style preferences are selected using canonical internal codes.
STYLE_MODIFIERS = {
 "professional": {
  "en": "Use a professional, clear and precise tone.",
  "fr": "Adoptez un ton professionnel, clair et précis.",
  "it": "Usa un tono professionale, chiaro e preciso.",
  "es": "Utiliza un tono profesional, claro y preciso.",
  "pt": "Utilize um tom profissional, claro e preciso.",
  "nl": "Gebruik een professionele, heldere en nauwkeurige toon.",
  "pl": "Stosuj profesjonalny, jasny i precyzyjny styl.",
  "tr": "Profesyonel, açık ve kesin bir üslup kullanın.",
  "ru": "Используйте профессиональный, ясный и точный стиль."
 },
 "friendly": {
  "en": "Use a friendly, respectful and professional tone.",
  "fr": "Adoptez un ton cordial, respectueux et professionnel.",
  "it": "Usa un tono cordiale, rispettoso e professionale.",
  "es": "Utiliza un tono cordial, respetuoso y profesional.",
  "pt": "Utilize um tom cordial, respeitoso e profissional.",
  "nl": "Gebruik een vriendelijke, respectvolle en professionele toon.",
  "pl": "Stosuj przyjazny, pełen szacunku i profesjonalny ton.",
  "tr": "Dostane, saygılı ve profesyonel bir üslup kullanın.",
  "ru": "Используйте дружелюбный, уважительный и профессиональный тон."
 },
 "factual": {
  "en": "Use a factual, neutral tone without unsupported judgments.",
  "fr": "Utilisez un ton factuel et neutre, sans jugement non étayé.",
  "it": "Usa un tono oggettivo e neutro, senza giudizi non supportati.",
  "es": "Utiliza un tono objetivo y neutral, sin juicios infundados.",
  "pt": "Utilize um tom factual e neutro, sem juízos sem fundamento.",
  "nl": "Gebruik een feitelijke, neutrale toon zonder ongefundeerde oordelen.",
  "pl": "Stosuj rzeczowy, neutralny styl bez nieuzasadnionych ocen.",
  "tr": "Kanıtsız yargılardan uzak, nesnel ve tarafsız bir üslup kullanın.",
  "ru": "Используйте фактический, нейтральный стиль без необоснованных оценок."
 },
 "short": {
  "en": "Keep the response very short and include only essential points.",
  "fr": "Restez très bref et ne conservez que les points essentiels.",
  "it": "Sii molto breve e includi solo i punti essenziali.",
  "es": "Sé muy breve e incluye solo lo esencial.",
  "pt": "Seja muito breve e inclua apenas o essencial.",
  "nl": "Houd het antwoord zeer kort en beperk het tot het belangrijkste.",
  "pl": "Odpowiedz bardzo krótko i uwzględnij tylko najważniejsze informacje.",
  "tr": "Yanıtı çok kısa tutun ve yalnızca temel noktaları ekleyin.",
  "ru": "Ответьте очень кратко, оставив только самое важное."
 },
 "compact": {
  "en": "Make the response concise but complete, without needless repetition.",
  "fr": "Soyez concis mais complet, sans répétitions inutiles.",
  "it": "Sii conciso ma completo, senza ripetizioni inutili.",
  "es": "Sé conciso pero completo, sin repeticiones innecesarias.",
  "pt": "Seja conciso mas completo, sem repetições desnecessárias.",
  "nl": "Wees beknopt maar volledig, zonder onnodige herhaling.",
  "pl": "Odpowiedz zwięźle, lecz wyczerpująco, bez powtórzeń.",
  "tr": "Gereksiz tekrar olmadan kısa ama eksiksiz yanıt verin.",
  "ru": "Отвечайте сжато, но полно, без лишних повторов."
 },
 "standard": {
  "en": "Provide sufficient detail to make the result directly usable.",
  "fr": "Fournissez assez de détails pour rendre le résultat directement exploitable.",
  "it": "Fornisci dettagli sufficienti per rendere il risultato subito utilizzabile.",
  "es": "Incluye detalles suficientes para que el resultado pueda utilizarse directamente.",
  "pt": "Inclua detalhes suficientes para que o resultado possa ser utilizado diretamente.",
  "nl": "Geef voldoende details om het resultaat direct bruikbaar te maken.",
  "pl": "Podaj wystarczające szczegóły, by wynik można było od razu wykorzystać.",
  "tr": "Sonucu doğrudan kullanılabilir kılacak yeterli ayrıntıyı verin.",
  "ru": "Дайте достаточно деталей для непосредственного использования результата."
 }
}


# Source constraints are canonical codes; do not turn them into promises of access.
SOURCE_RULES = {
 "webwork": {
  "en": "Use accessible web and work-context sources.",
  "fr": "Utilisez les sources Web et professionnelles accessibles.",
  "it": "Usa le fonti web e del contesto lavorativo accessibili.",
  "es": "Usa fuentes web y del entorno laboral accesibles.",
  "pt": "Utilize fontes Web e de trabalho acessíveis.",
  "nl": "Gebruik toegankelijke web- en werkbronnen.",
  "pl": "Korzystaj z dostępnych źródeł internetowych i służbowych.",
  "tr": "Erişilebilir web ve iş bağlamı kaynaklarını kullanın.",
  "ru": "Используйте доступные веб-источники и рабочий контекст."
 },
 "web": {
  "en": "Use accessible, verifiable web sources.",
  "fr": "Utilisez des sources Web accessibles et vérifiables.",
  "it": "Usa fonti web accessibili e verificabili.",
  "es": "Usa fuentes web accesibles y verificables.",
  "pt": "Utilize fontes Web acessíveis e verificáveis.",
  "nl": "Gebruik toegankelijke, controleerbare webbronnen.",
  "pl": "Korzystaj z dostępnych i weryfikowalnych źródeł internetowych.",
  "tr": "Erişilebilir ve doğrulanabilir web kaynaklarını kullanın.",
  "ru": "Используйте доступные и проверяемые веб-источники."
 },
 "provided": {
  "en": "Use only information explicitly supplied with this request.",
  "fr": "Utilisez uniquement les informations fournies dans cette demande.",
  "it": "Usa soltanto le informazioni esplicitamente fornite nella richiesta.",
  "es": "Usa solo la información proporcionada en esta solicitud.",
  "pt": "Utilize apenas as informações fornecidas neste pedido.",
  "nl": "Gebruik uitsluitend expliciet aangeleverde informatie.",
  "pl": "Korzystaj wyłącznie z informacji przekazanych w tym zapytaniu.",
  "tr": "Yalnızca bu istekle açıkça sağlanan bilgileri kullanın.",
  "ru": "Используйте только сведения, явно предоставленные в запросе."
 },
 "work": {
  "en": "Use the current accessible Microsoft 365 work context.",
  "fr": "Utilisez le contexte professionnel Microsoft 365 actuellement accessible.",
  "it": "Usa il contesto di lavoro Microsoft 365 attualmente accessibile.",
  "es": "Usa el contexto laboral de Microsoft 365 actualmente accesible.",
  "pt": "Utilize o contexto de trabalho Microsoft 365 atualmente acessível.",
  "nl": "Gebruik de momenteel toegankelijke Microsoft 365-werkcontext.",
  "pl": "Korzystaj z obecnie dostępnego kontekstu pracy Microsoft 365.",
  "tr": "Şu anda erişilebilir Microsoft 365 iş bağlamını kullanın.",
  "ru": "Используйте доступный рабочий контекст Microsoft 365."
 },
 "data": {
  "en": "Use only the datasets actually provided or accessible.",
  "fr": "Utilisez uniquement les jeux de données fournis ou accessibles.",
  "it": "Usa solo i set di dati forniti o accessibili.",
  "es": "Usa solo los conjuntos de datos proporcionados o accesibles.",
  "pt": "Utilize apenas os conjuntos de dados fornecidos ou acessíveis.",
  "nl": "Gebruik alleen daadwerkelijk aangeleverde of toegankelijke datasets.",
  "pl": "Korzystaj tylko z dostarczonych lub dostępnych zestawów danych.",
  "tr": "Yalnızca gerçekten sağlanan veya erişilebilir veri kümelerini kullanın.",
  "ru": "Используйте только предоставленные или доступные наборы данных."
 },
 "product": {
  "en": "Rely on verified product information and accessible technical documentation.",
  "fr": "Appuyez-vous sur des informations produit vérifiées et la documentation technique accessible.",
  "it": "Basati su informazioni di prodotto verificate e documentazione tecnica accessibile.",
  "es": "Básate en información de producto verificada y documentación técnica accesible.",
  "pt": "Baseie-se em informação de produto verificada e documentação técnica acessível.",
  "nl": "Gebruik geverifieerde productinformatie en toegankelijke technische documentatie.",
  "pl": "Opieraj się na sprawdzonych informacjach o produkcie i dostępnej dokumentacji.",
  "tr": "Doğrulanmış ürün bilgilerine ve erişilebilir teknik belgelere dayanın.",
  "ru": "Опирайтесь на проверенные сведения о продукте и доступную документацию."
 },
 "crm": {
  "en": "Use only CRM records that are actually accessible in the current context.",
  "fr": "Utilisez uniquement les dossiers CRM effectivement accessibles.",
  "it": "Usa solo i record CRM effettivamente accessibili.",
  "es": "Usa solo los registros CRM realmente accesibles.",
  "pt": "Utilize apenas os registos CRM efetivamente acessíveis.",
  "nl": "Gebruik alleen CRM-records die werkelijk toegankelijk zijn.",
  "pl": "Korzystaj tylko z rekordów CRM faktycznie dostępnych.",
  "tr": "Yalnızca mevcut bağlamda gerçekten erişilebilir CRM kayıtlarını kullanın.",
  "ru": "Используйте только реально доступные записи CRM."
 },
 "knowledge": {
  "en": "Use accessible knowledge-base content and explicitly supplied documents.",
  "fr": "Utilisez la base de connaissances accessible et les documents fournis.",
  "it": "Usa la base di conoscenza accessibile e i documenti forniti.",
  "es": "Usa la base de conocimientos accesible y los documentos proporcionados.",
  "pt": "Utilize a base de conhecimentos acessível e os documentos fornecidos.",
  "nl": "Gebruik toegankelijke kennisbankinhoud en aangeleverde documenten.",
  "pl": "Korzystaj z dostępnej bazy wiedzy i przekazanych dokumentów.",
  "tr": "Erişilebilir bilgi tabanını ve açıkça sağlanan belgeleri kullanın.",
  "ru": "Используйте доступную базу знаний и переданные документы."
 },
 "erp": {
  "en": "Use only ERP records and business data that can actually be accessed.",
  "fr": "Utilisez uniquement les données ERP et commerciales réellement accessibles.",
  "it": "Usa solo i record ERP e i dati aziendali effettivamente accessibili.",
  "es": "Usa solo registros ERP y datos empresariales realmente accesibles.",
  "pt": "Utilize apenas registos ERP e dados empresariais efetivamente acessíveis.",
  "nl": "Gebruik alleen werkelijk toegankelijke ERP-gegevens en bedrijfsdata.",
  "pl": "Korzystaj tylko z rzeczywiście dostępnych danych ERP i biznesowych.",
  "tr": "Yalnızca gerçekten erişilebilir ERP kayıtlarını ve iş verilerini kullanın.",
  "ru": "Используйте только реально доступные записи ERP и бизнес-данные."
 },
 "security": {
  "en": "Use actual security telemetry, logs and verified incident details.",
  "fr": "Utilisez les journaux, signaux de sécurité et détails d'incident vérifiés.",
  "it": "Usa log, segnali di sicurezza e dettagli degli incidenti verificati.",
  "es": "Usa registros, telemetría de seguridad y detalles de incidentes verificados.",
  "pt": "Utilize registos, telemetria de segurança e detalhes de incidentes verificados.",
  "nl": "Gebruik echte beveiligingslogboeken, signalen en geverifieerde incidentgegevens.",
  "pl": "Korzystaj z rzeczywistych logów, telemetrii i potwierdzonych danych incydentów.",
  "tr": "Gerçek güvenlik günlüklerini, telemetriyi ve doğrulanmış olay bilgilerini kullanın.",
  "ru": "Используйте реальные журналы, телеметрию и проверенные сведения об инцидентах."
 },
 "azure": {
  "en": "Use only Azure resources and configuration details that are accessible.",
  "fr": "Utilisez uniquement les ressources Azure et configurations accessibles.",
  "it": "Usa solo risorse Azure e configurazioni accessibili.",
  "es": "Usa solo recursos de Azure y configuraciones accesibles.",
  "pt": "Utilize apenas recursos Azure e configurações acessíveis.",
  "nl": "Gebruik alleen toegankelijke Azure-resources en configuratiegegevens.",
  "pl": "Korzystaj tylko z dostępnych zasobów Azure i konfiguracji.",
  "tr": "Yalnızca erişilebilir Azure kaynaklarını ve yapılandırmalarını kullanın.",
  "ru": "Используйте только доступные ресурсы Azure и настройки."
 },
 "repo": {
  "en": "Use the actual accessible repository files, code and change history.",
  "fr": "Utilisez les fichiers, le code et l'historique du dépôt réellement accessibles.",
  "it": "Usa file, codice e cronologia delle modifiche del repository accessibili.",
  "es": "Usa archivos, código e historial de cambios del repositorio accesible.",
  "pt": "Utilize ficheiros, código e histórico de alterações do repositório acessível.",
  "nl": "Gebruik werkelijk toegankelijke repositorybestanden, code en wijzigingshistorie.",
  "pl": "Korzystaj z faktycznie dostępnych plików repozytorium, kodu i historii zmian.",
  "tr": "Erişilebilir depo dosyalarını, kodu ve değişiklik geçmişini kullanın.",
  "ru": "Используйте доступные файлы репозитория, код и историю изменений."
 },
 "notebook": {
  "en": "Use the current accessible notebook content and its referenced sources.",
  "fr": "Utilisez le carnet accessible et ses sources référencées.",
  "it": "Usa il contenuto del taccuino accessibile e le fonti citate.",
  "es": "Usa el cuaderno accesible y sus fuentes referenciadas.",
  "pt": "Utilize o bloco de notas acessível e as fontes referenciadas.",
  "nl": "Gebruik de toegankelijke notitieblokinhoud en bijbehorende bronnen.",
  "pl": "Korzystaj z dostępnej zawartości notatnika i wskazanych źródeł.",
  "tr": "Erişilebilir not defteri içeriğini ve belirtilen kaynakları kullanın.",
  "ru": "Используйте доступное содержимое блокнота и указанные источники."
 }
}


# Reviewed audience and focus labels that are not in the UI dictionary.
FOCUS_AUDIENCE_LABELS = {
 "Primärquellen": {
  "en": "Primary sources",
  "fr": "Sources primaires",
  "it": "Fonti primarie",
  "es": "Fuentes primarias",
  "pt": "Fontes primárias",
  "nl": "Primaire bronnen",
  "pl": "Źródła pierwotne",
  "tr": "Birincil kaynaklar",
  "ru": "Первоисточники"
 },
 "Widersprüche": {
  "en": "Contradictions",
  "fr": "Contradictions",
  "it": "Contraddizioni",
  "es": "Contradicciones",
  "pt": "Contradições",
  "nl": "Tegenstrijdigheden",
  "pl": "Sprzeczności",
  "tr": "Çelişkiler",
  "ru": "Противоречия"
 },
 "Unterschiede": {
  "en": "Differences",
  "fr": "Différences",
  "it": "Differenze",
  "es": "Diferencias",
  "pt": "Diferenças",
  "nl": "Verschillen",
  "pl": "Różnice",
  "tr": "Farklar",
  "ru": "Различия"
 },
 "Trends": {
  "en": "Trends",
  "fr": "Tendances",
  "it": "Tendenze",
  "es": "Tendencias",
  "pt": "Tendências",
  "nl": "Trends",
  "pl": "Trendy",
  "tr": "Eğilimler",
  "ru": "Тенденции"
 },
 "Performance": {
  "en": "Performance",
  "fr": "Performance",
  "it": "Prestazioni",
  "es": "Rendimiento",
  "pt": "Desempenho",
  "nl": "Prestaties",
  "pl": "Wydajność",
  "tr": "Performans",
  "ru": "Производительность"
 },
 "Sicherheit": {
  "en": "Security",
  "fr": "Sécurité",
  "it": "Sicurezza",
  "es": "Seguridad",
  "pt": "Segurança",
  "nl": "Beveiliging",
  "pl": "Bezpieczeństwo",
  "tr": "Güvenlik",
  "ru": "Безопасность"
 },
 "Wartbarkeit": {
  "en": "Maintainability",
  "fr": "Maintenabilité",
  "it": "Manutenibilità",
  "es": "Mantenibilidad",
  "pt": "Manutenibilidade",
  "nl": "Onderhoudbaarheid",
  "pl": "Utrzymywalność",
  "tr": "Bakım kolaylığı",
  "ru": "Сопровождаемость"
 },
 "Scope": {
  "en": "Scope",
  "fr": "Périmètre",
  "it": "Ambito",
  "es": "Alcance",
  "pt": "Âmbito",
  "nl": "Reikwijdte",
  "pl": "Zakres",
  "tr": "Kapsam",
  "ru": "Охват"
 },
 "Tools": {
  "en": "Tools",
  "fr": "Outils",
  "it": "Strumenti",
  "es": "Herramientas",
  "pt": "Ferramentas",
  "nl": "Hulpmiddelen",
  "pl": "Narzędzia",
  "tr": "Araçlar",
  "ru": "Инструменты"
 },
 "Use Cases": {
  "en": "Use cases",
  "fr": "Cas d'usage",
  "it": "Casi d'uso",
  "es": "Casos de uso",
  "pt": "Casos de uso",
  "nl": "Toepassingsgevallen",
  "pl": "Przypadki użycia",
  "tr": "Kullanım senaryoları",
  "ru": "Сценарии использования"
 },
 "Prozess": {
  "en": "Process",
  "fr": "Processus",
  "it": "Processo",
  "es": "Proceso",
  "pt": "Processo",
  "nl": "Proces",
  "pl": "Proces",
  "tr": "Süreç",
  "ru": "Процесс"
 },
 "Stil": {
  "en": "Style",
  "fr": "Style",
  "it": "Stile",
  "es": "Estilo",
  "pt": "Estilo",
  "nl": "Stijl",
  "pl": "Styl",
  "tr": "Üslup",
  "ru": "Стиль"
 },
 "Schritte": {
  "en": "Steps",
  "fr": "Étapes",
  "it": "Passaggi",
  "es": "Pasos",
  "pt": "Etapas",
  "nl": "Stappen",
  "pl": "Kroki",
  "tr": "Adımlar",
  "ru": "Шаги"
 },
 "Trigger": {
  "en": "Triggers",
  "fr": "Déclencheurs",
  "it": "Attivatori",
  "es": "Disparadores",
  "pt": "Acionadores",
  "nl": "Triggers",
  "pl": "Wyzwalacze",
  "tr": "Tetikleyiciler",
  "ru": "Триггеры"
 },
 "Risiko": {
  "en": "Risk",
  "fr": "Risque",
  "it": "Rischio",
  "es": "Riesgo",
  "pt": "Risco",
  "nl": "Risico",
  "pl": "Ryzyko",
  "tr": "Risk",
  "ru": "Риск"
 },
 "Relevanz": {
  "en": "Relevance",
  "fr": "Pertinence",
  "it": "Rilevanza",
  "es": "Relevancia",
  "pt": "Relevância",
  "nl": "Relevantie",
  "pl": "Istotność",
  "tr": "Alaka düzeyi",
  "ru": "Релевантность"
 },
 "Quelle": {
  "en": "Source",
  "fr": "Source",
  "it": "Fonte",
  "es": "Fuente",
  "pt": "Fonte",
  "nl": "Bron",
  "pl": "Źródło",
  "tr": "Kaynak",
  "ru": "Источник"
 },
 "Zeitraum": {
  "en": "Time range",
  "fr": "Période",
  "it": "Intervallo temporale",
  "es": "Período",
  "pt": "Período",
  "nl": "Periode",
  "pl": "Okres",
  "tr": "Zaman aralığı",
  "ru": "Период"
 },
 "Treffergenauigkeit": {
  "en": "Match accuracy",
  "fr": "Précision des résultats",
  "it": "Precisione dei risultati",
  "es": "Precisión de coincidencia",
  "pt": "Precisão dos resultados",
  "nl": "Trefzekerheid",
  "pl": "Trafność dopasowania",
  "tr": "Eşleşme doğruluğu",
  "ru": "Точность совпадений"
 },
 "Ziel": {
  "en": "Goal",
  "fr": "Objectif",
  "it": "Obiettivo",
  "es": "Objetivo",
  "pt": "Objetivo",
  "nl": "Doel",
  "pl": "Cel",
  "tr": "Hedef",
  "ru": "Цель"
 },
 "Umsetzbarkeit": {
  "en": "Feasibility",
  "fr": "Faisabilité",
  "it": "Fattibilità",
  "es": "Viabilidad",
  "pt": "Viabilidade",
  "nl": "Haalbaarheid",
  "pl": "Wykonalność",
  "tr": "Uygulanabilirlik",
  "ru": "Реализуемость"
 },
 "Fachbereich": {
  "en": "Specialist department",
  "fr": "Service métier",
  "it": "Reparto specialistico",
  "es": "Departamento especializado",
  "pt": "Departamento especializado",
  "nl": "Vakafdeling",
  "pl": "Dział merytoryczny",
  "tr": "Uzmanlık birimi",
  "ru": "Профильный отдел"
 },
 "Strategie": {
  "en": "Strategy",
  "fr": "Stratégie",
  "it": "Strategia",
  "es": "Estrategia",
  "pt": "Estratégia",
  "nl": "Strategie",
  "pl": "Strategia",
  "tr": "Strateji",
  "ru": "Стратегия"
 },
 "Einkauf": {
  "en": "Procurement",
  "fr": "Achats",
  "it": "Acquisti",
  "es": "Compras",
  "pt": "Compras",
  "nl": "Inkoop",
  "pl": "Zakupy",
  "tr": "Satın alma",
  "ru": "Закупки"
 },
 "Projektteam": {
  "en": "Project team",
  "fr": "Équipe projet",
  "it": "Team di progetto",
  "es": "Equipo de proyecto",
  "pt": "Equipa de projeto",
  "nl": "Projectteam",
  "pl": "Zespół projektowy",
  "tr": "Proje ekibi",
  "ru": "Проектная команда"
 },
 "Kunde": {
  "en": "Customer",
  "fr": "Client",
  "it": "Cliente",
  "es": "Cliente",
  "pt": "Cliente",
  "nl": "Klant",
  "pl": "Klient",
  "tr": "Müşteri",
  "ru": "Клиент"
 },
 "intern": {
  "en": "Internal team",
  "fr": "Équipe interne",
  "it": "Team interno",
  "es": "Equipo interno",
  "pt": "Equipa interna",
  "nl": "Intern team",
  "pl": "Zespół wewnętrzny",
  "tr": "İç ekip",
  "ru": "Внутренняя команда"
 },
 "Projektleitung": {
  "en": "Project management",
  "fr": "Direction de projet",
  "it": "Direzione di progetto",
  "es": "Dirección de proyecto",
  "pt": "Gestão de projeto",
  "nl": "Projectleiding",
  "pl": "Kierownictwo projektu",
  "tr": "Proje yönetimi",
  "ru": "Руководство проекта"
 },
 "Controlling": {
  "en": "Controlling",
  "fr": "Contrôle de gestion",
  "it": "Controllo di gestione",
  "es": "Control de gestión",
  "pt": "Controlo de gestão",
  "nl": "Controlling",
  "pl": "Kontroling",
  "tr": "Finansal kontrol",
  "ru": "Управленческий учёт"
 },
 "IT": {
  "en": "IT",
  "fr": "Informatique",
  "it": "IT",
  "es": "TI",
  "pt": "TI",
  "nl": "IT",
  "pl": "IT",
  "tr": "BT",
  "ru": "ИТ"
 },
 "Entwicklung": {
  "en": "Development",
  "fr": "Développement",
  "it": "Sviluppo",
  "es": "Desarrollo",
  "pt": "Desenvolvimento",
  "nl": "Ontwikkeling",
  "pl": "Rozwój",
  "tr": "Geliştirme",
  "ru": "Разработка"
 },
 "Technische Fachrolle": {
  "en": "Technical specialist",
  "fr": "Spécialiste technique",
  "it": "Specialista tecnico",
  "es": "Especialista técnico",
  "pt": "Especialista técnico",
  "nl": "Technisch specialist",
  "pl": "Specjalista techniczny",
  "tr": "Teknik uzman",
  "ru": "Технический специалист"
 },
 "Agent-Owner": {
  "en": "Agent owner",
  "fr": "Responsable de l'agent",
  "it": "Responsabile dell'agente",
  "es": "Responsable del agente",
  "pt": "Responsável pelo agente",
  "nl": "Agentbeheerder",
  "pl": "Właściciel agenta",
  "tr": "Ajan sorumlusu",
  "ru": "Владелец агента"
 },
 "Produktteam": {
  "en": "Product team",
  "fr": "Équipe produit",
  "it": "Team di prodotto",
  "es": "Equipo de producto",
  "pt": "Equipa de produto",
  "nl": "Productteam",
  "pl": "Zespół produktowy",
  "tr": "Ürün ekibi",
  "ru": "Команда продукта"
 },
 "Marketing": {
  "en": "Marketing",
  "fr": "Marketing",
  "it": "Marketing",
  "es": "Marketing",
  "pt": "Marketing",
  "nl": "Marketing",
  "pl": "Marketing",
  "tr": "Pazarlama",
  "ru": "Маркетинг"
 },
 "Prozessmanagement": {
  "en": "Process management",
  "fr": "Gestion des processus",
  "it": "Gestione dei processi",
  "es": "Gestión de procesos",
  "pt": "Gestão de processos",
  "nl": "Procesmanagement",
  "pl": "Zarządzanie procesami",
  "tr": "Süreç yönetimi",
  "ru": "Управление процессами"
 },
 "Mitarbeitende": {
  "en": "Employees",
  "fr": "Collaborateurs",
  "it": "Dipendenti",
  "es": "Empleados",
  "pt": "Colaboradores",
  "nl": "Medewerkers",
  "pl": "Pracownicy",
  "tr": "Çalışanlar",
  "ru": "Сотрудники"
 },
 "Abhängigkeiten": {
  "en": "Dependencies",
  "fr": "Dépendances",
  "it": "Dipendenze",
  "es": "Dependencias",
  "pt": "Dependências",
  "nl": "Afhankelijkheden",
  "pl": "Zależności",
  "tr": "Bağımlılıklar",
  "ru": "Зависимости"
 },
 "Abweichungen": {
  "en": "Deviations",
  "fr": "Écarts",
  "it": "Scostamenti",
  "es": "Desviaciones",
  "pt": "Desvios",
  "nl": "Afwijkingen",
  "pl": "Odchylenia",
  "tr": "Sapmalar",
  "ru": "Отклонения"
 },
 "Aktualität": {
  "en": "Recency",
  "fr": "Actualité",
  "it": "Attualità",
  "es": "Actualidad",
  "pt": "Atualidade",
  "nl": "Actualiteit",
  "pl": "Aktualność",
  "tr": "Güncellik",
  "ru": "Актуальность"
 },
 "Annahmen": {
  "en": "Assumptions",
  "fr": "Hypothèses",
  "it": "Ipotesi",
  "es": "Suposiciones",
  "pt": "Pressupostos",
  "nl": "Aannames",
  "pl": "Założenia",
  "tr": "Varsayımlar",
  "ru": "Допущения"
 },
 "Aufgaben": {
  "en": "Tasks",
  "fr": "Tâches",
  "it": "Attività",
  "es": "Tareas",
  "pt": "Tarefas",
  "nl": "Taken",
  "pl": "Zadania",
  "tr": "Görevler",
  "ru": "Задачи"
 },
 "Bedingungen": {
  "en": "Conditions",
  "fr": "Conditions",
  "it": "Condizioni",
  "es": "Condiciones",
  "pt": "Condições",
  "nl": "Voorwaarden",
  "pl": "Warunki",
  "tr": "Koşullar",
  "ru": "Условия"
 },
 "Belege": {
  "en": "Supporting evidence",
  "fr": "Justificatifs",
  "it": "Prove documentali",
  "es": "Comprobantes",
  "pt": "Comprovativos",
  "nl": "Onderbouwing",
  "pl": "Dowody",
  "tr": "Kanıtlayıcı belgeler",
  "ru": "Подтверждающие документы"
 },
 "Berechtigungen": {
  "en": "Permissions",
  "fr": "Autorisations",
  "it": "Autorizzazioni",
  "es": "Permisos",
  "pt": "Permissões",
  "nl": "Rechten",
  "pl": "Uprawnienia",
  "tr": "İzinler",
  "ru": "Разрешения"
 },
 "Bestätigung": {
  "en": "Confirmation",
  "fr": "Confirmation",
  "it": "Conferma",
  "es": "Confirmación",
  "pt": "Confirmação",
  "nl": "Bevestiging",
  "pl": "Potwierdzenie",
  "tr": "Onay",
  "ru": "Подтверждение"
 },
 "Betroffene Assets": {
  "en": "Affected assets",
  "fr": "Actifs concernés",
  "it": "Risorse interessate",
  "es": "Activos afectados",
  "pt": "Ativos afetados",
  "nl": "Betrokken bedrijfsmiddelen",
  "pl": "Zasoby objęte zmianą",
  "tr": "Etkilenen varlıklar",
  "ru": "Затронутые активы"
 },
 "Call-to-Action": {
  "en": "Call to action",
  "fr": "Appel à l’action",
  "it": "Invito all’azione",
  "es": "Llamada a la acción",
  "pt": "Chamada para ação",
  "nl": "Oproep tot actie",
  "pl": "Wezwanie do działania",
  "tr": "Eylem çağrısı",
  "ru": "Призыв к действию"
 },
 "Daten": {
  "en": "Data",
  "fr": "Données",
  "it": "Dati",
  "es": "Datos",
  "pt": "Dados",
  "nl": "Gegevens",
  "pl": "Dane",
  "tr": "Veriler",
  "ru": "Данные"
 },
 "Datenqualität": {
  "en": "Data quality",
  "fr": "Qualité des données",
  "it": "Qualità dei dati",
  "es": "Calidad de datos",
  "pt": "Qualidade dos dados",
  "nl": "Datakwaliteit",
  "pl": "Jakość danych",
  "tr": "Veri kalitesi",
  "ru": "Качество данных"
 },
 "Doppelverarbeitung": {
  "en": "Duplicate processing",
  "fr": "Traitement en double",
  "it": "Elaborazione duplicata",
  "es": "Procesamiento duplicado",
  "pt": "Processamento duplicado",
  "nl": "Dubbele verwerking",
  "pl": "Podwójne przetwarzanie",
  "tr": "Yinelenen işleme",
  "ru": "Дублирующая обработка"
 },
 "Empfehlung": {
  "en": "Recommendation",
  "fr": "Recommandation",
  "it": "Raccomandazione",
  "es": "Recomendación",
  "pt": "Recomendação",
  "nl": "Aanbeveling",
  "pl": "Rekomendacja",
  "tr": "Öneri",
  "ru": "Рекомендация"
 },
 "Entscheidungen": {
  "en": "Decisions",
  "fr": "Décisions",
  "it": "Decisioni",
  "es": "Decisiones",
  "pt": "Decisões",
  "nl": "Besluiten",
  "pl": "Decyzje",
  "tr": "Kararlar",
  "ru": "Решения"
 },
 "Erfolgskriterium": {
  "en": "Success criterion",
  "fr": "Critère de réussite",
  "it": "Criterio di successo",
  "es": "Criterio de éxito",
  "pt": "Critério de sucesso",
  "nl": "Succescriterium",
  "pl": "Kryterium sukcesu",
  "tr": "Başarı ölçütü",
  "ru": "Критерий успеха"
 },
 "Evidenz": {
  "en": "Evidence",
  "fr": "Éléments probants",
  "it": "Evidenze",
  "es": "Evidencia",
  "pt": "Evidências",
  "nl": "Bewijsmateriaal",
  "pl": "Materiał dowodowy",
  "tr": "Kanıtlar",
  "ru": "Доказательства"
 },
 "Fehlerbehandlung": {
  "en": "Error handling",
  "fr": "Gestion des erreurs",
  "it": "Gestione degli errori",
  "es": "Gestión de errores",
  "pt": "Tratamento de erros",
  "nl": "Foutafhandeling",
  "pl": "Obsługa błędów",
  "tr": "Hata işleme",
  "ru": "Обработка ошибок"
 },
 "Fehlerfälle": {
  "en": "Failure cases",
  "fr": "Cas d’erreur",
  "it": "Casi di errore",
  "es": "Casos de error",
  "pt": "Casos de erro",
  "nl": "Foutscenario’s",
  "pl": "Scenariusze błędów",
  "tr": "Hata durumları",
  "ru": "Сценарии ошибок"
 },
 "Format": {
  "en": "Format",
  "fr": "Format",
  "it": "Formato",
  "es": "Formato",
  "pt": "Formato",
  "nl": "Formaat",
  "pl": "Format",
  "tr": "Biçim",
  "ru": "Формат"
 },
 "Fristen": {
  "en": "Deadlines",
  "fr": "Échéances",
  "it": "Scadenze",
  "es": "Plazos",
  "pt": "Prazos",
  "nl": "Termijnen",
  "pl": "Terminy",
  "tr": "Son tarihler",
  "ru": "Сроки"
 },
 "Grenzen": {
  "en": "Limits",
  "fr": "Limites",
  "it": "Limiti",
  "es": "Límites",
  "pt": "Limites",
  "nl": "Grenzen",
  "pl": "Ograniczenia",
  "tr": "Sınırlar",
  "ru": "Ограничения"
 },
 "Handlungsbedarf": {
  "en": "Required action",
  "fr": "Actions nécessaires",
  "it": "Azioni necessarie",
  "es": "Acciones necesarias",
  "pt": "Ações necessárias",
  "nl": "Benodigde acties",
  "pl": "Wymagane działania",
  "tr": "Gerekli eylemler",
  "ru": "Необходимые действия"
 },
 "Kennzahlen": {
  "en": "Key metrics",
  "fr": "Indicateurs clés",
  "it": "Indicatori chiave",
  "es": "Indicadores clave",
  "pt": "Indicadores-chave",
  "nl": "Kerncijfers",
  "pl": "Kluczowe wskaźniki",
  "tr": "Temel göstergeler",
  "ru": "Ключевые показатели"
 },
 "Kernaussage": {
  "en": "Key message",
  "fr": "Message clé",
  "it": "Messaggio chiave",
  "es": "Mensaje clave",
  "pt": "Mensagem principal",
  "nl": "Kernboodschap",
  "pl": "Główne przesłanie",
  "tr": "Ana mesaj",
  "ru": "Основная мысль"
 },
 "Kernaussagen": {
  "en": "Key points",
  "fr": "Points essentiels",
  "it": "Punti chiave",
  "es": "Puntos clave",
  "pt": "Pontos principais",
  "nl": "Kernpunten",
  "pl": "Najważniejsze punkty",
  "tr": "Temel noktalar",
  "ru": "Ключевые тезисы"
 },
 "Korrektheit": {
  "en": "Correctness",
  "fr": "Exactitude",
  "it": "Correttezza",
  "es": "Corrección",
  "pt": "Correção",
  "nl": "Juistheid",
  "pl": "Poprawność",
  "tr": "Doğruluk",
  "ru": "Корректность"
 },
 "Kosten / Auswirkungen": {
  "en": "Costs and impacts",
  "fr": "Coûts et effets",
  "it": "Costi e impatti",
  "es": "Costes e impactos",
  "pt": "Custos e impactos",
  "nl": "Kosten en gevolgen",
  "pl": "Koszty i skutki",
  "tr": "Maliyetler ve etkiler",
  "ru": "Затраты и последствия"
 },
 "Kriterien": {
  "en": "Criteria",
  "fr": "Critères",
  "it": "Criteri",
  "es": "Criterios",
  "pt": "Critérios",
  "nl": "Criteria",
  "pl": "Kryteria",
  "tr": "Ölçütler",
  "ru": "Критерии"
 },
 "Kürze": {
  "en": "Brevity",
  "fr": "Concision",
  "it": "Concisione",
  "es": "Brevedad",
  "pt": "Concisão",
  "nl": "Beknoptheid",
  "pl": "Zwięzłość",
  "tr": "Kısalık",
  "ru": "Краткость"
 },
 "Lern- / Entwicklungsschritt": {
  "en": "Learning or development step",
  "fr": "Étape d’apprentissage ou de développement",
  "it": "Fase di apprendimento o sviluppo",
  "es": "Paso de aprendizaje o desarrollo",
  "pt": "Etapa de aprendizagem ou desenvolvimento",
  "nl": "Leer- of ontwikkelstap",
  "pl": "Etap nauki lub rozwoju",
  "tr": "Öğrenme veya gelişim adımı",
  "ru": "Этап обучения или развития"
 },
 "Meilensteine": {
  "en": "Milestones",
  "fr": "Jalons",
  "it": "Traguardi",
  "es": "Hitos",
  "pt": "Marcos",
  "nl": "Mijlpalen",
  "pl": "Kamienie milowe",
  "tr": "Kilometre taşları",
  "ru": "Контрольные этапы"
 },
 "Priorität": {
  "en": "Priority",
  "fr": "Priorité",
  "it": "Priorità",
  "es": "Prioridad",
  "pt": "Prioridade",
  "nl": "Prioriteit",
  "pl": "Priorytet",
  "tr": "Öncelik",
  "ru": "Приоритет"
 },
 "Risiken": {
  "en": "Risks",
  "fr": "Risques",
  "it": "Rischi",
  "es": "Riesgos",
  "pt": "Riscos",
  "nl": "Risico’s",
  "pl": "Ryzyka",
  "tr": "Riskler",
  "ru": "Риски"
 }
}


# Exact task intentions reviewed against the 16 unchanged Free contracts.
# These preserve task-specific requirements beyond the translated task title.
FREE_INTENTS = {
 "chat_sum": {
  "en": "Summarize the supplied content precisely, highlighting the key statements, decisions, unresolved issues and next steps relevant to the stated objective.",
  "fr": "Résumez précisément le contenu fourni en soulignant les points clés, décisions, questions ouvertes et prochaines étapes pertinentes pour l'objectif.",
  "it": "Riassumi con precisione i contenuti forniti, evidenziando punti chiave, decisioni, questioni aperte e prossimi passi pertinenti all'obiettivo.",
  "es": "Resume con precisión el contenido proporcionado, destacando ideas clave, decisiones, asuntos pendientes y próximos pasos pertinentes para el objetivo.",
  "pt": "Resuma com precisão os conteúdos fornecidos, salientando pontos essenciais, decisões, questões pendentes e próximos passos relevantes para o objetivo.",
  "nl": "Vat de aangeleverde inhoud nauwkeurig samen en benadruk kernpunten, besluiten, openstaande zaken en vervolgstappen die voor het doel relevant zijn.",
  "pl": "Precyzyjnie podsumuj przekazaną treść, wskazując kluczowe ustalenia, decyzje, otwarte kwestie i kolejne kroki istotne dla celu.",
  "tr": "Verilen içeriği doğru biçimde özetleyin; hedefe uygun temel noktaları, kararları, açık konuları ve sonraki adımları vurgulayın.",
  "ru": "Точно изложите предоставленный материал, выделив ключевые положения, решения, открытые вопросы и следующие шаги, важные для цели."
 },
 "chat_write": {
  "en": "Create a directly usable business text from the provided instructions with a clear main message, logical structure and professional tone.",
  "fr": "Rédigez à partir des consignes fournies un texte professionnel immédiatement utilisable, avec un message central clair, une structure logique et un ton adapté.",
  "it": "Crea un testo aziendale subito utilizzabile dalle indicazioni fornite, con messaggio chiave chiaro, struttura logica e tono professionale.",
  "es": "Redacta un texto empresarial directamente utilizable a partir de las indicaciones, con mensaje central claro, estructura lógica y tono profesional.",
  "pt": "Crie um texto empresarial diretamente utilizável a partir das indicações, com mensagem central clara, estrutura lógica e tom profissional.",
  "nl": "Stel op basis van de instructies een direct bruikbare zakelijke tekst op met een duidelijke kernboodschap, logische structuur en professionele toon.",
  "pl": "Na podstawie wskazówek przygotuj gotowy do użycia tekst biznesowy z jasnym przekazem, logiczną strukturą i profesjonalnym tonem.",
  "tr": "Verilen yönergelerden açık ana mesajı, mantıklı yapısı ve profesyonel üslubu olan doğrudan kullanılabilir bir iş metni hazırlayın.",
  "ru": "Подготовьте по предоставленным указаниям готовый деловой текст с ясной основной мыслью, логичной структурой и профессиональным тоном."
 },
 "out_reply": {
  "en": "Draft a send-ready reply to the currently open or clearly selected email. Identify exactly what the sender asks, states or expects and address each point directly.",
  "fr": "Rédigez une réponse prête à envoyer au courriel ouvert ou clairement sélectionné. Repérez exactement les questions, informations et attentes de l'expéditeur et répondez point par point.",
  "it": "Prepara una risposta pronta da inviare all'e-mail aperta o selezionata. Individua domande, comunicazioni e aspettative del mittente e rispondi puntualmente.",
  "es": "Prepara una respuesta lista para enviar al correo abierto o seleccionado. Identifica exactamente preguntas, información y expectativas del remitente y responde a cada punto.",
  "pt": "Prepare uma resposta pronta a enviar ao e-mail aberto ou selecionado. Identifique perguntas, informações e expectativas do remetente e responda a cada ponto.",
  "nl": "Stel een verzendklaar antwoord op de geopende of geselecteerde e-mail op. Bepaal wat de afzender vraagt, meldt of verwacht en behandel ieder punt.",
  "pl": "Przygotuj gotową do wysłania odpowiedź na otwarty lub wybrany e-mail. Ustal pytania, informacje i oczekiwania nadawcy i odpowiedz na każdy punkt.",
  "tr": "Açık veya seçili e-postaya gönderilmeye hazır bir yanıt hazırlayın. Gönderenin sorularını, bildirimlerini ve beklentilerini belirleyip her birine doğrudan yanıt verin.",
  "ru": "Подготовьте готовый к отправке ответ на открытое или выбранное письмо. Определите вопросы, сведения и ожидания отправителя и ответьте по каждому пункту."
 },
 "out_improve": {
  "en": "Revise the open or supplied email draft so its meaning, facts and commitments are preserved while the text becomes clearer, more precise, professional and easier to scan.",
  "fr": "Révisez le brouillon d'e-mail ouvert ou fourni en conservant le sens, les faits et les engagements, tout en améliorant clarté, précision et lisibilité.",
  "it": "Rivedi la bozza e-mail aperta o fornita conservando significato, fatti e impegni e rendendo il testo più chiaro, preciso, professionale e leggibile.",
  "es": "Revisa el borrador de correo abierto o facilitado conservando significado, hechos y compromisos, pero mejorando claridad, precisión y legibilidad.",
  "pt": "Reveja o rascunho de e-mail aberto ou fornecido, preservando sentido, factos e compromissos e melhorando clareza, precisão e legibilidade.",
  "nl": "Herzie de geopende of aangeleverde e-mail zonder betekenis, feiten of toezeggingen te wijzigen. Maak de tekst duidelijker, nauwkeuriger en beter leesbaar.",
  "pl": "Popraw otwartą lub przekazaną wersję e-maila, zachowując sens, fakty i zobowiązania, ale zwiększając jasność, precyzję i czytelność.",
  "tr": "Açık veya sağlanan e-posta taslağını anlamı, olguları ve taahhütleri koruyarak daha açık, kesin, profesyonel ve okunabilir hâle getirin.",
  "ru": "Переработайте открытый или предоставленный черновик письма, сохранив смысл, факты и обязательства, но повысив ясность, точность и читаемость."
 },
 "out_cal_next": {
  "en": "Find the next future appointment in the available Outlook calendar matching the specified search criterion and clearly report the relevant appointment details.",
  "fr": "Trouvez dans le calendrier Outlook accessible le prochain rendez-vous futur correspondant au critère indiqué et communiquez clairement les détails pertinents.",
  "it": "Trova nel calendario Outlook disponibile il prossimo appuntamento futuro che corrisponde al criterio indicato e riportane chiaramente i dettagli.",
  "es": "Busca en el calendario de Outlook disponible la próxima cita futura que cumpla el criterio indicado y presenta claramente los detalles relevantes.",
  "pt": "Encontre no calendário Outlook disponível o próximo compromisso futuro que corresponde ao critério indicado e apresente claramente os detalhes.",
  "nl": "Zoek in de beschikbare Outlook-agenda de eerstvolgende afspraak die aan het opgegeven criterium voldoet en vermeld de relevante gegevens.",
  "pl": "Znajdź w dostępnym kalendarzu Outlook najbliższe przyszłe spotkanie spełniające kryterium i jasno podaj szczegóły.",
  "tr": "Mevcut Outlook takviminde belirtilen arama ölçütüne uyan bir sonraki randevuyu bulun ve ilgili ayrıntıları açıkça belirtin.",
  "ru": "Найдите в доступном календаре Outlook ближайшую будущую встречу, отвечающую заданному критерию, и ясно укажите сведения о ней."
 },
 "out_cal_schedule": {
  "en": "Prepare a specific Outlook appointment from the stated scheduling requirements, taking into account purpose, attendees, time window, duration and any visible conflicts or limitations.",
  "fr": "Préparez un rendez-vous Outlook concret à partir des exigences, en tenant compte de l'objectif, des participants, de la période, de la durée et des conflits visibles.",
  "it": "Prepara un appuntamento Outlook concreto in base ai requisiti indicati, considerando scopo, partecipanti, fascia oraria, durata e conflitti visibili.",
  "es": "Prepara una cita concreta de Outlook según los requisitos, considerando objetivo, asistentes, franja horaria, duración y posibles conflictos.",
  "pt": "Prepare um compromisso Outlook concreto segundo os requisitos, considerando objetivo, participantes, período, duração e conflitos identificados.",
  "nl": "Bereid een concrete Outlook-afspraak voor op basis van de eisen, inclusief doel, deelnemers, tijdvenster, duur en zichtbare conflicten.",
  "pl": "Przygotuj konkretne spotkanie w Outlook według wymagań, uwzględniając cel, uczestników, czas, długość i widoczne konflikty.",
  "tr": "Belirtilen planlama gereksinimlerine göre amaç, katılımcılar, zaman aralığı, süre ve görünen çakışmaları dikkate alarak Outlook randevusu hazırlayın.",
  "ru": "Подготовьте конкретную встречу Outlook по заданным требованиям, учитывая цель, участников, интервал, длительность и известные конфликты."
 },
 "out_todo_create": {
  "en": "Create an action-oriented task list from the stated topic or case and derive only next steps that are justified by the information actually available.",
  "fr": "Créez une liste de tâches concrètes à partir du sujet ou dossier indiqué et ne déduisez que des étapes justifiées par les informations disponibles.",
  "it": "Crea un elenco operativo di attività dal tema o caso indicato e ricava soltanto passi successivi giustificati dalle informazioni disponibili.",
  "es": "Crea una lista práctica de tareas a partir del asunto indicado y propone solo pasos siguientes justificados por la información disponible.",
  "pt": "Crie uma lista prática de tarefas a partir do assunto indicado e derive apenas passos seguintes justificados pela informação disponível.",
  "nl": "Maak een actiegerichte takenlijst op basis van het onderwerp en leid alleen vervolgstappen af die door beschikbare informatie worden ondersteund.",
  "pl": "Na podstawie wskazanego tematu przygotuj zadania do wykonania i wyprowadź tylko kroki uzasadnione dostępnymi informacjami.",
  "tr": "Belirtilen konu veya olaydan eyleme dönük görev listesi oluşturun; yalnızca mevcut bilgilerle gerekçelendirilen sonraki adımları önerin.",
  "ru": "Составьте практический список задач по указанной теме и предложите только те дальнейшие шаги, которые подтверждены доступными сведениями."
 },
 "out_todo_prioritize": {
  "en": "Prioritize only the specified tasks by urgency, business impact, due dates and visible dependencies, and explain the resulting order clearly.",
  "fr": "Classez uniquement les tâches indiquées selon l'urgence, l'impact métier, les échéances et les dépendances constatées, et expliquez clairement l'ordre.",
  "it": "Dai priorità solo alle attività indicate secondo urgenza, impatto aziendale, scadenze e dipendenze note, spiegando chiaramente l'ordine.",
  "es": "Prioriza solo las tareas indicadas según urgencia, impacto empresarial, fechas límite y dependencias visibles; explica claramente el orden.",
  "pt": "Priorize apenas as tarefas indicadas por urgência, impacto empresarial, prazos e dependências visíveis, justificando claramente a ordem.",
  "nl": "Prioriteer uitsluitend de opgegeven taken op urgentie, zakelijke impact, deadlines en bekende afhankelijkheden en licht de volgorde toe.",
  "pl": "Nadaj priorytety tylko wskazanym zadaniom według pilności, wpływu biznesowego, terminów i znanych zależności, uzasadniając kolejność.",
  "tr": "Yalnızca belirtilen görevleri aciliyet, iş etkisi, son tarihler ve bilinen bağımlılıklara göre önceliklendirin; sıralamayı açıklayın.",
  "ru": "Расставьте приоритеты только для указанных задач по срочности, деловому влиянию, срокам и известным зависимостям; объясните порядок."
 },
 "teams_notes": {
  "en": "Create a reliable meeting follow-up from the supplied notes and clearly separate status updates, decisions, tasks, owners, dates and outstanding issues.",
  "fr": "Rédigez un compte rendu fiable à partir des notes de réunion, en distinguant clairement état d'avancement, décisions, tâches, responsables, dates et questions ouvertes.",
  "it": "Prepara un resoconto affidabile dalle note della riunione, distinguendo stato, decisioni, attività, responsabili, date e questioni aperte.",
  "es": "Elabora un seguimiento fiable de las notas de reunión separando estados, decisiones, tareas, responsables, fechas y asuntos pendientes.",
  "pt": "Prepare um seguimento fiável das notas da reunião, separando estados, decisões, tarefas, responsáveis, datas e questões pendentes.",
  "nl": "Maak een betrouwbare vergaderopvolging van de aangeleverde notities en scheid status, besluiten, taken, verantwoordelijken, datums en openstaande punten.",
  "pl": "Przygotuj rzetelne podsumowanie z notatek spotkania, wyraźnie rozdzielając status, decyzje, zadania, osoby odpowiedzialne, terminy i kwestie otwarte.",
  "tr": "Verilen toplantı notlarından güvenilir bir takip özeti hazırlayın; durumları, kararları, görevleri, sorumluları, tarihleri ve açık konuları ayırın.",
  "ru": "Подготовьте достоверные итоги по заметкам встречи, отдельно указав состояние, решения, задачи, ответственных, даты и открытые вопросы."
 },
 "teams_chat": {
  "en": "Summarize the supplied or clearly referenced Teams chat so that its progression, outcomes, decisions, open questions and next steps are understandable without rereading it.",
  "fr": "Résumez le chat Teams fourni ou explicitement cité pour rendre compréhensibles le déroulement, les résultats, les décisions, les questions ouvertes et les suites sans relire les échanges.",
  "it": "Riassumi la chat Teams fornita o chiaramente indicata in modo che svolgimento, risultati, decisioni, questioni aperte e prossimi passi siano comprensibili senza rileggerla.",
  "es": "Resume el chat de Teams facilitado o claramente referido para entender secuencia, resultados, decisiones, preguntas abiertas y pasos siguientes sin releerlo.",
  "pt": "Resuma a conversa Teams fornecida ou claramente referida para compreender sequência, resultados, decisões, questões abertas e passos seguintes sem reler.",
  "nl": "Vat de aangeleverde of duidelijk genoemde Teams-chat samen zodat verloop, resultaten, besluiten, open vragen en vervolgstappen zonder herlezen begrijpelijk zijn.",
  "pl": "Podsumuj podany lub wyraźnie wskazany czat Teams tak, aby przebieg, wyniki, decyzje, pytania otwarte i kolejne kroki były jasne bez ponownego czytania.",
  "tr": "Sağlanan veya açıkça belirtilen Teams sohbetini, akış, sonuçlar, kararlar, açık sorular ve sonraki adımlar yeniden okumadan anlaşılacak şekilde özetleyin.",
  "ru": "Суммируйте предоставленный или явно указанный чат Teams так, чтобы ход беседы, результаты, решения, вопросы и дальнейшие шаги были понятны без перечитывания."
 },
 "word_rewrite": {
  "en": "Revise the selected or supplied Word text for clarity, structure and linguistic precision without unintentionally changing technical statements, numbers, names or binding content.",
  "fr": "Améliorez la clarté, la structure et la précision du texte Word sélectionné ou fourni sans modifier involontairement les faits techniques, chiffres, noms ou engagements.",
  "it": "Rivedi il testo Word selezionato o fornito per chiarezza, struttura e precisione senza alterare involontariamente affermazioni tecniche, numeri, nomi o impegni.",
  "es": "Revisa el texto de Word seleccionado o proporcionado para mejorar claridad, estructura y precisión sin cambiar por accidente datos técnicos, cifras, nombres ni compromisos.",
  "pt": "Reveja o texto Word selecionado ou fornecido para melhorar clareza, estrutura e precisão sem alterar involuntariamente factos técnicos, números, nomes ou compromissos.",
  "nl": "Herzie de geselecteerde of aangeleverde Word-tekst op duidelijkheid, structuur en nauwkeurigheid zonder technische uitspraken, cijfers, namen of toezeggingen onbedoeld te wijzigen.",
  "pl": "Popraw wybrany lub przekazany tekst Word pod kątem jasności, struktury i precyzji, bez niezamierzonych zmian treści technicznej, liczb, nazw czy zobowiązań.",
  "tr": "Seçilen veya sağlanan Word metnini teknik ifadeleri, sayıları, isimleri ya da bağlayıcı bilgileri istemeden değiştirmeden açıklık, yapı ve dilsel kesinlik açısından iyileştirin.",
  "ru": "Улучшите ясность, структуру и точность выбранного текста Word, не изменяя непреднамеренно технические утверждения, числа, имена и обязательства."
 },
 "word_sum": {
  "en": "Summarize the open or supplied Word document so its key content, figures, dates, decisions, risks and unresolved items can be understood without rereading the document.",
  "fr": "Résumez le document Word ouvert ou fourni de sorte que les points essentiels, chiffres, dates, décisions, risques et questions ouvertes soient clairs sans le relire.",
  "it": "Riassumi il documento Word aperto o fornito per rendere comprensibili contenuti, cifre, date, decisioni, rischi e punti aperti senza rileggerlo.",
  "es": "Resume el documento Word abierto o facilitado para comprender contenido clave, cifras, fechas, decisiones, riesgos y pendientes sin releerlo.",
  "pt": "Resuma o documento Word aberto ou fornecido para compreender conteúdo essencial, números, datas, decisões, riscos e questões abertas sem reler.",
  "nl": "Vat het geopende of aangeleverde Word-document samen zodat inhoud, cijfers, datums, besluiten, risico's en open punten zonder herlezen duidelijk zijn.",
  "pl": "Podsumuj otwarty lub dostarczony dokument Word, aby najważniejsze treści, liczby, terminy, decyzje, ryzyka i kwestie otwarte były jasne bez ponownego czytania.",
  "tr": "Açık veya sağlanan Word belgesini ana içerik, sayılar, tarihler, kararlar, riskler ve açık noktalar yeniden okumadan anlaşılacak şekilde özetleyin.",
  "ru": "Суммируйте открытый или предоставленный документ Word так, чтобы ключевые сведения, цифры, даты, решения, риски и открытые вопросы были понятны без перечитывания."
 },
 "excel_explain": {
  "en": "Analyze the open or supplied Excel table and explain the key visible metrics, patterns, relationships and anomalies clearly and on the basis of actual data.",
  "fr": "Analysez le tableau Excel ouvert ou fourni et expliquez clairement les indicateurs, tendances, liens et anomalies visibles sur la base des données disponibles.",
  "it": "Analizza la tabella Excel aperta o fornita e spiega chiaramente indicatori, schemi, relazioni e anomalie visibili sulla base dei dati reali.",
  "es": "Analiza la tabla de Excel abierta o facilitada y explica con claridad métricas, patrones, relaciones y anomalías visibles basándote en datos reales.",
  "pt": "Analise a tabela Excel aberta ou fornecida e explique claramente métricas, padrões, relações e anomalias visíveis com base em dados reais.",
  "nl": "Analyseer de geopende of aangeleverde Excel-tabel en leg zichtbare cijfers, patronen, verbanden en afwijkingen begrijpelijk uit op basis van echte gegevens.",
  "pl": "Przeanalizuj otwartą lub przekazaną tabelę Excel i jasno wyjaśnij wskaźniki, wzorce, zależności i odchylenia na podstawie faktycznych danych.",
  "tr": "Açık veya sağlanan Excel tablosunu analiz edin; görünen metrikleri, kalıpları, ilişkileri ve anormallikleri gerçek verilere dayanarak açıklayın.",
  "ru": "Проанализируйте открытую или предоставленную таблицу Excel и понятно объясните показатели, закономерности, связи и аномалии на основе реальных данных."
 },
 "excel_compare": {
  "en": "Compare the specified areas or values in the current Excel table systematically, show absolute and mathematically meaningful percentage changes, and distinguish observations from possible explanations.",
  "fr": "Comparez systématiquement les plages ou valeurs indiquées dans Excel, montrez les variations absolues et les pourcentages pertinents et distinguez résultats et explications possibles.",
  "it": "Confronta sistematicamente intervalli o valori indicati in Excel, mostra variazioni assolute e percentuali sensate e distingui dati da possibili spiegazioni.",
  "es": "Compara sistemáticamente rangos o valores indicados de Excel, muestra cambios absolutos y porcentuales cuando proceda y separa hallazgos de posibles explicaciones.",
  "pt": "Compare sistematicamente os intervalos ou valores indicados do Excel, apresente variações absolutas e percentuais pertinentes e distinga resultados de possíveis explicações.",
  "nl": "Vergelijk de opgegeven gebieden of waarden in Excel systematisch, toon absolute en zinvolle procentuele veranderingen en scheid bevindingen van mogelijke verklaringen.",
  "pl": "Porównaj wskazane obszary lub wartości w Excelu, pokaż zmiany bezwzględne i sensowne procentowe oraz oddziel wyniki od możliwych wyjaśnień.",
  "tr": "Excel'deki belirtilen aralık veya değerleri sistematik karşılaştırın; mutlak ve anlamlı yüzde değişimleri gösterin, gözlemleri olası açıklamalardan ayırın.",
  "ru": "Систематически сравните указанные области или значения Excel, покажите абсолютные и уместные процентные изменения и отделите факты от возможных объяснений."
 },
 "ppt_outline": {
  "en": "Create a clear PowerPoint outline from the presentation requirements, with a coherent storyline, meaningful slide titles and concise key messages.",
  "fr": "Élaborez un plan PowerPoint clair à partir du besoin, avec une progression logique, des titres de diapositives pertinents et des messages clés concis.",
  "it": "Crea una struttura PowerPoint chiara dalle esigenze, con storia logica, titoli significativi e messaggi chiave concisi.",
  "es": "Crea un esquema claro de PowerPoint según la presentación solicitada, con hilo argumental coherente, títulos significativos y mensajes clave concisos.",
  "pt": "Crie uma estrutura PowerPoint clara com base no pedido, com narrativa coerente, títulos de diapositivos relevantes e mensagens-chave concisas.",
  "nl": "Maak op basis van de presentatieopdracht een duidelijke PowerPoint-opzet met logisch verhaal, betekenisvolle diatitels en beknopte kernboodschappen.",
  "pl": "Na podstawie zadania opracuj przejrzysty plan PowerPoint z logiczną narracją, trafnymi tytułami slajdów i zwięzłymi przekazami.",
  "tr": "Sunum gereksinimlerinden tutarlı bir hikâye akışı, anlamlı slayt başlıkları ve kısa ana mesajlarla açık bir PowerPoint taslağı oluşturun.",
  "ru": "Составьте по заданию ясный план PowerPoint с логичной структурой, содержательными заголовками слайдов и краткими ключевыми тезисами."
 },
 "ppt_rewrite": {
  "en": "Revise the selected or supplied PowerPoint material so it is concise, easily understood on slides and suitable for presentation, without accidentally changing verified facts or binding statements.",
  "fr": "Révisez le contenu PowerPoint fourni pour qu'il soit concis, lisible sur les diapositives et adapté à la présentation, sans modifier les faits vérifiés ou engagements.",
  "it": "Rivedi il materiale PowerPoint selezionato affinché sia conciso e adatto alle slide, senza alterare fatti verificati o dichiarazioni vincolanti.",
  "es": "Revisa el contenido PowerPoint seleccionado para que sea breve, legible y apto para diapositivas sin cambiar datos comprobados ni compromisos.",
  "pt": "Reveja o conteúdo PowerPoint selecionado para ser conciso e adequado aos diapositivos sem alterar factos verificados nem compromissos.",
  "nl": "Herzie het geselecteerde PowerPoint-materiaal zodat het beknopt, snel leesbaar en geschikt voor dia's is, zonder geverifieerde feiten of toezeggingen te wijzigen.",
  "pl": "Popraw wybraną treść PowerPoint, by była zwięzła i czytelna na slajdach bez niezamierzonych zmian potwierdzonych faktów lub zobowiązań.",
  "tr": "Seçilen PowerPoint içeriğini doğrulanmış olguları ve bağlayıcı ifadeleri değiştirmeden slaytlarda hızla anlaşılır, kısa ve sunuma uygun hâle getirin.",
  "ru": "Переработайте выбранные материалы PowerPoint для краткости и читаемости на слайдах, не изменяя подтверждённые факты и обязательства."
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
    for match in re.finditer(r'^\s*Object\.assign\(TEXT,(\{[^\n]+\})\);$', source, flags=re.M):
        translations.update(json.loads(match.group(1)))
    return translations


def _translated(source: str, language: str) -> str:
    """No German fallback for generated foreign-language instructions."""
    if not source:
        return ''
    candidate = (_product_dictionary().get(source, {}).get(language)
                 or CHOICE_LABELS.get(source, {}).get(language)
                 or FOCUS_AUDIENCE_LABELS.get(source, {}).get(language))
    return str(candidate).strip() if candidate else ''


OUTPUT_CATEGORIES = {
 "email": {
  "en": "a ready-to-use email or message",
  "fr": "un e-mail ou message prêt à l'emploi",
  "it": "un'e-mail o un messaggio pronto all'uso",
  "es": "un correo o mensaje listo para usar",
  "pt": "um e-mail ou mensagem pronto a usar",
  "nl": "een direct bruikbare e-mail of bericht",
  "pl": "gotowy do użycia e-mail lub wiadomość",
  "tr": "kullanıma hazır e-posta veya ileti",
  "ru": "готовое к использованию письмо или сообщение"
 },
 "summary": {
  "en": "a focused, accurate summary",
  "fr": "une synthèse ciblée et fidèle",
  "it": "un riepilogo mirato e accurato",
  "es": "un resumen preciso y centrado",
  "pt": "um resumo preciso e focado",
  "nl": "een gerichte, nauwkeurige samenvatting",
  "pl": "zwięzłe i dokładne podsumowanie",
  "tr": "odaklı ve doğru bir özet",
  "ru": "точная и предметная сводка"
 },
 "report": {
  "en": "a structured professional report",
  "fr": "un rapport professionnel structuré",
  "it": "un rapporto professionale strutturato",
  "es": "un informe profesional estructurado",
  "pt": "um relatório profissional estruturado",
  "nl": "een gestructureerd professioneel rapport",
  "pl": "uporządkowany raport profesjonalny",
  "tr": "yapılandırılmış profesyonel rapor",
  "ru": "структурированный профессиональный отчёт"
 },
 "matrix": {
  "en": "a structured comparison matrix",
  "fr": "une matrice de comparaison structurée",
  "it": "una matrice di confronto strutturata",
  "es": "una matriz comparativa estructurada",
  "pt": "uma matriz comparativa estruturada",
  "nl": "een gestructureerde vergelijkingsmatrix",
  "pl": "uporządkowana macierz porównawcza",
  "tr": "yapılandırılmış karşılaştırma matrisi",
  "ru": "структурированная матрица сравнения"
 },
 "table": {
  "en": "a clearly labeled table",
  "fr": "un tableau clairement annoté",
  "it": "una tabella con intestazioni chiare",
  "es": "una tabla con encabezados claros",
  "pt": "uma tabela com cabeçalhos claros",
  "nl": "een duidelijk gelabelde tabel",
  "pl": "czytelna tabela z nagłówkami",
  "tr": "açık başlıklı bir tablo",
  "ru": "таблица с понятными заголовками"
 },
 "analysis": {
  "en": "a detailed, evidence-based analysis",
  "fr": "une analyse détaillée fondée sur les faits",
  "it": "un'analisi dettagliata basata sulle prove",
  "es": "un análisis detallado basado en datos",
  "pt": "uma análise detalhada baseada em evidências",
  "nl": "een gedetailleerde, onderbouwde analyse",
  "pl": "szczegółowa analiza oparta na faktach",
  "tr": "kanıta dayalı ayrıntılı analiz",
  "ru": "подробный анализ на основе фактов"
 },
 "plan": {
  "en": "an actionable step-by-step plan",
  "fr": "un plan d'action par étapes",
  "it": "un piano operativo passo dopo passo",
  "es": "un plan de acción paso a paso",
  "pt": "um plano de ação passo a passo",
  "nl": "een uitvoerbaar stappenplan",
  "pl": "wykonalny plan krok po kroku",
  "tr": "uygulanabilir adım adım plan",
  "ru": "практический пошаговый план"
 },
 "list": {
  "en": "a clearly organized, prioritized list",
  "fr": "une liste structurée et hiérarchisée",
  "it": "un elenco organizzato e prioritizzato",
  "es": "una lista organizada por prioridades",
  "pt": "uma lista organizada por prioridades",
  "nl": "een duidelijk geordende lijst met prioriteiten",
  "pl": "czytelna lista według priorytetów",
  "tr": "önceliklendirilmiş düzenli liste",
  "ru": "структурированный список по приоритетам"
 },
 "presentation": {
  "en": "an outline or slide content ready for presentation",
  "fr": "un plan ou contenu de diapositives prêt à présenter",
  "it": "una struttura o contenuto di slide pronto per la presentazione",
  "es": "un esquema o contenido de diapositivas listo para presentar",
  "pt": "um esquema ou conteúdo de diapositivos pronto para apresentar",
  "nl": "een presentatieopzet of direct bruikbare dia-inhoud",
  "pl": "układ lub treść slajdów gotowa do prezentacji",
  "tr": "sunuma hazır taslak veya slayt içeriği",
  "ru": "план или готовый материал для слайдов"
 },
 "code": {
  "en": "runnable code or an expression with a concise explanation",
  "fr": "du code exécutable ou une expression avec explication concise",
  "it": "codice eseguibile o un'espressione con breve spiegazione",
  "es": "código ejecutable o expresión con explicación breve",
  "pt": "código executável ou expressão com explicação breve",
  "nl": "uitvoerbare code of een expressie met korte uitleg",
  "pl": "działający kod lub wyrażenie z krótkim wyjaśnieniem",
  "tr": "kısa açıklamalı çalıştırılabilir kod veya ifade",
  "ru": "исполняемый код или выражение с кратким объяснением"
 },
 "workflow": {
  "en": "a clear workflow with triggers, steps and outcomes",
  "fr": "un flux de travail clair avec déclencheurs, étapes et résultats",
  "it": "un flusso di lavoro chiaro con trigger, passaggi e risultati",
  "es": "un flujo de trabajo claro con disparadores, pasos y resultados",
  "pt": "um fluxo de trabalho claro com acionadores, etapas e resultados",
  "nl": "een duidelijke workflow met triggers, stappen en resultaten",
  "pl": "jasny przepływ pracy z wyzwalaczami, krokami i wynikami",
  "tr": "tetikleyicileri, adımları ve sonuçları belirli iş akışı",
  "ru": "понятный процесс с триггерами, шагами и результатами"
 },
 "brief": {
  "en": "a concise decision-oriented briefing",
  "fr": "une note de synthèse concise pour la décision",
  "it": "un briefing conciso per le decisioni",
  "es": "un informe breve orientado a decisiones",
  "pt": "um briefing conciso para apoio à decisão",
  "nl": "een beknopte beslisgerichte briefing",
  "pl": "zwięzły briefing wspierający decyzję",
  "tr": "karar odaklı kısa bilgilendirme",
  "ru": "краткая справка для принятия решений"
 },
 "concept": {
  "en": "a concrete, structured solution concept",
  "fr": "un concept de solution concret et structuré",
  "it": "un concetto di soluzione concreto e strutturato",
  "es": "un concepto de solución concreto y estructurado",
  "pt": "um conceito de solução concreto e estruturado",
  "nl": "een concreet, gestructureerd oplossingsconcept",
  "pl": "konkretna koncepcja rozwiązania",
  "tr": "somut ve yapılandırılmış çözüm taslağı",
  "ru": "конкретная структурированная концепция решения"
 },
 "prompt": {
  "en": "a precise, immediately reusable prompt",
  "fr": "un prompt précis et directement réutilisable",
  "it": "un prompt preciso e subito riutilizzabile",
  "es": "un prompt preciso y reutilizable",
  "pt": "um prompt preciso e reutilizável",
  "nl": "een precieze, direct herbruikbare prompt",
  "pl": "precyzyjny prompt gotowy do użycia",
  "tr": "hemen kullanılabilir açık bir istem",
  "ru": "точный промпт, готовый к использованию"
 },
 "questionnaire": {
  "en": "a structured set of questions with clear answer options",
  "fr": "un questionnaire structuré avec options de réponse claires",
  "it": "un questionario strutturato con opzioni di risposta chiare",
  "es": "un cuestionario estructurado con opciones claras",
  "pt": "um questionário estruturado com opções claras",
  "nl": "een gestructureerde vragenlijst met duidelijke antwoordopties",
  "pl": "uporządkowany kwestionariusz z jasnymi odpowiedziami",
  "tr": "açık yanıt seçenekli yapılandırılmış anket",
  "ru": "структурированная анкета с ясными вариантами ответа"
 },
 "guide": {
  "en": "clear, verified step-by-step instructions",
  "fr": "des instructions claires, vérifiables et détaillées par étapes",
  "it": "istruzioni chiare e verificabili passo dopo passo",
  "es": "instrucciones claras y verificables paso a paso",
  "pt": "instruções claras e verificáveis passo a passo",
  "nl": "duidelijke, controleerbare stapsgewijze instructies",
  "pl": "jasna, weryfikowalna instrukcja krok po kroku",
  "tr": "açık ve doğrulanabilir adım adım yönergeler",
  "ru": "понятные проверяемые пошаговые инструкции"
 },
 "review": {
  "en": "a constructive, evidence-based review with findings and recommendations",
  "fr": "une revue constructive et factuelle avec constats et recommandations",
  "it": "una revisione costruttiva basata sui fatti con risultati e raccomandazioni",
  "es": "una revisión constructiva basada en hechos con hallazgos y recomendaciones",
  "pt": "uma revisão construtiva baseada em evidências com conclusões e recomendações",
  "nl": "een constructieve, onderbouwde review met bevindingen en aanbevelingen",
  "pl": "rzeczowy przegląd z ustaleniami i zaleceniami",
  "tr": "bulgular ve öneriler içeren yapıcı kanıta dayalı inceleme",
  "ru": "конструктивный разбор с фактами, выводами и рекомендациями"
 },
 "generic": {
  "en": "a structured, directly usable deliverable for the selected task",
  "fr": "un livrable structuré et directement utilisable pour cette tâche",
  "it": "un risultato strutturato e subito utilizzabile per questa attività",
  "es": "un resultado estructurado y listo para la tarea seleccionada",
  "pt": "um resultado estruturado e pronto a usar para a tarefa",
  "nl": "een gestructureerd en direct bruikbaar resultaat voor deze taak",
  "pl": "uporządkowany wynik gotowy do wykorzystania w tym zadaniu",
  "tr": "seçilen görev için yapılandırılmış ve kullanılabilir çıktı",
  "ru": "структурированный готовый результат для выбранной задачи"
 }
}
OUTPUT_CATEGORY_PATTERNS = [["code","DAX|KQL|SQL|Code|Código|Skript|Befehle|Ausdruck|IaC|Refactoring|Patch|Bug"],["prompt","Prompt|Custom Instructions"],["workflow","Flow|Workflow|Prozessfluss|Schrittfolge|Approva"],["questionnaire","Quiz|Fragebogen|Fragenkatalog|Fragenliste|Fragenmatrix"],["presentation","Folie|Folien|Präsentation|Storyboard|Deck|Sprecherhinweise|Videoskript|Voiceover"],["email","E-Mail|Nachricht|Mail|Antwort|Reply"],["summary","Summary|Zusammenfassung|Kurzfassung|Recap|Catch-up|Kurzübersicht|Kurzsummary"],["brief","Briefing|Brief|One-Pager"],["review","Review|Audit|Checkliste|Check|Prüfung|Testmatrix|Abnahme"],["matrix","Matrix|matrix|Architekturmatrix"],["table","Tabelle|Tabelle|Data Table|Analysetabelle"],["report","Bericht|Report|Investigation"],["analysis","Analyse|Analysis|Auswertung|Insight|Trends|Anomalie|Stimmung|Assessment"],["plan","Plan|Roadmap|Zeitlinie|Timeline|Aufgabenstruktur|Aufgabenliste|Maßnahmen"],["guide","Guide|Anleitung|Korrekturschritte|Troubleshooting|Schritt-für-Schritt"],["list","Liste|Übersicht|Inventory|Katalog|Cluster|Treffer|Kriterien"],["concept","Konzept|Design|Architecture|Architektur|Screen|Seitenentwurf|Sitemap|Lösungsvorschlag|Setup|Vorschlag|Strategie"]]



# Platform guardrails that the canonical task composer enforces per app.
APP_SCOPE_RULES = {
 "copilot_chat": {
  "en": "Use only sources and work data genuinely accessible in the selected Copilot context. Do not invent internal company information.",
  "fr": "N'utilisez que des sources et données professionnelles réellement accessibles dans le contexte Copilot choisi. N'inventez aucune donnée interne.",
  "it": "Usa soltanto fonti e dati di lavoro realmente accessibili nel contesto Copilot selezionato. Non inventare dati aziendali interni.",
  "es": "Utiliza solo fuentes y datos de trabajo realmente accesibles en el contexto Copilot seleccionado. No inventes datos internos de la empresa.",
  "pt": "Utilize apenas fontes e dados de trabalho realmente acessíveis no contexto Copilot escolhido. Não invente dados internos da empresa.",
  "nl": "Gebruik alleen bronnen en werkgegevens die daadwerkelijk toegankelijk zijn in de gekozen Copilot-context. Verzin geen interne bedrijfsgegevens.",
  "pl": "Korzystaj tylko ze źródeł i danych roboczych faktycznie dostępnych w wybranym kontekście Copilot. Nie wymyślaj wewnętrznych danych firmy.",
  "tr": "Yalnızca seçilen Copilot bağlamında gerçekten erişilebilen kaynakları ve iş verilerini kullanın. Şirket içi verileri uydurmayın.",
  "ru": "Используйте только источники и рабочие данные, реально доступные в выбранном контексте Copilot. Не выдумывайте внутренние сведения компании."
 },
 "outlook": {
  "en": "Refer only to emails, threads, calendar or meeting information available in the current context. Do not claim a message was sent or an appointment changed unless that action is confirmed.",
  "fr": "Référez-vous seulement aux e-mails, conversations, calendriers et réunions disponibles dans le contexte actuel. Ne prétendez ni qu'un message a été envoyé ni qu'un rendez-vous a été modifié sans confirmation.",
  "it": "Fai riferimento solo a e-mail, conversazioni, calendario o riunioni disponibili nel contesto corrente. Non dichiarare invii o modifiche ad appuntamenti senza conferma.",
  "es": "Usa solo correos, hilos, calendarios o reuniones disponibles en el contexto actual. No afirmes que se envió un mensaje o cambió una cita sin confirmación.",
  "pt": "Utilize apenas e-mails, conversas, calendários ou reuniões disponíveis no contexto atual. Não indique que uma mensagem foi enviada ou uma reunião alterada sem confirmação.",
  "nl": "Verwijs alleen naar e-mails, gespreksreeksen, agenda's en vergaderingen die beschikbaar zijn in de huidige context. Claim geen verzonden bericht of gewijzigde afspraak zonder bevestiging.",
  "pl": "Odwołuj się wyłącznie do wiadomości, wątków, kalendarzy i spotkań dostępnych w bieżącym kontekście. Nie twierdź, że wysłano wiadomość lub zmieniono termin bez potwierdzenia.",
  "tr": "Yalnızca mevcut bağlamda bulunan e-postaları, yazışmaları, takvim veya toplantı bilgilerini kullanın. Onaylanmadıkça mesaj gönderildiğini veya randevu değiştirildiğini söylemeyin.",
  "ru": "Ссылайтесь только на письма, переписки, календарь и встречи, доступные в текущем контексте. Не утверждайте, что письмо отправлено или встреча изменена, без подтверждения."
 },
 "teams": {
  "en": "Use only chats, channel messages, transcripts and meeting content actually available. Mark responsibilities, decisions or deadlines as open when the evidence is ambiguous.",
  "fr": "Utilisez uniquement les conversations, messages de canal, transcriptions et contenus de réunion réellement disponibles. Signalez comme ouverts les responsabilités, décisions ou délais insuffisamment établis.",
  "it": "Usa solo chat, messaggi di canale, trascrizioni e contenuti delle riunioni realmente disponibili. Indica come aperti responsabilità, decisioni e scadenze non documentate con certezza.",
  "es": "Utiliza solo chats, mensajes de canal, transcripciones y contenido de reuniones realmente disponibles. Señala como pendientes las responsabilidades, decisiones o fechas no confirmadas.",
  "pt": "Utilize apenas chats, mensagens de canal, transcrições e conteúdos de reuniões realmente disponíveis. Assinale como pendentes responsabilidades, decisões ou prazos sem comprovação clara.",
  "nl": "Gebruik alleen werkelijk beschikbare chats, kanaalberichten, transcripties en vergaderinhoud. Markeer verantwoordelijkheden, besluiten en termijnen als open wanneer ze niet eenduidig zijn vastgelegd.",
  "pl": "Korzystaj tylko z rzeczywiście dostępnych czatów, wiadomości kanałowych, transkrypcji i treści spotkań. Oznacz jako otwarte obowiązki, decyzje i terminy, jeśli nie są jednoznacznie potwierdzone.",
  "tr": "Yalnızca gerçekten erişilebilir sohbetleri, kanal iletilerini, dökümleri ve toplantı içeriklerini kullanın. Belirsiz sorumluluk, karar veya tarihleri açık konu olarak işaretleyin.",
  "ru": "Используйте только реально доступные чаты, сообщения каналов, расшифровки и материалы встреч. Помечайте обязанности, решения и сроки как открытые, если они не подтверждены однозначно."
 },
 "word": {
  "en": "Work with the open document and explicitly referenced sources. Preserve established facts, figures, names and requirements unless a change is requested.",
  "fr": "Travaillez à partir du document ouvert et des sources explicitement citées. Préservez les faits, chiffres, noms et exigences établis sauf demande de modification.",
  "it": "Lavora sul documento aperto e sulle fonti esplicitamente citate. Conserva fatti, numeri, nomi e requisiti accertati salvo richiesta di modifica.",
  "es": "Trabaja con el documento abierto y las fuentes indicadas expresamente. Conserva los hechos, cifras, nombres y requisitos establecidos salvo petición de cambio.",
  "pt": "Trabalhe com o documento aberto e as fontes expressamente referidas. Preserve factos, números, nomes e requisitos confirmados salvo pedido de alteração.",
  "nl": "Werk met het geopende document en expliciet genoemde bronnen. Behoud vaststaande feiten, cijfers, namen en vereisten tenzij om een wijziging wordt gevraagd.",
  "pl": "Pracuj na otwartym dokumencie i wyraźnie wskazanych źródłach. Zachowaj potwierdzone fakty, liczby, nazwiska i wymagania, chyba że poproszono o zmianę.",
  "tr": "Açık belge ve açıkça belirtilen kaynaklarla çalışın. Değişiklik istenmedikçe doğrulanmış olguları, sayıları, adları ve gereksinimleri koruyun.",
  "ru": "Работайте с открытым документом и явно указанными источниками. Сохраняйте подтверждённые факты, цифры, имена и требования, если не запрошено изменение."
 },
 "excel": {
  "en": "Base calculations on the actually available data range. Identify assumptions, missing values and data-quality problems. Do not fabricate metrics.",
  "fr": "Fondez les calculs sur les plages de données réellement disponibles. Signalez les hypothèses, valeurs manquantes et problèmes de qualité. N'inventez pas d'indicateurs.",
  "it": "Basa i calcoli sull'intervallo di dati realmente disponibile. Segnala ipotesi, valori mancanti e problemi di qualità dei dati. Non inventare indicatori.",
  "es": "Basa los cálculos en el rango de datos realmente disponible. Indica supuestos, valores ausentes y problemas de calidad. No inventes métricas.",
  "pt": "Baseie os cálculos nos intervalos de dados realmente disponíveis. Identifique pressupostos, valores em falta e problemas de qualidade. Não invente indicadores.",
  "nl": "Baseer berekeningen op het werkelijk beschikbare gegevensbereik. Benoem aannames, ontbrekende waarden en kwaliteitsproblemen. Verzin geen kengetallen.",
  "pl": "Opieraj obliczenia na rzeczywiście dostępnych zakresach danych. Wskaż założenia, brakujące wartości i problemy z jakością. Nie wymyślaj wskaźników.",
  "tr": "Hesaplamaları gerçekten mevcut veri aralığına dayandırın. Varsayımları, eksik değerleri ve veri kalitesi sorunlarını belirtin. Metrik uydurmayın.",
  "ru": "Основывайте расчёты только на реально доступном диапазоне данных. Укажите допущения, пропуски и проблемы качества данных. Не выдумывайте показатели."
 },
 "powerpoint": {
  "en": "Preserve verified facts from referenced files. Do not invent figures or references. Separate slide content from optional speaker notes.",
  "fr": "Préservez les faits vérifiés des fichiers de référence. N'inventez ni chiffres ni références. Séparez le contenu des diapositives des notes de présentation facultatives.",
  "it": "Conserva i fatti verificati dei file citati. Non inventare cifre o riferimenti. Separa il contenuto delle diapositive dalle eventuali note del relatore.",
  "es": "Conserva los hechos verificados de los archivos citados. No inventes cifras ni referencias. Separa el contenido de las diapositivas de las notas opcionales del presentador.",
  "pt": "Preserve factos comprovados dos ficheiros referidos. Não invente valores nem referências. Separe o conteúdo dos diapositivos das notas opcionais do apresentador.",
  "nl": "Behoud geverifieerde feiten uit genoemde bestanden. Verzin geen cijfers of verwijzingen. Houd dia-inhoud gescheiden van optionele sprekersnotities.",
  "pl": "Zachowaj potwierdzone fakty z przywołanych plików. Nie wymyślaj liczb ani odniesień. Oddziel treść slajdów od opcjonalnych notatek prelegenta.",
  "tr": "Başvurulan dosyalardaki doğrulanmış bilgileri koruyun. Sayı veya kaynak uydurmayın. Slayt içeriğini isteğe bağlı konuşmacı notlarından ayırın.",
  "ru": "Сохраняйте проверенные факты из указанных файлов. Не выдумывайте цифры и ссылки. Отделяйте содержимое слайдов от необязательных заметок докладчика."
 }
}


def _output_label(value: str, language: str) -> str:
    """Best-effort native category fallback for unlocalized PM20 output options.

    Categories are only used when the exact reviewed UI translation is absent;
    avoid presenting an untranslated German output label as foreign-language text.
    """
    translated = _translated(str(value or ''), language)
    if translated:
        return translated
    for category, pattern in OUTPUT_CATEGORY_PATTERNS:
        if re.search(pattern, str(value or ''), re.IGNORECASE):
            return OUTPUT_CATEGORIES[category][language]
    return OUTPUT_CATEGORIES['generic'][language]


def render_localized_prompt(
    *, language: str, result: dict, product: str, task_title: str, task_id: str,
    application: str, family: str, selections: dict, maximum_chars: int | None = None,
) -> dict:
    """Return result with translated instructions, preserving canonical metadata.

    Locale-specific text is composed, not translated from arbitrary user data.
    Missing task-title translations never result in a German instruction.
    """
    if language == 'de':
        return result
    copy = MESSAGES[language]
    title = (_translated(task_title, language)
             or FREE_TASK_TITLES.get(task_id, {}).get(language)
             or SURFACE_TASK_TITLES.get(task_title, {}).get(language)
             or copy['fallback'])
    pieces = [
        f"{copy['task']}: {title}",
        f"{copy['app']}: {application}",
        f"{copy['requirements']}: {FREE_INTENTS.get(task_id, {}).get(language) or copy['intro']} {copy['output']}",
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
            role = (copy['primary'] if key == 'primary' else copy['secondary'] if key == 'secondary' else (_translated(str(key), language) or f"{copy['fields']} {index}"))
            supplied.append(f"{role}: «{literal}»")
    if supplied:
        pieces.append(copy['input'] + ':\n' + '\n'.join(supplied))
    if not maximum_chars:
        focus = selections.get('focus') or []
        if isinstance(focus, list):
            # Never silently drop a selected priority when one custom value
            # has no reviewed dictionary entry. Preserve its literal as data.
            translated = [
                _translated(str(value), language) or f'«{str(value)}»'
                for value in focus if str(value or '').strip()
            ]
            if translated:
                pieces.append(f"{copy['focus']}: " + ', '.join(translated))
        audience_raw = str(selections.get('audience') or '').strip()
        if audience_raw:
            audience = _translated(audience_raw, language) or f'«{audience_raw}»'
            pieces.append(f"{copy['audience']}: {audience}")
        selected_output = str(selections.get('output') or '').strip()
        if selected_output:
            pieces.append(f"{copy['format']}: {_output_label(selected_output, language)}")
        pieces.extend([
            f"{copy['method']}: {FAMILY_METHODS.get(family, {}).get(language) or copy.get(family, copy['analysis'])}",
        ])
        for code in ('tone', 'detail'):
            text = STYLE_MODIFIERS.get(str(selections.get(code) or ''), {}).get(language)
            if text:
                pieces.append(text)
        source_rule = SOURCE_RULES.get(str(selections.get('source') or ''), {}).get(language)
        if source_rule:
            pieces.append(source_rule)
        pieces.extend([
            copy['scope'],
            APP_SCOPE_RULES.get(str(application).strip().lower().replace(' ', '_'), {}).get(language, ''),
            f"{copy['quality']}: {copy['no_fabrication']}",
        ])
    prompt = '\n\n'.join(pieces)
    truncated_input = False
    if maximum_chars:
        # Compact PM20 prompts must retain the task and as much of the
        # selected source context as fits. Signal truncation explicitly.
        limit = int(maximum_chars)
        # The chosen output language MUST remain present even when long
        # user-provided source text exhausts a compact task's character cap.
        # Otherwise Copilot may answer in the source language by accident.
        prefix = f"{copy['task']}: {title}. {copy['output']}"
        if len(prefix) >= limit:
            truncated_input = bool(supplied)
            compact = prefix[:limit]
        else:
            details = '; '.join(supplied)
            available = max(0, limit - len(prefix) - 2)
            if len(details) > available:
                truncated_input = True
                details = (details[:max(0, available - 1)].rstrip(' ,;.:') + '…') if available else ''
            compact = prefix + ('. ' + details if details else '')
        prompt = compact
    return {**result, 'prompt': prompt, 'language': language,
            'localization_mode': 'structured',
            'source_values_preserved': not truncated_input,
            'input_truncated': truncated_input}
