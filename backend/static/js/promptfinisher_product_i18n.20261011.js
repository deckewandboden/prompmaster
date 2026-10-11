/* PROMPTFINISHER: presentation-only localization for protected V2 Free/Pro.
 * Golden Master, catalog IDs, entitlements, input values and prompt bodies remain immutable.
 * This is an incremental UI catalog; unsupported terms stay German visibly.
 */
(() => {
  'use strict';
  const LANGUAGE_NAMES={
  "de": "Deutsch",
  "en": "English",
  "es": "Español",
  "pt": "Português",
  "tr": "Türkçe",
  "ru": "Русский",
  "pl": "Polski",
  "fr": "Français",
  "it": "Italiano",
  "nl": "Nederlands"
};
  const TEXT={
  "Für Microsoft Copilot": {
    "en": "For Microsoft Copilot",
    "es": "Para Microsoft Copilot",
    "pt": "Para o Microsoft Copilot",
    "tr": "Microsoft Copilot için",
    "ru": "Для Microsoft Copilot",
    "pl": "Dla Microsoft Copilot",
    "fr": "Pour Microsoft Copilot",
    "it": "Per Microsoft Copilot",
    "nl": "Voor Microsoft Copilot"
  },
  "FÜR MICROSOFT COPILOT": {
    "en": "FOR MICROSOFT COPILOT",
    "es": "PARA MICROSOFT COPILOT",
    "pt": "PARA O MICROSOFT COPILOT",
    "tr": "MICROSOFT COPILOT İÇİN",
    "ru": "ДЛЯ MICROSOFT COPILOT",
    "pl": "DLA MICROSOFT COPILOT",
    "fr": "POUR MICROSOFT COPILOT",
    "it": "PER MICROSOFT COPILOT",
    "nl": "VOOR MICROSOFT COPILOT"
  },
  "PROMPTFINISHER Pro entdecken →": {
    "en": "Discover PROMPTFINISHER Pro →",
    "es": "Descubrir PROMPTFINISHER Pro →",
    "pt": "Descobrir o PROMPTFINISHER Pro →",
    "tr": "PROMPTFINISHER Pro'yu keşfet →",
    "ru": "Узнать о PROMPTFINISHER Pro →",
    "pl": "Poznaj PROMPTFINISHER Pro →",
    "fr": "Découvrir PROMPTFINISHER Pro →",
    "it": "Scopri PROMPTFINISHER Pro →",
    "nl": "Ontdek PROMPTFINISHER Pro →"
  },
  "Sag Copilot genauer, was du brauchst.": {
    "en": "Tell Copilot exactly what you need.",
    "es": "Dile a Copilot exactamente qué necesitas.",
    "pt": "Diga ao Copilot exatamente do que precisa.",
    "tr": "Copilot'a neye ihtiyacınız olduğunu açıkça söyleyin.",
    "ru": "Объясните Copilot, что именно вам нужно.",
    "pl": "Powiedz Copilotowi dokładnie, czego potrzebujesz.",
    "fr": "Dites précisément à Copilot ce dont vous avez besoin.",
    "it": "Spiega a Copilot esattamente di cosa hai bisogno.",
    "nl": "Vertel Copilot precies wat je nodig hebt."
  },
  "Mehr aus Microsoft Copilot. Mit System.": {
    "en": "Get more from Microsoft Copilot. Systematically.",
    "es": "Saca más partido a Microsoft Copilot. Con método.",
    "pt": "Tire mais partido do Microsoft Copilot. Com método.",
    "tr": "Microsoft Copilot'tan daha fazlasını sistemli şekilde alın.",
    "ru": "Больше возможностей Microsoft Copilot. Системно.",
    "pl": "Wykorzystaj więcej możliwości Microsoft Copilot. Systematycznie.",
    "fr": "Tirez davantage parti de Microsoft Copilot. Avec méthode.",
    "it": "Ottieni di più da Microsoft Copilot. Con metodo.",
    "nl": "Haal meer uit Microsoft Copilot. Met structuur."
  },
  "PROMPTFINISHER macht aus deinem Anliegen Schritt für Schritt einen klaren, direkt einsetzbaren Prompt – kostenlos im Browser.": {
    "en": "PROMPTFINISHER turns your request into a clear, ready-to-use prompt, step by step — free in your browser.",
    "es": "PROMPTFINISHER convierte tu solicitud paso a paso en un prompt claro y listo para usar, gratis en el navegador.",
    "pt": "O PROMPTFINISHER transforma o seu pedido num prompt claro e pronto a usar, passo a passo, gratuitamente no navegador.",
    "tr": "PROMPTFINISHER, isteğinizi adım adım tarayıcıda ücretsiz olarak kullanıma hazır bir prompta dönüştürür.",
    "ru": "PROMPTFINISHER шаг за шагом превращает ваш запрос в понятный готовый промпт — бесплатно в браузере.",
    "pl": "PROMPTFINISHER krok po kroku zamienia Twój pomysł w jasny, gotowy do użycia prompt — bezpłatnie w przeglądarce.",
    "fr": "PROMPTFINISHER transforme progressivement votre demande en un prompt clair, prêt à l'emploi et gratuit dans votre navigateur.",
    "it": "PROMPTFINISHER trasforma passo dopo passo la tua richiesta in un prompt chiaro e pronto all'uso, gratuitamente nel browser.",
    "nl": "PROMPTFINISHER zet je vraag stap voor stap om in een duidelijke prompt die direct bruikbaar is, gratis in de browser."
  },
  "34 Copilot-Bereiche, präzise Aufgabenführung und professionelle Ausgabeformate – für Prompts, die im Arbeitsalltag sofort weiterhelfen.": {
    "en": "34 Copilot areas, precise task guidance and professional output formats for prompts that work right away.",
    "es": "34 áreas de Copilot, tareas guiadas y formatos profesionales para crear prompts útiles desde el primer momento.",
    "pt": "34 áreas do Copilot, orientação precisa de tarefas e formatos profissionais para prompts imediatamente úteis.",
    "tr": "34 Copilot alanı, ayrıntılı görev yönlendirmesi ve iş hayatına uygun profesyonel çıktı biçimleri.",
    "ru": "34 области Copilot, точное сопровождение задач и профессиональные форматы результата для повседневной работы.",
    "pl": "34 obszary Copilot, precyzyjne prowadzenie przez zadania i profesjonalne formaty wyników.",
    "fr": "34 domaines Copilot, un accompagnement précis des tâches et des formats de sortie professionnels.",
    "it": "34 aree Copilot, guida precisa alle attività e formati professionali per risultati immediatamente utilizzabili.",
    "nl": "34 Copilot-gebieden, gerichte taakbegeleiding en professionele uitvoerformaten voor direct bruikbare prompts."
  },
  "Copilot-Stufe": {
    "en": "Copilot tier",
    "es": "Nivel de Copilot",
    "pt": "Nível do Copilot",
    "tr": "Copilot düzeyi",
    "ru": "Уровень Copilot",
    "pl": "Poziom Copilot",
    "fr": "Niveau Copilot",
    "it": "Livello Copilot",
    "nl": "Copilot-niveau"
  },
  "Anwendung": {
    "en": "Application",
    "es": "Aplicación",
    "pt": "Aplicação",
    "tr": "Uygulama",
    "ru": "Приложение",
    "pl": "Aplikacja",
    "fr": "Application",
    "it": "Applicazione",
    "nl": "Toepassing"
  },
  "Aufgabe": {
    "en": "Task",
    "es": "Tarea",
    "pt": "Tarefa",
    "tr": "Görev",
    "ru": "Задача",
    "pl": "Zadanie",
    "fr": "Tâche",
    "it": "Attività",
    "nl": "Taak"
  },
  "Kontext": {
    "en": "Context",
    "es": "Contexto",
    "pt": "Contexto",
    "tr": "Bağlam",
    "ru": "Контекст",
    "pl": "Kontekst",
    "fr": "Contexte",
    "it": "Contesto",
    "nl": "Context"
  },
  "Zielgruppe": {
    "en": "Audience",
    "es": "Destinatarios",
    "pt": "Público-alvo",
    "tr": "Hedef kitle",
    "ru": "Аудитория",
    "pl": "Odbiorcy",
    "fr": "Public cible",
    "it": "Destinatari",
    "nl": "Doelgroep"
  },
  "Schwerpunkt": {
    "en": "Focus",
    "es": "Enfoque",
    "pt": "Foco",
    "tr": "Odak",
    "ru": "Акцент",
    "pl": "Priorytet",
    "fr": "Priorité",
    "it": "Priorità",
    "nl": "Focus"
  },
  "Prompt-Check": {
    "en": "Prompt review",
    "es": "Revisión del prompt",
    "pt": "Revisão do prompt",
    "tr": "Prompt kontrolü",
    "ru": "Проверка промпта",
    "pl": "Sprawdzenie promptu",
    "fr": "Vérification du prompt",
    "it": "Controllo del prompt",
    "nl": "Promptcontrole"
  },
  "Dein fertiger Prompt": {
    "en": "Your finished prompt",
    "es": "Tu prompt terminado",
    "pt": "O seu prompt final",
    "tr": "Tamamlanan promptunuz",
    "ru": "Готовый промпт",
    "pl": "Twój gotowy prompt",
    "fr": "Votre prompt final",
    "it": "Il tuo prompt finale",
    "nl": "Je voltooide prompt"
  },
  "Die wichtigsten Einstellungen auf einen Blick.": {
    "en": "Key settings at a glance.",
    "es": "Ajustes principales de un vistazo.",
    "pt": "Principais definições num relance.",
    "tr": "Önemli ayarlara genel bakış.",
    "ru": "Главные настройки с первого взгляда.",
    "pl": "Najważniejsze ustawienia w skrócie.",
    "fr": "Les principaux réglages en un coup d'œil.",
    "it": "Le impostazioni principali in breve.",
    "nl": "De belangrijkste instellingen in één oogopslag."
  },
  "Fortschritt": {
    "en": "Progress",
    "es": "Progreso",
    "pt": "Progresso",
    "tr": "İlerleme",
    "ru": "Прогресс",
    "pl": "Postęp",
    "fr": "Progression",
    "it": "Avanzamento",
    "nl": "Voortgang"
  },
  "Noch nicht gewählt": {
    "en": "Not selected yet",
    "es": "Aún no seleccionado",
    "pt": "Ainda não selecionado",
    "tr": "Henüz seçilmedi",
    "ru": "Ещё не выбрано",
    "pl": "Jeszcze nie wybrano",
    "fr": "Pas encore sélectionné",
    "it": "Non ancora selezionato",
    "nl": "Nog niet gekozen"
  },
  "Noch nicht vollständig": {
    "en": "Not complete yet",
    "es": "Aún incompleto",
    "pt": "Ainda incompleto",
    "tr": "Henüz tamamlanmadı",
    "ru": "Ещё не завершено",
    "pl": "Jeszcze nie ukończono",
    "fr": "Pas encore terminé",
    "it": "Non ancora completo",
    "nl": "Nog niet compleet"
  },
  "Bearbeiten": {
    "en": "Edit",
    "es": "Editar",
    "pt": "Editar",
    "tr": "Düzenle",
    "ru": "Изменить",
    "pl": "Edytuj",
    "fr": "Modifier",
    "it": "Modifica",
    "nl": "Bewerken"
  },
  "Kontext / Pflichtangaben": {
    "en": "Context / required details",
    "es": "Contexto / datos obligatorios",
    "pt": "Contexto / informações obrigatórias",
    "tr": "Bağlam / zorunlu bilgiler",
    "ru": "Контекст / обязательные сведения",
    "pl": "Kontekst / wymagane informacje",
    "fr": "Contexte / informations obligatoires",
    "it": "Contesto / dati obbligatori",
    "nl": "Context / verplichte gegevens"
  },
  "Ausgabe": {
    "en": "Output",
    "es": "Resultado",
    "pt": "Resultado",
    "tr": "Çıktı",
    "ru": "Результат",
    "pl": "Wynik",
    "fr": "Résultat",
    "it": "Risultato",
    "nl": "Uitvoer"
  },
  "Fehlende Pflichtangaben werden hier hervorgehoben. Mit „Bearbeiten“ springst du direkt zum betroffenen Schritt zurück.": {
    "en": "Missing required information is highlighted here. Select Edit to return to that step.",
    "es": "Aquí se destacan los datos obligatorios que faltan. Pulsa Editar para volver al paso.",
    "pt": "As informações obrigatórias em falta são destacadas aqui. Clique em Editar para voltar ao passo.",
    "tr": "Eksik zorunlu bilgiler burada vurgulanır. İlgili adıma dönmek için Düzenle'yi seçin.",
    "ru": "Недостающие обязательные сведения выделены. Нажмите «Изменить», чтобы вернуться к шагу.",
    "pl": "Brakujące wymagane informacje są tu wyróżnione. Wybierz Edytuj, aby wrócić do kroku.",
    "fr": "Les informations obligatoires manquantes sont mises en évidence. Cliquez sur Modifier pour revenir à l'étape.",
    "it": "Qui sono evidenziati i dati obbligatori mancanti. Seleziona Modifica per tornare al passaggio.",
    "nl": "Ontbrekende verplichte gegevens worden hier gemarkeerd. Kies Bewerken om naar de stap terug te gaan."
  },
  "Weiter zur Zielgruppe →": {
    "en": "Continue to audience →",
    "es": "Continuar a destinatarios →",
    "pt": "Continuar para público-alvo →",
    "tr": "Hedef kitleye devam →",
    "ru": "К аудитории →",
    "pl": "Dalej do odbiorców →",
    "fr": "Continuer vers le public cible →",
    "it": "Continua ai destinatari →",
    "nl": "Verder naar doelgroep →"
  },
  "Weiter zur Ausgabe →": {
    "en": "Continue to output →",
    "es": "Continuar a resultados →",
    "pt": "Continuar para resultado →",
    "tr": "Çıktıya devam →",
    "ru": "К результату →",
    "pl": "Dalej do wyniku →",
    "fr": "Continuer vers le résultat →",
    "it": "Continua al risultato →",
    "nl": "Verder naar uitvoer →"
  },
  "Zum Prompt-Check →": {
    "en": "Go to prompt review →",
    "es": "Ir a revisión del prompt →",
    "pt": "Ir para revisão do prompt →",
    "tr": "Prompt kontrolüne git →",
    "ru": "К проверке промпта →",
    "pl": "Do sprawdzenia promptu →",
    "fr": "Vérifier le prompt →",
    "it": "Vai al controllo del prompt →",
    "nl": "Naar promptcontrole →"
  },
  "Abmelden": {
    "en": "Sign out",
    "es": "Cerrar sesión",
    "pt": "Terminar sessão",
    "tr": "Çıkış yap",
    "ru": "Выйти",
    "pl": "Wyloguj się",
    "fr": "Se déconnecter",
    "it": "Esci",
    "nl": "Afmelden"
  },
  "PROMPTFINISHER Free": {
    "en": "PROMPTFINISHER Free",
    "es": "PROMPTFINISHER Free",
    "pt": "PROMPTFINISHER Free",
    "tr": "PROMPTFINISHER Free",
    "ru": "PROMPTFINISHER Free",
    "pl": "PROMPTFINISHER Free",
    "fr": "PROMPTFINISHER Free",
    "it": "PROMPTFINISHER Free",
    "nl": "PROMPTFINISHER Free"
  },
  "PROMPTFINISHER Pro": {
    "en": "PROMPTFINISHER Pro",
    "es": "PROMPTFINISHER Pro",
    "pt": "PROMPTFINISHER Pro",
    "tr": "PROMPTFINISHER Pro",
    "ru": "PROMPTFINISHER Pro",
    "pl": "PROMPTFINISHER Pro",
    "fr": "PROMPTFINISHER Pro",
    "it": "PROMPTFINISHER Pro",
    "nl": "PROMPTFINISHER Pro"
  },
  "Ausgabe definieren": {
    "en": "Define output",
    "es": "Definir resultado",
    "pt": "Definir resultado",
    "tr": "Çıktıyı belirle",
    "ru": "Определить результат",
    "pl": "Zdefiniuj wynik",
    "fr": "Définir le résultat",
    "it": "Definisci il risultato",
    "nl": "Uitvoer bepalen"
  },
  "Zielgruppe festlegen": {
    "en": "Select audience",
    "es": "Elegir destinatarios",
    "pt": "Selecionar público-alvo",
    "tr": "Hedef kitleyi seç",
    "ru": "Выбрать аудиторию",
    "pl": "Wybierz odbiorców",
    "fr": "Choisir le public cible",
    "it": "Seleziona i destinatari",
    "nl": "Doelgroep kiezen"
  },
  "Schwerpunkte auswählen": {
    "en": "Choose focus areas",
    "es": "Elegir prioridades",
    "pt": "Selecionar áreas de foco",
    "tr": "Odak alanlarını seç",
    "ru": "Выбрать акценты",
    "pl": "Wybierz priorytety",
    "fr": "Choisir les priorités",
    "it": "Scegli le priorità",
    "nl": "Focusgebieden kiezen"
  },
  "Anwendung auswählen": {
    "en": "Select application",
    "es": "Elegir aplicación",
    "pt": "Selecionar aplicação",
    "tr": "Uygulama seç",
    "ru": "Выбрать приложение",
    "pl": "Wybierz aplikację",
    "fr": "Choisir l'application",
    "it": "Seleziona l'applicazione",
    "nl": "Toepassing kiezen"
  },
  "Aufgabe auswählen": {
    "en": "Select task",
    "es": "Elegir tarea",
    "pt": "Selecionar tarefa",
    "tr": "Görev seç",
    "ru": "Выбрать задачу",
    "pl": "Wybierz zadanie",
    "fr": "Choisir la tâche",
    "it": "Seleziona l'attività",
    "nl": "Taak kiezen"
  },
  "Zurücksetzen": {
    "en": "Reset",
    "es": "Restablecer",
    "pt": "Repor",
    "tr": "Sıfırla",
    "ru": "Сбросить",
    "pl": "Resetuj",
    "fr": "Réinitialiser",
    "it": "Reimposta",
    "nl": "Opnieuw instellen"
  },
  "Schwerpunkte empfehlen": {
    "en": "Suggest focus areas",
    "es": "Sugerir prioridades",
    "pt": "Sugerir áreas de foco",
    "tr": "Odak alanı öner",
    "ru": "Предложить акценты",
    "pl": "Zaproponuj priorytety",
    "fr": "Proposer des priorités",
    "it": "Suggerisci priorità",
    "nl": "Focusgebieden voorstellen"
  },
  "Prompt kopieren": {
    "en": "Copy prompt",
    "es": "Copiar prompt",
    "pt": "Copiar prompt",
    "tr": "Promptu kopyala",
    "ru": "Копировать промпт",
    "pl": "Kopiuj prompt",
    "fr": "Copier le prompt",
    "it": "Copia prompt",
    "nl": "Prompt kopiëren"
  },
  "Ihre Konfiguration": {
    "en": "Your configuration",
    "es": "Tu configuración",
    "pt": "A sua configuração",
    "tr": "Yapılandırmanız",
    "ru": "Ваша конфигурация",
    "pl": "Twoja konfiguracja",
    "fr": "Votre configuration",
    "it": "La tua configurazione",
    "nl": "Je configuratie"
  },
  "Worum geht es konkret?": {
    "en": "What is this about?",
    "es": "¿De qué se trata?",
    "pt": "Qual é o assunto?",
    "tr": "Konu nedir?",
    "ru": "О чём идёт речь?",
    "pl": "O co dokładnie chodzi?",
    "fr": "Quel est le sujet ?",
    "it": "Di cosa si tratta?",
    "nl": "Waar gaat het over?"
  },
  "Detailtiefe": {
    "en": "Detail level",
    "es": "Nivel de detalle",
    "pt": "Nível de detalhe",
    "tr": "Ayrıntı düzeyi",
    "ru": "Уровень подробности",
    "pl": "Poziom szczegółowości",
    "fr": "Niveau de détail",
    "it": "Livello di dettaglio",
    "nl": "Detailniveau"
  },
  "Ausgabeformat": {
    "en": "Output format",
    "es": "Formato de salida",
    "pt": "Formato de saída",
    "tr": "Çıktı biçimi",
    "ru": "Формат результата",
    "pl": "Format wyniku",
    "fr": "Format de sortie",
    "it": "Formato di output",
    "nl": "Uitvoerformaat"
  },
  "Tonalität": {
    "en": "Tone",
    "es": "Tono",
    "pt": "Tom",
    "tr": "Üslup",
    "ru": "Тон",
    "pl": "Ton",
    "fr": "Ton",
    "it": "Tono",
    "nl": "Toon"
  },
  "Pflichtfeld": {
    "en": "Required field",
    "es": "Campo obligatorio",
    "pt": "Campo obrigatório",
    "tr": "Zorunlu alan",
    "ru": "Обязательное поле",
    "pl": "Pole wymagane",
    "fr": "Champ obligatoire",
    "it": "Campo obbligatorio",
    "nl": "Verplicht veld"
  },
  "PFLICHTFELD": {
    "en": "REQUIRED FIELD",
    "es": "CAMPO OBLIGATORIO",
    "pt": "CAMPO OBRIGATÓRIO",
    "tr": "ZORUNLU ALAN",
    "ru": "ОБЯЗАТЕЛЬНОЕ ПОЛЕ",
    "pl": "POLE WYMAGANE",
    "fr": "CHAMP OBLIGATOIRE",
    "it": "CAMPO OBBLIGATORIO",
    "nl": "VERPLICHT VELD"
  },
  "Bitte auswählen": {
    "en": "Please select",
    "es": "Selecciona",
    "pt": "Selecione",
    "tr": "Lütfen seçin",
    "ru": "Выберите",
    "pl": "Wybierz",
    "fr": "Veuillez sélectionner",
    "it": "Seleziona",
    "nl": "Maak een keuze"
  },
  "Professionell": {
    "en": "Professional",
    "es": "Profesional",
    "pt": "Profissional",
    "tr": "Profesyonel",
    "ru": "Профессиональный",
    "pl": "Profesjonalny",
    "fr": "Professionnel",
    "it": "Professionale",
    "nl": "Professioneel"
  },
  "Kompakt": {
    "en": "Concise",
    "es": "Breve",
    "pt": "Conciso",
    "tr": "Kısa",
    "ru": "Краткий",
    "pl": "Zwięzły",
    "fr": "Concis",
    "it": "Conciso",
    "nl": "Beknopt"
  },
  "Ausführlich": {
    "en": "Detailed",
    "es": "Detallado",
    "pt": "Detalhado",
    "tr": "Ayrıntılı",
    "ru": "Подробный",
    "pl": "Szczegółowy",
    "fr": "Détaillé",
    "it": "Dettagliato",
    "nl": "Uitgebreid"
  },
  "Prompt noch nicht erstellt.": {
    "en": "Prompt not created yet.",
    "es": "El prompt aún no se ha creado.",
    "pt": "O prompt ainda não foi criado.",
    "tr": "Prompt henüz oluşturulmadı.",
    "ru": "Промпт ещё не создан.",
    "pl": "Prompt nie został jeszcze utworzony.",
    "fr": "Le prompt n'est pas encore créé.",
    "it": "Il prompt non è ancora stato creato.",
    "nl": "Prompt is nog niet aangemaakt."
  },
  "Bitte zuerst alle markierten Pflichtfelder ausfüllen.": {
    "en": "Complete all required fields first.",
    "es": "Rellena primero los campos obligatorios.",
    "pt": "Preencha primeiro todos os campos obrigatórios.",
    "tr": "Önce tüm zorunlu alanları doldurun.",
    "ru": "Сначала заполните обязательные поля.",
    "pl": "Najpierw wypełnij wszystkie wymagane pola.",
    "fr": "Renseignez d'abord tous les champs obligatoires.",
    "it": "Compila prima tutti i campi obbligatori.",
    "nl": "Vul eerst alle verplichte velden in."
  },
  "Dein Prompt wird hier nach vollständiger Eingabe erzeugt.": {
    "en": "Your prompt appears here after completing the inputs.",
    "es": "Aquí aparecerá tu prompt cuando termines.",
    "pt": "O seu prompt aparecerá aqui depois de preencher os dados.",
    "tr": "Girişleri tamamladığınızda promptunuz burada görünür.",
    "ru": "Промпт появится здесь после заполнения данных.",
    "pl": "Twój prompt pojawi się tutaj po uzupełnieniu danych.",
    "fr": "Votre prompt apparaîtra ici après saisie complète.",
    "it": "Il prompt apparirà qui dopo aver completato i dati.",
    "nl": "Je prompt verschijnt hier zodra alle gegevens zijn ingevuld."
  },
  "Dieses Feld muss ausgefüllt werden, bevor der Prompt erzeugt wird.": {
    "en": "Complete this field before creating the prompt.",
    "es": "Rellena este campo antes de generar el prompt.",
    "pt": "Preencha este campo antes de gerar o prompt.",
    "tr": "Prompt oluşturmadan önce bu alanı doldurun.",
    "ru": "Заполните это поле перед созданием промпта.",
    "pl": "Wypełnij to pole przed utworzeniem promptu.",
    "fr": "Renseignez ce champ avant de créer le prompt.",
    "it": "Compila questo campo prima di creare il prompt.",
    "nl": "Vul dit veld in voordat je de prompt maakt."
  },
  "Sprache": {
    "en": "Language",
    "es": "Idioma",
    "pt": "Idioma",
    "tr": "Dil",
    "ru": "Язык",
    "pl": "Język",
    "fr": "Langue",
    "it": "Lingua",
    "nl": "Taal"
  },
  "Sprache wählen": {
    "en": "Select language",
    "es": "Elegir idioma",
    "pt": "Escolher idioma",
    "tr": "Dil seç",
    "ru": "Выбрать язык",
    "pl": "Wybierz język",
    "fr": "Choisir la langue",
    "it": "Scegli la lingua",
    "nl": "Taal kiezen"
  },
  "Deutsch": {
    "en": "German",
    "es": "Alemán",
    "pt": "Alemão",
    "tr": "Almanca",
    "ru": "Немецкий",
    "pl": "Niemiecki",
    "fr": "Allemand",
    "it": "Tedesco",
    "nl": "Duits"
  }
};
  const language = (document.cookie.match(/(?:^|; )promptfinisher_language=([^;]+)/)?.[1] || 'de').toLowerCase();
  const locale = Object.hasOwn(LANGUAGE_NAMES, language) ? language : 'de';
  document.documentElement.lang = locale;
  const t = key => TEXT[key]?.[locale] || key;
  window.PF_PRODUCT_LOCALE = Object.freeze({code:locale, t});
  const header = document.querySelector('.pmv2-header-actions');
  if (!header || header.querySelector('[data-pf-product-language]')) return;
  const label = document.createElement('label');
  label.className = 'pmv2-language';
  label.setAttribute('aria-label', t('Sprache wählen'));
  const select = document.createElement('select');
  select.setAttribute('aria-label', t('Sprache wählen'));
  select.dataset.pfProductLanguage = '1';
  for (const [code, name] of Object.entries(LANGUAGE_NAMES)) {
    const option = document.createElement('option');
    option.value = code;
    option.textContent = name;
    option.selected = code === locale;
    select.append(option);
  }
  select.addEventListener('change', () => {
    const next = location.pathname + location.search;
    const url = '/auth/language/?language=' + encodeURIComponent(select.value)
      + '&next=' + encodeURIComponent(next);
    location.assign(url);
  });
  label.append(select);
  header.prepend(label);
  const style = document.createElement('style');
  style.textContent = '.pmv2-language{display:flex;align-items:center;flex:0 0 136px;min-width:0}'
    + '.pmv2-language select{box-sizing:border-box;width:136px;max-width:100%;height:36px;'
    + 'padding:4px 22px 4px 9px;border:1px solid #9caec0;border-radius:9px;'
    + 'background:#fff;color:#102b43;font-size:12px;font-weight:650;cursor:pointer}'
    + '@media(max-width:700px){.pmv2-language{flex-basis:110px}.pmv2-language select{width:110px}}';
  document.head.append(style);
  if (locale === 'de') return;
  const notUi = 'script,style,textarea,input,option,[contenteditable],'
    + '.task,.app,.app-card,.task-card,.input-card,.option,.option-card,'
    + '#promptOutput,#pmv2PromptOutput,.pmv2-review-value';
  const matches = text => {
    const trimmed = (text || '').trim();
    return trimmed && Object.hasOwn(TEXT, trimmed) ? t(trimmed) : null;
  };
  const updateNode = node => {
    const parent = node.parentElement;
    if (!parent || parent.closest(notUi)) return;
    const original = node.nodeValue || '';
    const translated = matches(original);
    if (translated && translated !== original.trim()) {
      node.nodeValue = original.replace(original.trim(), translated);
    }
  };
  const walk = root => {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) updateNode(walker.currentNode);
  };
  const roots = [...document.querySelectorAll('.pmv2-header,.pmv2-hero,.pmv2-workspace')];
  roots.forEach(walk);
  let pending = false;
  const observer = new MutationObserver(records => {
    if (pending) return;
    if (!records.some(record => record.type === 'childList')) return;
    pending = true;
    queueMicrotask(() => {
      pending = false;
      roots.forEach(walk);
    });
  });
  roots.forEach(root => observer.observe(root, {subtree:true,childList:true}));
})();
