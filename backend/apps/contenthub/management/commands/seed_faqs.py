from django.core.management.base import BaseCommand

from apps.contenthub.models import FAQEntry


FAQS = [
    ('installation', 'Muss PromptMaster installiert werden?', 'Nein. PromptMaster wird direkt im Browser verwendet.'),
    ('ki-ausfuehrung', 'Werden meine Prompts auf einem PromptMaster-KI-Server analysiert?', 'PromptMaster erstellt den Prompt. Die KI-Ausführung findet in Microsoft Copilot statt. Bei PromptMaster Pro werden die für die Prompt-Komposition eingegebenen Daten serverseitig verarbeitet, standardmäßig jedoch nicht als Promptinhalt gespeichert.'),
    ('payment-data', 'Werden meine Zahlungsdaten bei PromptMaster gespeichert?', 'Zahlungsdaten werden über den angebundenen Zahlungsdienst verarbeitet; PromptMaster speichert keine vollständigen Karten- oder Kontodaten.'),
    ('future-products', 'Gibt es zukünftig weitere PromptMaster-Versionen?', 'Die Produktarchitektur ist für weitere Varianten vorbereitet.'),
    ('price-change', 'Kann netstyle den Preis später ändern?', 'Preisänderungen gelten nur für zukünftige Käufe beziehungsweise Verlängerungen und verändern keine historischen Bestellungen.'),
    ('free-vs-pro', 'Was unterscheidet PromptMaster Pro von Free?', 'Pro enthält alle Free-Funktionen sowie zusätzliche Anwendungen, Szenarien und Verwaltungsfunktionen.'),
]


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        for index, (key, question, answer) in enumerate(FAQS, start=10):
            FAQEntry.objects.update_or_create(
                key=key,
                defaults={'question': question, 'answer': answer, 'audience': 'public', 'sort_order': index, 'active': True},
            )
        self.stdout.write(self.style.SUCCESS(f'{len(FAQS)} FAQ-Einträge gesetzt.'))
