from django.core.management.base import BaseCommand

from apps.contenthub.models import FAQEntry


FAQS = [
    ('installation', 'Muss PROMPTFINISHER installiert werden?', 'Nein. PROMPTFINISHER wird direkt im Browser verwendet.'),
    ('ki-ausfuehrung', 'Werden meine Prompts auf einem PROMPTFINISHER-KI-Server analysiert?', 'PROMPTFINISHER erstellt den Prompt. Die KI-Ausführung findet in Microsoft Copilot statt. Bei PROMPTFINISHER Pro werden die für die Prompt-Komposition eingegebenen Daten serverseitig verarbeitet, standardmäßig jedoch nicht als Promptinhalt gespeichert.'),
    ('payment-data', 'Werden meine Zahlungsdaten bei PROMPTFINISHER gespeichert?', 'Zahlungsdaten werden über den angebundenen Zahlungsdienst verarbeitet; PROMPTFINISHER speichert keine vollständigen Karten- oder Kontodaten.'),
    ('future-products', 'Gibt es zukünftig weitere PROMPTFINISHER-Versionen?', 'Die Produktarchitektur ist für weitere Varianten vorbereitet.'),
    ('price-change', 'Kann netstyle den Preis später ändern?', 'Preisänderungen gelten nur für zukünftige Käufe beziehungsweise Verlängerungen und verändern keine historischen Bestellungen.'),
    ('free-vs-pro', 'Was unterscheidet PROMPTFINISHER Pro von Free?', 'Pro enthält alle Free-Funktionen sowie zusätzliche Anwendungen, Szenarien und Verwaltungsfunktionen.'),
]


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        for index, (key, question, answer) in enumerate(FAQS, start=10):
            FAQEntry.objects.update_or_create(
                key=key,
                defaults={'question': question, 'answer': answer, 'audience': 'public', 'sort_order': index, 'active': True},
            )
        self.stdout.write(self.style.SUCCESS(f'{len(FAQS)} FAQ-Einträge gesetzt.'))
