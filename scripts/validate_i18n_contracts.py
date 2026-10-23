#!/usr/bin/env python3
"""Early-release i18n gate: 9 locale catalogs, placeholders and brand terms.

No third-party packages. Catches broken interpolation/format strings before
PostgreSQL, browser tests or the Docker image is built.
"""
from __future__ import annotations

from ast import literal_eval
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ('en', 'es', 'pt', 'tr', 'ru', 'pl', 'fr', 'it', 'nl')
BRAND_LABELS = (
    'Word', 'Excel', 'PowerPoint', 'Outlook', 'Teams', 'OneNote',
    'OneDrive', 'SharePoint', 'Power BI', 'Power Apps', 'Power Automate',
    'Copilot Studio', 'Clipchamp', 'Whiteboard', 'Power Pages',
    'Microsoft Security Copilot', 'Microsoft 365 Copilot Business',
    'Copilot Chat (Basic)', 'M365 Copilot (Basic)',
    'Microsoft Forms', 'Microsoft Planner', 'Microsoft Fabric',
    'Microsoft Copilot in Azure', 'Workplace Analytics', 'Copilot Analytics',
)
PLACEHOLDER = re.compile(r'%[(]([A-Za-z_][A-Za-z0-9_]*)[)][a-zA-Z]')


def parse_po(path: Path) -> dict[str, str]:
    entries = {}
    key = None
    translation = ''
    section = None

    def save():
        if key:
            if key in entries:
                raise ValueError(f'{path}: duplicated msgid {key!r}')
            entries[key] = translation

    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('msgid '):
            save()
            key = literal_eval(line[len('msgid '):])
            translation = ''
            section = 'id'
        elif line.startswith('msgstr '):
            translation = literal_eval(line[len('msgstr '):])
            section = 'translation'
        elif line.startswith('"') and section:
            piece = literal_eval(line)
            if section == 'id':
                key += piece
            else:
                translation += piece
    save()
    return entries


def main() -> None:
    base = parse_po(ROOT / 'backend/locale/en/LC_MESSAGES/django.po')
    assert len(base) >= 370, 'Too few canonical gettext messages'
    for code in LOCALES:
        path = ROOT / 'backend/locale' / code / 'LC_MESSAGES/django.po'
        found = parse_po(path)
        if set(found) != set(base):
            missing = set(base) - set(found)
            extra = set(found) - set(base)
            raise SystemExit(f'I18N FAIL {code}: missing={len(missing)}, unexpected={len(extra)}')
        for key, target in found.items():
            if not target.strip():
                raise SystemExit(f'I18N FAIL {code}: empty translation {key!r}')
            expected_tokens = sorted(PLACEHOLDER.findall(key))
            actual_tokens = sorted(PLACEHOLDER.findall(target))
            if expected_tokens != actual_tokens:
                raise SystemExit(
                    f'I18N FAIL {code}: unsafe named placeholders {key!r}: '
                    f'{expected_tokens} != {actual_tokens}'
                )
        if code in ('pl', 'fr', 'it', 'nl'):
            for product in ('PROMPTFINISHER Free', 'PROMPTFINISHER Pro', 'Free'):
                if found.get(product) != product:
                    raise SystemExit(f'I18N FAIL {code}: product branding modified: {product}')
        print(f'I18N PASS {code}: {len(found)} strings, placeholders unchanged')

    # The dynamic Free/Pro UI catalog is separate from Django gettext.
    # Product names must never be translated as ordinary dictionary words.
    bundle = (ROOT / 'backend/static/js/promptfinisher_product_i18n.20261011.js'
              ).read_text(encoding='utf-8')
    # The generated product bundle contains a base JSON dictionary followed
    # by one or more independently serialized Object.assign(TEXT,...) maps.
    # Combine all parts, rejecting duplicates, exactly as at runtime.
    rows = bundle.splitlines()
    bases = [v.strip() for v in rows if v.strip().startswith('const TEXT=')]
    additions = [v.strip() for v in rows if v.strip().startswith('Object.assign(TEXT,')]
    if len(bases) != 1 or not additions:
        raise SystemExit('I18N FAIL: unexpected product catalog structure')
    if not bases[0].endswith(';') or any(not v.endswith(');') for v in additions):
        raise SystemExit('I18N FAIL: malformed product dictionary terminators')
    catalog = json.loads(bases[0][len('const TEXT='):-1])
    for item in additions:
        more = json.loads(item[len('Object.assign(TEXT,'):-2])
        duplicates = set(more).intersection(catalog)
        if duplicates:
            raise SystemExit(f'I18N FAIL: duplicate product keys: {sorted(duplicates)!r}')
        catalog.update(more)
    for brand in BRAND_LABELS:
        if brand not in catalog:
            raise SystemExit(f'I18N FAIL: missing protected product label {brand}')
        for code in LOCALES:
            if catalog[brand].get(code) != brand:
                raise SystemExit(
                    f'I18N FAIL: product label {brand!r} mutated in {code}: '
                    f'{catalog[brand].get(code)!r}'
                )
    # Official application names must also survive inside descriptions and
    # task titles, not just when they occupy the whole translation key.
    checked = 0
    for original, translations in catalog.items():
        embedded = [brand for brand in BRAND_LABELS if brand in original]
        if not embedded:
            continue
        for code in LOCALES:
            rendered = translations.get(code, '')
            for brand in embedded:
                if brand not in rendered:
                    raise SystemExit(
                        f'I18N FAIL {code}: protected product name {brand!r} '
                        f'missing from translated phrase {original!r}'
                    )
                checked += 1
    print(f'I18N EMBEDDED BRAND LABELS PASS: {checked} preserved product names')

    # Reject broken word boundaries introduced by chained offline translations.
    # These names are indivisible trademarks and must never stick to a word.
    fused_brand = re.compile(
        r'(?:Copilot Chat|M365 Copilot|PROMPTFINISHER|netstyle|SharePoint|OneDrive)'
        r'(?=[A-Za-zÀ-ÿА-Яа-я])'
    )
    fused_microsoft_brand = re.compile(
        r'(?i)(?:(?<=\w)Microsoft\s+Copilot|'
        r'Microsoft\s+Copilot(?=\w)|'
        r'(?<=\w)M365\s+Copilot|M365\s+Copilot(?=\w))'
    )
    repeated_machine_word = re.compile(r'\b([A-Za-z]{2,})(?:\s+\1){4,}\b', re.I)
    for phrase, variants in catalog.items():
        for code in LOCALES:
            translation = variants.get(code, '')
            if fused_brand.search(translation) or fused_microsoft_brand.search(translation):
                raise SystemExit(
                    f'I18N FAIL {code}: product name concatenated to text: '
                    f'{phrase!r} => {translation[:160]!r}'
                )
            if repeated_machine_word.search(translation):
                raise SystemExit(
                    f'I18N FAIL {code}: repeated machine-translation token: '
                    f'{phrase!r} => {translation[:160]!r}'
                )
    protected_copilot_ui = (
        '1. Welche Microsoft-Copilot-Version nutzen Sie?',
        '1. Welche Copilot-Stufe zeigt Microsoft für Ihr Konto an?',
        'Alle erzeugten Prompts können direkt in Microsoft Copilot verwendet werden. Die Verfügbarkeit einzelner Microsoft-Funktionen hängt von Microsoft-Lizenz, Tenant und Rollout ab.',
        'Diese Funktion benötigt eine andere Microsoft-Copilot-Stufe.',
        'Microsoft-Copilot-Stufe erforderlich',
    )
    for source in protected_copilot_ui:
        for code in LOCALES:
            translated = catalog.get(source, {}).get(code, '')
            if 'Microsoft Copilot' not in translated:
                raise SystemExit(
                    f'I18N FAIL {code}: protected Copilot name missing in {source!r}'
                )
    print('I18N COPILOT PHRASES PASS: no concatenated brand names')

    for phrase in ('ab Copilot Chat (Basic)', 'ab M365 Copilot (Basic)'):
        for code in LOCALES:
            label = catalog[phrase][code]
            if any(label.lower().startswith(prefix) for prefix in (
                'off', 'apagado', 'desligado', 'kapalı',
                'выключать', 'wyłączone', 'départ', 'uit',
            )):
                raise SystemExit(f'I18N FAIL {code}: availability tier mistranslated as disabled')
    # German source phrases in the dynamic UI catalog can contain perfectly
    # valid Turkish repetitions (e.g. "adım adım" = step by step). All other
    # consecutive repeated whole words signal broken offline translation.
    doubled_word = re.compile(r'(?<!\w)(\w{2,})(?:\s+\1)+(?!\w)', re.I)
    for phrase, translations in catalog.items():
        for code in LOCALES:
            value = translations.get(code, '')
            for match in doubled_word.finditer(value):
                idiomatic_step_by_step = (
                    code == 'tr'
                    and re.search(r'Schritt[- ]für[- ]Schritt', phrase)
                    and match.group(0).casefold() == 'adım adım'
                )
                if not idiomatic_step_by_step:
                    raise SystemExit(
                        f'I18N FAIL {code}: repeated localized word in '
                        f'{phrase!r}: {match.group(0)!r}'
                    )
    turkish_quality = {
        'Kalender': 'Takvim',
        'Nächsten Termin prüfen': 'Sonraki randevuyu kontrol et',
        'optional': 'İsteğe bağlı',
        'Agent': 'Ajan',
        'Analytics': 'Analitik',
        'Architecture': 'Mimari',
        'Audio': 'Ses',
        'Coding': 'Kodlama',
        'Kommunikation': 'İletişim',
        'Notebook-Code erzeugen': 'Not defteri kodu oluştur',
        'Präsentation': 'Sunum',
        'Prompt-Abnahmetest erstellen': 'Prompt kabul testi oluştur',
        'Recherche': 'Araştırma',
        'Sales': 'Satış',
        'Stärken identifizieren': 'Güçlü yönleri belirle',
        'Umsetzung': 'Uygulama',
        'Video': 'Video',
        'Zusammenfassung': 'Özet',
        "Daten, Kennzahlen, Auffälligkeiten und Trends auswerten": "Verileri, temel göstergeleri, anormallikleri ve eğilimleri analiz et",
        "Datenschutz": "Veri koruma",
        "Offene Punkte": "Açık konular",
        "PROMPT BEREIT": "PROMPT HAZIR",
        "Schließen": "Kapat",
        "teilweise": "Kısmen",
        "Ausdrücke": "İfadeler",
        "Chats & Kanäle": "Sohbetler ve kanallar",
        "Datenanalyse": "Veri analizi",
        "Datenmodell": "Veri modeli",
        "Exposure": "Maruziyetler",
        "Flow debuggen": "Akış hatalarını ayıkla",
        "Formeln": "Formüller",
        "Lead bewerten": "Potansiyel müşteriyi değerlendir",
        "Modell": "Model",
        "Optimierung": "İyileştirme",
        "Viva Glint": "Viva Glint",
        "1. Welche Copilot-Stufe zeigt Microsoft für Ihr Konto an?": "1. Hesabınızda hangi Microsoft Copilot seviyesi görünüyor?",
    }
    for source, expected in turkish_quality.items():
        if catalog.get(source, {}).get('tr') != expected:
            raise SystemExit(
                f'I18N FAIL tr: reviewed UI term {source!r} changed unexpectedly'
            )
    checked_chat = (
        'Sicherer Microsoft-Copilot-Chat für Recherche, Inhalte, Analyse '
        'und gezielt bereitgestellte Dateien.'
    )
    if catalog.get(checked_chat, {}).get('tr') != (
        'Araştırma, içerik, analiz ve özel olarak sağlanan dosyalar '
        'için güvenli Microsoft Copilot sohbeti.'
    ):
        raise SystemExit('I18N FAIL tr: Copilot Chat product description drift')
    print('I18N TURKISH QUALITY PASS: 37 reviewed terms and whole-word repetition gate')

    # The protected Free/Pro runtime uses stable option values for composer
    # semantics. Translate only the visible text of explicitly-valued options.
    tone_keys = (
        'Kompakt', 'Standard', 'Detailliert', 'Professionell', 'Sachlich',
        'Management', 'Technisch', 'Direkt', 'Freundlich',
    )
    tone_examples = {
        ('Standard', 'tr'): 'Standart',
        ('Detailliert', 'tr'): 'Ayrıntılı',
        ('Detailliert', 'fr'): 'Détaillé',
        ('Sachlich', 'tr'): 'Nesnel',
        ('Sachlich', 'nl'): 'Zakelijk',
        ('Sachlich', 'pl'): 'Rzeczowy',
        ('Management', 'tr'): 'Yönetim',
        ('Management', 'nl'): 'Management',
        ('Freundlich', 'es'): 'Amable',
        ('Freundlich', 'tr'): 'Samimi',
    }
    for key in tone_keys:
        variants = catalog.get(key)
        if not variants:
            raise SystemExit(f'I18N FAIL: missing response-style choice {key!r}')
        for code in LOCALES:
            value = variants.get(code, '')
            if not value.strip():
                raise SystemExit(f'I18N FAIL {code}: empty response-style choice {key!r}')
            if re.search(r'\b(\w{2,})(?:\s+\1)\b', value, flags=re.I):
                raise SystemExit(
                    f'I18N FAIL {code}: repeated response-style choice {key!r}: {value!r}'
                )
    for (key, code), expected in tone_examples.items():
        if catalog[key][code] != expected:
            raise SystemExit(
                f'I18N FAIL {code}: response-style term {key!r} must be {expected!r}, '
                f'got {catalog[key][code]!r}'
            )
    if "'script,style,textarea,input,option,[contenteditable],'" in bundle:
        raise SystemExit('I18N FAIL: visible select option labels excluded from translation')
    if "option.setAttribute('value', option.textContent.trim())" not in bundle:
        raise SystemExit('I18N FAIL: implicit option values must be frozen before display translation')
    if "if (option && !option.hasAttribute('value')) return;" in bundle:
        raise SystemExit('I18N FAIL: implicit option text must not remain untranslated')
    print('I18N RESPONSE STYLE PASS: nine controls x nine locales, stable option values')

    # Availability and completion markers affect user decisions. Machine
    # translations must never invert inclusion semantics or drop status glyphs.
    reviewed_states = {
      "– nicht enthalten": {
        "en": "– Not included",
        "es": "– No incluido",
        "pt": "– Não incluído",
        "tr": "– Dahil değil",
        "ru": "– Не включено",
        "pl": "– Nie uwzględniono",
        "fr": "– Non inclus",
        "it": "– Non incluso",
        "nl": "– Niet inbegrepen"
      },
      "✓ enthalten": {
        "en": "✓ Included",
        "es": "✓ Incluido",
        "pt": "✓ Incluído",
        "tr": "✓ Dahil",
        "ru": "✓ Включено",
        "pl": "✓ Uwzględniono",
        "fr": "✓ Inclus",
        "it": "✓ Incluso",
        "nl": "✓ Inbegrepen"
      },
      "✓ vollständig": {
        "en": "✓ Complete",
        "es": "✓ Completo",
        "pt": "✓ Completo",
        "tr": "✓ Tam",
        "ru": "✓ Полностью",
        "pl": "✓ W pełni",
        "fr": "✓ Complet",
        "it": "✓ Completo",
        "nl": "✓ Volledig"
      },
      "NOCH NICHT VOLLSTÄNDIG": {
        "en": "NOT YET COMPLETE",
        "es": "AÚN NO ESTÁ COMPLETO",
        "pt": "AINDA NÃO ESTÁ COMPLETO",
        "tr": "HENÜZ TAMAMLANMADI",
        "ru": "ЕЩЁ НЕ ЗАВЕРШЕНО",
        "pl": "JESZCZE NIEUKOŃCZONE",
        "fr": "PAS ENCORE COMPLET",
        "it": "NON ANCORA COMPLETO",
        "nl": "NOG NIET VOLLEDIG"
      }
    }
    for source, target_locales in reviewed_states.items():
        for locale in LOCALES:
            current = catalog.get(source, {}).get(locale)
            if current != target_locales[locale]:
                raise SystemExit(
                    f'I18N FAIL {locale}: availability/completion label {source!r}: '
                    f'{current!r} != {target_locales[locale]!r}'
                )
    print('I18N AVAILABILITY STATES PASS: 4 status labels x 9 languages')

    # Reviewed critical app-access, prompt, and workflow instructions.
    # In particular, 'Pull Request' is a software term, not a pulling action,
    # and an email supplement must not invert the source's negative condition.
    reviewed_action_labels = {
      "Pull Request prüfen": {
        "en": "Review Pull Request",
        "es": "Revisar Pull Request",
        "pt": "Rever Pull Request",
        "tr": "Pull Request'i incele",
        "ru": "Проверить Pull Request",
        "pl": "Sprawdź Pull Request",
        "fr": "Examiner la Pull Request",
        "it": "Esaminare la Pull Request",
        "nl": "Pull Request controleren"
      },
      "Diese Anwendung ist mit Ihrer aktuellen Auswahl nicht freigeschaltet.": {
        "en": "This application is not unlocked with your current selection.",
        "es": "Esta aplicación no está desbloqueada con su selección actual.",
        "pt": "Este aplicativo não está desbloqueado com sua seleção atual.",
        "tr": "Bu uygulama mevcut seçiminizle kullanıma açık değil.",
        "ru": "Это приложение не разблокировано с вашим текущим выбором.",
        "pl": "Ta aplikacja nie jest odblokowana przy obecnym wyborze.",
        "fr": "Cette application n'est pas déverrouillée avec votre sélection actuelle.",
        "it": "Questa applicazione non è sbloccata con la selezione corrente.",
        "nl": "Deze toepassing is niet ontgrendeld met uw huidige selectie."
      },
      "Optional. Ergänzen Sie nur Informationen, die nicht bereits aus der E-Mail hervorgehen.": {
        "en": "Optional. Add only information that is not already included in the email.",
        "es": "Opcional. Añada solo información que no figure ya en el correo electrónico.",
        "pt": "Opcional. Acrescente apenas informações que ainda não constem do e-mail.",
        "tr": "İsteğe bağlı. Yalnızca e-postada zaten yer almayan bilgileri ekleyin.",
        "ru": "Необязательно. Добавляйте только сведения, которых ещё нет в электронном письме.",
        "pl": "Opcjonalnie. Dodaj tylko informacje, których nie ma jeszcze w wiadomości e-mail.",
        "fr": "Facultatif. Ajoutez uniquement les informations qui ne figurent pas déjà dans l'e-mail.",
        "it": "Facoltativo. Aggiungi solo informazioni non già presenti nell'e-mail.",
        "nl": "Optioneel. Voeg alleen informatie toe die nog niet in de e-mail staat."
      },
      "Azure-Ressourcen entwerfen, betreiben, optimieren und Fehler analysieren.": {
        "en": "Design, operate, and optimize Azure resources, and analyze errors.",
        "es": "Diseñar, administrar y optimizar recursos de Azure y analizar errores.",
        "pt": "Conceber, gerir e otimizar recursos do Azure e analisar erros.",
        "tr": "Azure kaynaklarını tasarlayın, yönetin, optimize edin ve hataları analiz edin.",
        "ru": "Проектировать, эксплуатировать и оптимизировать ресурсы Azure, анализировать ошибки.",
        "pl": "Projektuj, obsługuj i optymalizuj zasoby Azure oraz analizuj błędy.",
        "fr": "Concevoir, exploiter et optimiser les ressources Azure, puis analyser les erreurs.",
        "it": "Progettare, gestire e ottimizzare le risorse Azure e analizzare gli errori.",
        "nl": "Azure-resources ontwerpen, beheren en optimaliseren en fouten analyseren."
      },
      "Bericht prüfen": {
        "en": "Review report",
        "es": "Revisar el informe",
        "pt": "Rever o relatório",
        "tr": "Raporu incele",
        "ru": "Проверить отчёт",
        "pl": "Sprawdź raport",
        "fr": "Examiner le rapport",
        "it": "Esaminare il rapporto",
        "nl": "Rapport controleren"
      },
      "Nächsten Termin prüfen": {
        "en": "Check next appointment",
        "es": "Comprobar la próxima cita",
        "pt": "Verificar o próximo compromisso",
        "tr": "Sonraki randevuyu kontrol et",
        "ru": "Проверить следующую встречу",
        "pl": "Sprawdź następny termin",
        "fr": "Vérifier le prochain rendez-vous",
        "it": "Verificare il prossimo appuntamento",
        "nl": "Volgende afspraak controleren"
      }
    }
    for source, target_locales in reviewed_action_labels.items():
        for locale in LOCALES:
            current = catalog.get(source, {}).get(locale)
            if current != target_locales[locale]:
                raise SystemExit(
                    f'I18N FAIL {locale}: reviewed action {source!r}: '
                    f'{current!r} != {target_locales[locale]!r}'
                )
    print('I18N REVIEWED ACTIONS PASS: 6 critical source texts x 9 languages')

    # License warnings are action-critical: keep both the complete Microsoft
    # product name and an explicit requirement word in every translated label.
    requirement_words = {
        'en': 'REQUIRED', 'es': 'REQUIERE', 'pt': 'NECESSÁRIO',
        'tr': 'GEREKLİ', 'ru': 'ТРЕБУЕТСЯ', 'pl': 'WYMAGANY',
        'fr': 'REQUIS', 'it': 'RICHIESTO', 'nl': 'VEREIST',
    }
    for source, official in (
        ('M365 COPILOT (BASIC) ERFORDERLICH', 'M365 COPILOT (BASIC)'),
        ('MICROSOFT 365 COPILOT BUSINESS ERFORDERLICH',
         'MICROSOFT 365 COPILOT BUSINESS'),
    ):
        for code in LOCALES:
            label = catalog[source][code]
            if official not in label or requirement_words[code] not in label.upper():
                raise SystemExit(
                    f'I18N FAIL {code}: licensing requirement lost: '
                    f'{source!r} => {label!r}'
                )
    print('I18N LICENSE REQUIREMENT PASS: two license gates x nine languages')

    print('I18N PHRASE QUALITY PASS: no fused brand tokens or runaway word repetitions')

    print(f'I18N PRODUCT LABELS PASS: {len(BRAND_LABELS)} brands x {len(LOCALES)} locales')
    # The live Django Pro catalog is seeded from this frozen runtime source.
    # Verify visible app metadata and task-selection labels (not hidden prompt
    # instructions, IDs or user inputs) cannot silently fall back to German.
    logic_path = ROOT / 'backend/apps/prompts/data/pm20_golden_logic.json'
    app_definitions = json.loads(logic_path.read_text(encoding='utf-8'))['APP']
    if len(app_definitions) != 34:
        raise SystemExit(f'I18N FAIL: expected 34 application definitions, got {len(app_definitions)}')
    total_tasks = sum(len(app['tasks']) for app in app_definitions.values())
    if total_tasks != 194:
        raise SystemExit(f'I18N FAIL: expected 194 catalog tasks, got {total_tasks}')
    categories = {
        'app name': {app['name'] for app in app_definitions.values()},
        'app description': {app['copy'] for app in app_definitions.values()},
        'app licensing': {app['access'] for app in app_definitions.values()},
        'task title': {
            task['title'] for app in app_definitions.values() for task in app['tasks']
        },
        'task description': {
            task['intent'] for app in app_definitions.values() for task in app['tasks']
        },
        'task area': {
            task['area'] for app in app_definitions.values() for task in app['tasks']
        },
        'required input': {
            item for app in app_definitions.values() for task in app['tasks']
            for item in task.get('required', [])
        },
        'optional input': {
            item for app in app_definitions.values() for task in app['tasks']
            for item in task.get('optional', [])
        },
        'task audience': {
            item for app in app_definitions.values() for task in app['tasks']
            for item in task.get('audiences', [])
        },
        'task focus': {
            item for app in app_definitions.values() for task in app['tasks']
            for item in task.get('focus', [])
        },
        'output label': {
            item for app in app_definitions.values() for task in app['tasks']
            for item in task.get('outputs', [])
        },
    }
    for category, values in categories.items():
        for phrase in values:
            if phrase not in catalog:
                raise SystemExit(f'I18N FAIL: missing {category} string: {phrase!r}')
            for code in LOCALES:
                if not catalog[phrase].get(code, '').strip():
                    raise SystemExit(
                        f'I18N FAIL {code}: untranslated {category} label: {phrase!r}'
                    )
    print(
        'I18N LIVE APP CATALOG PASS: 34 apps / 194 tasks; '
        + ', '.join(f'{name}={len(values)}' for name, values in categories.items())
        + ' across nine target locales'
    )

    print('I18N CONTRACTS PASS: 10 UI languages incl. DE source')


if __name__ == '__main__':
    main()
