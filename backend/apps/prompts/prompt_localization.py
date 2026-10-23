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
                 or CHOICE_LABELS.get(source, {}).get(language))
    return str(candidate).strip() if candidate else ''


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
            f"{copy['method']}: {FAMILY_METHODS.get(family, {}).get(language) or copy.get(family, copy['analysis'])}",
        ])
        for code in ('tone', 'detail'):
            text = STYLE_MODIFIERS.get(str(selections.get(code) or ''), {}).get(language)
            if text:
                pieces.append(text)
        pieces.extend([
            copy['scope'],
            f"{copy['quality']}: {copy['no_fabrication']}",
        ])
    prompt = '\n\n'.join(pieces)
    truncated_input = False
    if maximum_chars:
        # Compact PM20 prompts must retain the task and as much of the
        # selected source context as fits. Signal truncation explicitly.
        limit = int(maximum_chars)
        compact = f"{copy['task']}: {title}. " + '; '.join(supplied)
        if len(compact) + len(copy['output']) + 2 <= limit:
            compact += '. ' + copy['output']
        if len(compact) > limit:
            truncated_input = True
            compact = compact[:max(0, limit - 1)].rstrip(' ,;.:') + '…'
        prompt = compact
    return {**result, 'prompt': prompt, 'language': language,
            'localization_mode': 'structured',
            'source_values_preserved': not truncated_input,
            'input_truncated': truncated_input}
