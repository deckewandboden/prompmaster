import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.legal.models import LegalDocument
from apps.notifications.models import EmailTemplate


VERSION = '2026-09-28'


class Command(BaseCommand):
    help = (
        'Installiert die geprüften PromptMaster-Rechtstexte mit Stand 28.09.2026 '
        'und aktiviert sie versioniert.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--vat-id',
            default=os.getenv('NETSTYLE_VAT_ID', ''),
            help=(
                'Intern bestätigte Umsatzsteuer-Identifikationsnummer für das Impressum. '
                'Standard: NETSTYLE_VAT_ID aus der Umgebung.'
            ),
        )
        parser.add_argument(
            '--consumer-dispute',
            choices=('no', 'yes'),
            default='no',
            help=(
                'Angabe nach § 36 VSBG: no = keine freiwillige Teilnahme, '
                'yes = Teilnahmebereitschaft (Schlichtungsstelle muss intern geprüft werden).'
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        vat_id = (options['vat_id'] or '').strip()
        if not vat_id:
            if settings.ENVIRONMENT == 'production':
                raise CommandError(
                    'NETSTYLE_VAT_ID bzw. --vat-id fehlt. Eine USt-IdNr. wird '
                    'absichtlich nicht aus externen Verzeichnissen übernommen.'
                )
            vat_id = 'STAGING – nicht produktiv'
        elif not vat_id.upper().startswith('DE') or len(vat_id.replace(' ', '')) != 11:
            raise CommandError('USt-IdNr. muss im Format DE123456789 angegeben werden.')
        else:
            vat_id = vat_id.replace(' ', '').upper()
        dispute = options['consumer_dispute']

        dispute_text = (
            'Verbraucherstreitbeilegung\n'
            'Die netstyle Informationstechnik GmbH ist weder verpflichtet noch bereit, '
            'an Streitbeilegungsverfahren vor einer Verbraucherschlichtungsstelle teilzunehmen.'
            if dispute == 'no'
            else
            'Verbraucherstreitbeilegung\n'
            'Die netstyle Informationstechnik GmbH ist bereit, an einem '
            'Streitbeilegungsverfahren vor einer Verbraucherschlichtungsstelle teilzunehmen. '
            'Die konkret zuständige Stelle ist vor Aktivierung dieser Variante intern zu ergänzen.'
        )

        imprint = f"""Impressum

Angaben gemäß § 5 Digitale-Dienste-Gesetz (DDG)

netstyle Informationstechnik GmbH
Am Bühl 2
57223 Kreuztal
Deutschland

Telefon: +49 2732 5928-0
Fax: +49 2732 5928-28
E-Mail: info@netstyle.de

Vertretungsberechtigte Geschäftsführer:
Rainer Spickermann
Jürgen Gastes
Thomas Bode

Registereintrag:
Amtsgericht Siegen
Handelsregister HRB 3971

Umsatzsteuer-Identifikationsnummer gemäß § 27a UStG:
{vat_id or '[intern zu ergänzen]'}

Verantwortlich für journalistisch-redaktionelle Inhalte
Soweit PromptMaster journalistisch-redaktionelle Inhalte im Sinne von § 18 Abs. 2 Medienstaatsvertrag anbietet, sind die Geschäftsführer Rainer Spickermann, Jürgen Gastes und Thomas Bode, Anschrift wie oben, verantwortlich.

Kontakt
Für Fragen zu PromptMaster erreichen Sie uns unter info@netstyle.de oder telefonisch unter +49 2732 5928-0.

{dispute_text}

Hinweis zur früheren EU-Online-Streitbeilegungsplattform
Die frühere europäische Plattform zur Online-Streitbeilegung (OS-Plattform) wurde eingestellt. Ein Verweis auf diese Plattform wird daher nicht mehr bereitgestellt.

Urheber- und Kennzeichenrechte
Inhalte, Marken, Logos und sonstige geschützte Bestandteile von PromptMaster dürfen nur im Rahmen der gesetzlichen Vorschriften oder mit Zustimmung des jeweiligen Rechteinhabers genutzt werden. Rechte an Microsoft, Microsoft 365, Copilot und weiteren bezeichneten Produkten liegen bei den jeweiligen Rechteinhabern. PromptMaster ist ein Angebot der netstyle Informationstechnik GmbH.
"""

        privacy = """Datenschutzerklärung für PromptMaster

Stand: 28.09.2026

1. Verantwortlicher
Verantwortlicher im Sinne der Datenschutz-Grundverordnung (DSGVO) ist:

netstyle Informationstechnik GmbH
Am Bühl 2
57223 Kreuztal
Deutschland
Telefon: +49 2732 5928-0
E-Mail: info@netstyle.de

Geschäftsführer: Rainer Spickermann, Jürgen Gastes, Thomas Bode.

2. Datenschutzbeauftragte
Die Datenschutzbeauftragte der netstyle Informationstechnik GmbH erreichen Sie unter:

Cristina Contreras
netstyle Informationstechnik GmbH
Am Bühl 2
57223 Kreuztal
E-Mail: CContreras@netstyle.de

3. Welche Daten PromptMaster verarbeitet
Je nach Nutzung verarbeiten wir insbesondere:
- technische Verbindungs- und Sicherheitsdaten, etwa IP-Adresse, Zeitpunkt, Browser-/User-Agent-Informationen sowie Sicherheits- und Auditereignisse,
- Konto- und Kontaktdaten wie Name, E-Mail-Adresse und gegebenenfalls Telefonnummer,
- Unternehmens-, Rechnungs- und Steuerangaben,
- Benutzer-, Rollen-, Lizenz-, Laufzeit- und Geräteinformationen,
- Bestell-, Zahlungsstatus-, Erstattungs- und Transaktionsreferenzen,
- Supportanfragen und die zur Bearbeitung übermittelten Inhalte,
- Nachweise über akzeptierte Rechtsdokumente,
- Erklärungen zu Widerruf, Kündigung und Datenschutzrechten,
- E-Mail-Versand- und Zustellinformationen.

Zahlungsdaten wie vollständige Kreditkartennummern werden nicht bei PromptMaster gespeichert. Die eigentliche Zahlungsdateneingabe erfolgt beim Zahlungsdienstleister.

4. Zwecke und Rechtsgrundlagen
Wir verarbeiten personenbezogene Daten insbesondere
- zur Vertragsanbahnung, Vertragserfüllung, Bereitstellung von PromptMaster, Lizenzverwaltung, Abrechnung und Support auf Grundlage von Art. 6 Abs. 1 Buchst. b DSGVO,
- zur Erfüllung gesetzlicher Aufbewahrungs-, Nachweis-, Steuer-, Handels- und Verbraucherschutzpflichten auf Grundlage von Art. 6 Abs. 1 Buchst. c DSGVO,
- zur Absicherung des Dienstes, Verhinderung von Missbrauch, Fehleranalyse, IT-Sicherheit, Protokollierung und Durchsetzung berechtigter Ansprüche auf Grundlage von Art. 6 Abs. 1 Buchst. f DSGVO,
- auf Grundlage einer Einwilligung nach Art. 6 Abs. 1 Buchst. a DSGVO, soweit wir für eine konkrete Verarbeitung eine Einwilligung einholen.

5. Prompt-Erstellung und Microsoft Copilot
PromptMaster unterstützt bei der Erstellung strukturierter Prompts. Die Ausführung des fertigen Prompts in Microsoft Copilot erfolgt außerhalb von PromptMaster und unterliegt den Bedingungen und Datenschutzhinweisen des vom Nutzer eingesetzten Microsoft-Dienstes. PromptMaster verkauft keine personenbezogenen Daten an Werbenetzwerke und erstellt aus Prompt-Inhalten keine Werbeprofile.

6. Zahlungsabwicklung über Mollie
Für Zahlungen nutzen wir Mollie. Im Rahmen der Zahlungsabwicklung werden die hierfür erforderlichen Bestell- und Zahlungsinformationen an Mollie übermittelt. Die Eingabe sensibler Zahlungsinstrumentdaten erfolgt auf den Systemen von Mollie. Mollie verarbeitet Zahlungsdaten im Rahmen seiner eigenen gesetzlichen und datenschutzrechtlichen Verantwortlichkeit. PromptMaster speichert insbesondere Zahlungsstatus, Betrag, Bestellbezug und Provider-Referenzen, soweit dies für Vertragsabwicklung, Nachweis und Buchhaltung erforderlich ist.

7. E-Mail-Versand
Wir verwenden E-Mail zur Kontoverifizierung, Passwort- und Sicherheitskommunikation, Vertragsabwicklung, Lizenzinformation, Support, Zahlungsinformation sowie zur gesetzlich erforderlichen Bestätigung von Widerrufs- und Kündigungserklärungen. Je nach technischer Konfiguration erfolgt der Versand über den von netstyle eingesetzten Mailserver bzw. Microsoft Graph.

8. Cookies und lokale Speicherung
PromptMaster verwendet technisch notwendige Cookies bzw. vergleichbare Mechanismen für Anmeldung, Sitzungsschutz, CSRF-Schutz, Sicherheit und den sicheren Checkout. Nach dem derzeitigen technischen Stand setzt die öffentliche PromptMaster-Marketingseite keine Werbe-, Profiling- oder Webanalyse-Cookies ein. Für ausschließlich technisch erforderliche Speicherung und Zugriffe ist keine Einwilligung über einen Marketing-Cookie-Banner erforderlich. Werden künftig optionale Analyse- oder Marketingdienste eingeführt, wird die Einwilligungssteuerung vor deren Aktivierung entsprechend angepasst.

9. Empfänger und Kategorien von Empfängern
Daten können im erforderlichen Umfang an folgende Empfänger übermittelt werden:
- technische Hosting-, Infrastruktur- und IT-Dienstleister,
- Zahlungsdienstleister, insbesondere Mollie,
- E-Mail- und Kommunikationsdienstleister,
- Steuerberatung, Wirtschaftsprüfung, Banken und Behörden, soweit dies rechtlich erforderlich ist,
- sonstige Auftragsverarbeiter nach Art. 28 DSGVO.

10. Drittlandübermittlungen
Soweit ein eingesetzter Dienst personenbezogene Daten außerhalb des Europäischen Wirtschaftsraums verarbeitet, erfolgt die Übermittlung nur unter Beachtung der Voraussetzungen der Art. 44 ff. DSGVO, etwa aufgrund eines Angemessenheitsbeschlusses oder geeigneter Garantien. Welche Übermittlungen tatsächlich stattfinden, richtet sich nach den jeweils aktivierten technischen Diensten.

11. Speicherdauer
Wir speichern personenbezogene Daten nur so lange, wie dies für den jeweiligen Zweck erforderlich ist. Vertrags-, Abrechnungs- und steuerlich relevante Daten werden entsprechend den gesetzlichen Aufbewahrungspflichten gespeichert. Sicherheits-, Audit-, Support-, Sitzungs- und technische Betriebsdaten werden nach den jeweils festgelegten und dokumentierten Aufbewahrungsregeln gelöscht oder anonymisiert, sofern keine gesetzlichen Pflichten oder berechtigten Gründe für eine längere Speicherung bestehen.

12. Betroffenenrechte
Sie haben nach Maßgabe der gesetzlichen Voraussetzungen insbesondere das Recht auf
- Auskunft nach Art. 15 DSGVO,
- Berichtigung nach Art. 16 DSGVO,
- Löschung nach Art. 17 DSGVO,
- Einschränkung der Verarbeitung nach Art. 18 DSGVO,
- Datenübertragbarkeit nach Art. 20 DSGVO,
- Widerspruch nach Art. 21 DSGVO,
- Widerruf einer erteilten Einwilligung mit Wirkung für die Zukunft.

Anfragen richten Sie bitte an info@netstyle.de oder an die oben genannte Datenschutzbeauftragte.

13. Beschwerderecht
Sie haben nach Art. 77 DSGVO das Recht, sich bei einer Datenschutzaufsichtsbehörde zu beschweren. Für die netstyle Informationstechnik GmbH ist insbesondere erreichbar:

Landesbeauftragte für Datenschutz und Informationsfreiheit Nordrhein-Westfalen
Kavalleriestraße 2-4
40213 Düsseldorf
Telefon: 0211 38424-0
E-Mail: poststelle@ldi.nrw.de

14. Sicherheit
PromptMaster setzt angemessene technische und organisatorische Maßnahmen ein. Dazu gehören insbesondere verschlüsselte Übertragung, rollenbasierte Berechtigungen, sichere Sitzungen, CSRF-Schutz, serverseitige Lizenzprüfung, Protokollierung sicherheitsrelevanter Vorgänge und getrennte Administrationsbereiche.

15. Änderungen
Wir passen diese Datenschutzerklärung an, wenn sich Funktionen, Empfänger, Rechtslage oder technische Verarbeitung wesentlich ändern. Die jeweils aktive Fassung wird versioniert bereitgestellt.
"""

        withdrawal = """Widerrufsbelehrung für Verbraucher

Stand: 28.09.2026

Widerrufsrecht
Sie haben das Recht, binnen vierzehn Tagen ohne Angabe von Gründen diesen Vertrag zu widerrufen.

Die Widerrufsfrist beträgt vierzehn Tage ab dem Tag des Vertragsschlusses.

Um Ihr Widerrufsrecht auszuüben, müssen Sie uns

netstyle Informationstechnik GmbH
Am Bühl 2
57223 Kreuztal
Deutschland
Telefon: +49 2732 5928-0
E-Mail: info@netstyle.de

mittels einer eindeutigen Erklärung über Ihren Entschluss, diesen Vertrag zu widerrufen, informieren. Sie können dafür die auf PromptMaster bereitgestellte elektronische Widerrufsfunktion „Vertrag widerrufen“ verwenden. Die Nutzung dieser Funktion ist nicht verpflichtend; ein Widerruf kann auch auf anderem eindeutigem Weg erklärt werden.

Zur Wahrung der Widerrufsfrist reicht es aus, dass Sie die Mitteilung über die Ausübung des Widerrufsrechts vor Ablauf der Widerrufsfrist absenden.

Folgen des Widerrufs
Wenn Sie diesen Vertrag widerrufen, haben wir Ihnen alle Zahlungen, die wir von Ihnen im Zusammenhang mit dem widerrufenen Vertrag erhalten haben, unverzüglich und spätestens binnen vierzehn Tagen ab dem Tag zurückzuzahlen, an dem die Mitteilung über Ihren Widerruf bei uns eingegangen ist. Für die Rückzahlung verwenden wir grundsätzlich dasselbe Zahlungsmittel, das Sie bei der ursprünglichen Transaktion eingesetzt haben, sofern nicht ausdrücklich etwas anderes vereinbart wurde und Ihnen dadurch keine Kosten entstehen.

Vorzeitiger Leistungsbeginn
PromptMaster Pro ist eine digitale Dienstleistung, die nach bestätigter Zahlung kurzfristig bereitgestellt wird. Wenn Sie ausdrücklich verlangen, dass wir vor Ablauf der Widerrufsfrist mit der Leistung beginnen, und Sie den Vertrag später wirksam widerrufen, kann nach den gesetzlichen Voraussetzungen Wertersatz für die bis zum Widerruf erbrachten Leistungen geschuldet sein.

Elektronische Widerrufsfunktion
Unter /vertrag-widerrufen/ steht während der Widerrufsfrist eine elektronische Widerrufsfunktion zur Verfügung. Nach Absenden über „Widerruf bestätigen“ erhalten Sie unverzüglich eine elektronische Eingangsbestätigung mit Inhalt, Datum und Uhrzeit Ihrer Erklärung.

Muster-Widerrufsformular
Wenn Sie den Vertrag widerrufen wollen, können Sie folgende Angaben an uns übermitteln:

An:
netstyle Informationstechnik GmbH
Am Bühl 2
57223 Kreuztal
E-Mail: info@netstyle.de

Hiermit widerrufe ich den von mir abgeschlossenen Vertrag über PromptMaster Pro.

Bestellt / Vertrag geschlossen am:
Name:
Anschrift:
Bestellnummer oder Kundennummer:
Datum:
Unterschrift (nur bei Mitteilung auf Papier):
"""

        terms = f"""Allgemeine Geschäftsbedingungen für PromptMaster

Stand: 28.09.2026

1. Anbieter und Geltungsbereich
Anbieter von PromptMaster ist die netstyle Informationstechnik GmbH, Am Bühl 2, 57223 Kreuztal. Diese AGB gelten für die Nutzung von PromptMaster Free und für Verträge über PromptMaster Pro. Gegenüber Verbrauchern gelten zwingende gesetzliche Verbraucherschutzvorschriften vorrangig.

2. Leistungsbeschreibung
PromptMaster unterstützt Nutzer bei der strukturierten Erstellung von Prompts für Microsoft Copilot und weitere im Produkt bezeichnete Microsoft-Anwendungen. PromptMaster ist kein Bestandteil von Microsoft und ersetzt keine erforderliche Microsoft-Lizenz. Funktionsumfang, unterstützte Anwendungen und technische Voraussetzungen ergeben sich aus der jeweils aktuellen Produktbeschreibung.

3. PromptMaster Free
PromptMaster Free kann im jeweils bereitgestellten Funktionsumfang ohne Entgelt genutzt werden. Ein Anspruch auf dauerhafte Bereitstellung bestimmter kostenloser Funktionen besteht nur im Rahmen zwingender gesetzlicher Vorgaben.

4. PromptMaster Pro
PromptMaster Pro ist eine entgeltliche digitale Dienstleistung. Pro-Lizenzen werden je Benutzer bzw. Lizenzplatz für die beim Kauf angegebene Laufzeit bereitgestellt. Nach aktuellem Produktmodell beträgt die Laufzeit exakt 365 Tage. Es erfolgt keine automatische kostenpflichtige Verlängerung. Eine Verlängerung erfordert eine neue ausdrückliche Bestellung.

5. Vertragsschluss
Die Darstellung auf der Webseite ist eine Aufforderung zur Abgabe einer Bestellung. Der Kunde wählt Lizenzanzahl und Kundentyp, gibt die erforderlichen Daten ein und gibt über die eindeutig als zahlungspflichtig gekennzeichnete Schaltfläche eine verbindliche Bestellung ab. Der Vertrag kommt nach erfolgreicher Annahme und Zahlungsabwicklung entsprechend dem im Checkout dargestellten Ablauf zustande. Der Vertragsinhalt und die zugeordneten Rechtsdokumentversionen werden technisch protokolliert.

6. Preise und Zahlung
Es gelten die im Checkout unmittelbar vor Abgabe der Bestellung angezeigten Preise. Verbraucherpreise werden einschließlich der gesetzlichen Umsatzsteuer angezeigt. Die Abrechnung für PromptMaster Pro erfolgt nach aktuellem Produktmodell für die gesamte 365-Tage-Laufzeit im Voraus. Die Zahlungsabwicklung erfolgt über Mollie und die im Checkout angebotenen Zahlungsmethoden.

7. Bereitstellung und Benutzerkonto
Nach bestätigter Zahlung werden die erworbenen Lizenzen dem Kundenkonto zugeordnet. Bei Unternehmenskunden verwaltet der Firmenadministrator die Benutzer und Lizenzzuweisungen. Zugangsdaten sind geheim zu halten und dürfen nicht mit unberechtigten Dritten geteilt werden.

8. Zusätzliche Lizenzen
Unternehmenskunden können während einer bestehenden Kundenbeziehung zusätzliche Lizenzen erwerben. Jede neu erworbene Lizenz hat die beim Nachkauf ausgewiesene eigene Laufzeit und Vergütung, sofern im Checkout nichts Abweichendes angegeben wird.

9. Verbraucher und Widerruf
Verbrauchern steht bei Vorliegen der gesetzlichen Voraussetzungen ein Widerrufsrecht zu. Einzelheiten enthält die aktuelle Widerrufsbelehrung. Die elektronische Widerrufsfunktion ist unter /vertrag-widerrufen/ erreichbar.

10. Vorzeitiger Leistungsbeginn bei Verbrauchern
Verlangt ein Verbraucher im Checkout ausdrücklich den Beginn der digitalen Dienstleistung vor Ablauf der Widerrufsfrist, wird dieser Wunsch als Nachweis zum Vertrag gespeichert. Ein etwaiger Wertersatz richtet sich ausschließlich nach den gesetzlichen Vorschriften.

11. Laufzeit, Ende und Kündigung
Eine Pro-Lizenz endet nach Ablauf der vereinbarten Laufzeit, wenn keine Verlängerung bestellt wurde. Die gesetzlichen Rechte zur außerordentlichen Kündigung bleiben unberührt. Verbraucher können eine Kündigungserklärung über die dauerhaft erreichbare Funktion /vertraege-kuendigen/ abgeben. Bei fehlender Angabe eines Beendigungszeitpunkts wird eine Kündigung im Zweifel zum frühestmöglichen rechtlich wirksamen Zeitpunkt behandelt.

12. Änderungen und Aktualisierungen
netstyle darf PromptMaster weiterentwickeln und aktualisieren. Gegenüber Verbrauchern bleiben die gesetzlichen Rechte bei digitalen Produkten unberührt. Erforderliche Aktualisierungen einschließlich Sicherheitsaktualisierungen werden im gesetzlich geschuldeten Zeitraum bereitgestellt. Wesentliche nachteilige Änderungen richten sich nach den dafür geltenden gesetzlichen Voraussetzungen.

13. Verfügbarkeit
netstyle betreibt PromptMaster mit angemessener Sorgfalt. Wartung, Sicherheitsmaßnahmen, Störungen von Netzen und Diensten Dritter sowie Ereignisse außerhalb des zumutbaren Einflussbereichs können die Verfügbarkeit vorübergehend einschränken. Zwingende gesetzliche Ansprüche bleiben unberührt.

14. Ergebnisse und Microsoft-Dienste
PromptMaster erzeugt Hilfestellungen und strukturierte Prompts. Ein bestimmtes Ergebnis bei Microsoft Copilot wird nicht garantiert. Inhalt, Verfügbarkeit und Leistungsumfang von Microsoft-Diensten unterliegen den Bedingungen des jeweiligen Anbieters.

15. Pflichten des Kunden
Der Kunde ist für die Richtigkeit seiner Angaben, die Sicherheit seiner Konten und die rechtmäßige Nutzung eingegebener Inhalte verantwortlich. Es dürfen insbesondere keine rechtswidrigen Inhalte, fremden Zugangsdaten oder Inhalte verarbeitet werden, für deren Nutzung keine Berechtigung besteht.

16. Mängelrechte für Verbraucher
Für Verbraucher gelten die gesetzlichen Vorschriften für digitale Produkte, insbesondere §§ 327 ff. BGB. Diese Rechte werden durch diese AGB nicht eingeschränkt.

17. Haftung
netstyle haftet unbeschränkt bei Vorsatz und grober Fahrlässigkeit, bei schuldhafter Verletzung von Leben, Körper oder Gesundheit, nach dem Produkthaftungsgesetz sowie im Umfang ausdrücklich übernommener Garantien. Bei leicht fahrlässiger Verletzung wesentlicher Vertragspflichten ist die Haftung auf den vertragstypischen, vorhersehbaren Schaden begrenzt. Im Übrigen ist die Haftung bei leichter Fahrlässigkeit ausgeschlossen, soweit gesetzlich zulässig. Zwingende Verbraucherrechte bleiben unberührt.

18. Datenschutz
Informationen zur Verarbeitung personenbezogener Daten enthält die jeweils aktuelle PromptMaster-Datenschutzerklärung.

19. Verbraucherstreitbeilegung
{dispute_text.replace('Verbraucherstreitbeilegung\n', '')}

20. Anwendbares Recht und Gerichtsstand
Es gilt deutsches Recht unter Ausschluss des UN-Kaufrechts. Bei Verbrauchern gilt diese Rechtswahl nur, soweit dadurch zwingender Schutz des Staates des gewöhnlichen Aufenthalts nicht entzogen wird. Gegenüber Kaufleuten, juristischen Personen des öffentlichen Rechts und öffentlich-rechtlichen Sondervermögen ist, soweit zulässig, Siegen Gerichtsstand.

21. Schlussbestimmungen
Sollte eine Bestimmung unwirksam sein oder werden, bleiben die übrigen Bestimmungen wirksam. An die Stelle einer unwirksamen Bestimmung treten die gesetzlichen Regelungen.
"""

        license_terms = """Lizenz- und Nutzungsbedingungen für PromptMaster

Stand: 28.09.2026

1. Gegenstand
Diese Lizenz- und Nutzungsbedingungen regeln die Nutzung von PromptMaster Free und PromptMaster Pro ergänzend zu den AGB.

2. Nutzungsrecht
Während der jeweiligen Bereitstellungs- bzw. Lizenzdauer erhält der berechtigte Nutzer ein einfaches, nicht ausschließliches, nicht übertragbares Recht, PromptMaster über die bereitgestellte Webanwendung für eigene rechtmäßige Zwecke zu verwenden.

3. PromptMaster Pro und Lizenzplätze
Ein Pro-Lizenzplatz darf zu einem Zeitpunkt nur einem berechtigten Nutzer zugeordnet sein. Bei Unternehmenskonten kann der Firmenadministrator einen Lizenzplatz innerhalb des eigenen Unternehmens freigeben und einem anderen berechtigten Mitarbeiter neu zuordnen. Die technische Lizenzhistorie bleibt aus Nachweis- und Sicherheitsgründen erhalten.

4. Geräte
Soweit ein Produkt ein Gerätelimit vorsieht, darf die Nutzung nur innerhalb des im Kundenkonto ausgewiesenen Limits erfolgen. Geräte können aus Sicherheitsgründen widerrufen oder neu registriert werden.

5. Nicht gestattete Nutzung
Nicht gestattet sind insbesondere
- die Weitergabe persönlicher Zugangsdaten an unberechtigte Dritte,
- die entgeltliche oder unentgeltliche Weitervermietung oder der Weiterverkauf einzelner PromptMaster-Zugänge ohne Zustimmung von netstyle,
- das Umgehen technischer Lizenz-, Zugriffs- oder Sicherheitsmechanismen,
- automatisierte missbräuchliche Zugriffe, die Sicherheit oder Stabilität beeinträchtigen,
- die Nutzung für rechtswidrige Zwecke.

Gesetzlich zwingend erlaubte Handlungen bleiben unberührt.

6. Inhalte des Nutzers
Der Nutzer behält seine Rechte an selbst eingegebenen Inhalten. Er ist dafür verantwortlich, dass er zur Verarbeitung und Nutzung der eingegebenen Informationen berechtigt ist. Besonders schutzbedürftige oder vertrauliche Daten sollen nur eingegeben werden, wenn dies für den jeweiligen Anwendungsfall erforderlich und organisatorisch zulässig ist.

7. Microsoft und Drittprodukte
Microsoft, Microsoft 365, Copilot und andere genannte Drittprodukte sind nicht Bestandteil der PromptMaster-Lizenz. Erforderliche Lizenzen, Konten und Berechtigungen für Drittprodukte sind vom Nutzer bzw. seinem Unternehmen selbst bereitzustellen.

8. Updates und Weiterentwicklung
Während einer aktiven Pro-Laufzeit stehen die im Produkt enthaltenen allgemeinen Weiterentwicklungen im Rahmen des jeweiligen Produkts zur Verfügung. Gegenüber Verbrauchern gelten zusätzlich die gesetzlichen Aktualisierungspflichten für digitale Produkte einschließlich erforderlicher Sicherheitsaktualisierungen.

9. Ende des Nutzungsrechts
Das Recht zur Nutzung von Pro-Funktionen endet mit Ablauf der bezahlten Lizenzperiode, soweit keine Verlängerung erfolgt. Das Kundenkonto kann für Verwaltung, Historie und erneuten Lizenzerwerb bestehen bleiben. Gesetzliche Rückabwicklungs-, Widerrufs- und Kündigungsrechte bleiben unberührt.

10. Schutzrechte
PromptMaster, Software, Gestaltung, Datenstrukturen und Inhalte sind im Rahmen der anwendbaren Schutzrechte geschützt. Diese Bedingungen übertragen keine Eigentums- oder Schutzrechte an der Software selbst.
"""

        accessibility = """Information zur Barrierefreiheit von PromptMaster

Stand: 28.09.2026

1. Anbieter und Dienstleistung
PromptMaster ist eine webbasierte digitale Dienstleistung der netstyle Informationstechnik GmbH, Am Bühl 2, 57223 Kreuztal. Die Anwendung unterstützt Nutzer dabei, strukturierte Prompts für Microsoft Copilot zu erstellen. PromptMaster Pro kann online bestellt, bezahlt, aktiviert und über ein Kundenportal verwaltet werden.

2. Durchführung der Dienstleistung
Die wesentlichen Schritte sind:
- Informationen zu Free und Pro auf der öffentlichen Webseite,
- Auswahl der Lizenzanzahl und des Kundentyps,
- Eingabe von Kontakt- und Rechnungsdaten,
- Bestätigung der Vertragsinformationen,
- Weiterleitung zur sicheren Zahlungsabwicklung,
- Aktivierung des Kundenkontos und der Lizenzen,
- Nutzung von PromptMaster und Verwaltung von Benutzern, Lizenzen, Geräten und Bestellungen.

3. Barrierefreiheitsanforderungen
Für den elektronischen Geschäftsverkehr berücksichtigt PromptMaster die anwendbaren Anforderungen des Barrierefreiheitsstärkungsgesetzes (BFSG) und der hierzu erlassenen Verordnung. Ziel ist, Informationen, Identifizierungs-, Authentifizierungs-, Sicherheits- und Zahlungsfunktionen so anzubieten, dass sie wahrnehmbar, bedienbar, verständlich und robust nutzbar sind.

4. Umgesetzte Maßnahmen
PromptMaster verwendet unter anderem:
- semantische HTML-Strukturen und beschriftete Formularfelder,
- Tastaturbedienbarkeit der wesentlichen Formulare und Funktionen,
- verständliche Überschriften und Navigationsbezeichnungen,
- sichtbare Fehlermeldungen und Statusinformationen,
- responsive Darstellung für unterschiedliche Bildschirmgrößen,
- textbasierte Alternativen für wesentliche Informationen,
- eindeutig bezeichnete Kauf-, Widerrufs- und Kündigungsfunktionen,
- Verzicht auf externe Werbe- und Trackingelemente im aktuellen Marketingauftritt.

5. Dekorative und komplexe Darstellungen
Die öffentliche Marketingseite kann dekorative grafische beziehungsweise animierte Elemente enthalten. Diese sind für Abschluss, Verwaltung und Nutzung eines Vertrags nicht erforderlich. Wesentliche Produkt-, Preis- und Vertragsinformationen werden zusätzlich textlich bereitgestellt.

6. Laufende Prüfung
PromptMaster wird technisch weiterentwickelt. Festgestellte Barrieren werden bewertet und im Rahmen der gesetzlichen Anforderungen behoben. Diese Information beruht auf einer internen technischen Bewertung und ersetzt keine förmliche Zertifizierung.

7. Feedback und Kontakt
Wenn Sie eine Barriere feststellen oder Informationen in einer besser zugänglichen Form benötigen, wenden Sie sich bitte an:

netstyle Informationstechnik GmbH
Am Bühl 2
57223 Kreuztal
Telefon: +49 2732 5928-0
E-Mail: info@netstyle.de

Bitte beschreiben Sie möglichst genau, welche Seite oder Funktion betroffen ist und welche Unterstützung Sie benötigen.

8. Zuständige Marktüberwachungsbehörde
Für die Marktüberwachung nach dem BFSG ist die Marktüberwachungsstelle der Länder für die Barrierefreiheit von Produkten und Dienstleistungen (MLBF AöR) zuständig:

Carl-Miller-Straße 6
39112 Magdeburg
Telefon: +49 391 289 230 23
E-Mail: kontakt@mlbf-barrierefrei.de

9. Erstellung und Überprüfung
Erstellt am 28.09.2026. Die Angaben werden bei wesentlichen Änderungen an PromptMaster oder den gesetzlichen Anforderungen überprüft und aktualisiert.
"""

        documents = {
            'imprint': imprint,
            'privacy': privacy,
            'withdrawal': withdrawal,
            'terms': terms,
            'license': license_terms,
            'accessibility': accessibility,
        }

        now = timezone.now()
        for doc_type, content in documents.items():
            LegalDocument.objects.filter(
                doc_type=doc_type,
                active=True,
            ).update(active=False)
            LegalDocument.objects.update_or_create(
                doc_type=doc_type,
                version=VERSION,
                defaults={
                    'content': content.strip(),
                    'valid_from': now,
                    'active': True,
                },
            )

        templates = {
            'withdrawal_received': (
                'PromptMaster – Eingang Ihres Widerrufs',
                'Guten Tag {name},\n\nwir bestätigen den Eingang Ihres Widerrufs.\n'
                'Vertrag / Bestellung / Kundennummer: {contract_reference}\n'
                'Eingang: {submitted_at}\n'
                'Vorgangs-ID: {declaration_id}\n\n'
                'Diese Nachricht dokumentiert den elektronischen Eingang Ihrer Erklärung.',
            ),
            'cancellation_received': (
                'PromptMaster – Eingang Ihrer Kündigung',
                'Guten Tag {name},\n\nwir bestätigen den Eingang Ihrer Kündigung.\n'
                'Art: {cancellation_kind}\n'
                'Vertrag / Bestellung / Kundennummer: {contract_reference}\n'
                'Gewünschter Beendigungszeitpunkt: {requested_end_date}\n'
                'Grund: {reason}\n'
                'Eingang: {submitted_at}\n'
                'Vorgangs-ID: {declaration_id}\n\n'
                'Diese Nachricht dokumentiert den elektronischen Eingang Ihrer Erklärung.',
            ),
        }
        for code, (subject, body_text) in templates.items():
            EmailTemplate.objects.update_or_create(
                code=code,
                defaults={
                    'subject': subject,
                    'body_text': body_text,
                    'active': True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'PromptMaster-Rechtstexte {VERSION} aktiviert: '
                + ', '.join(documents.keys())
            )
        )
        self.stdout.write(f'USt-IdNr. im Impressum: {vat_id or "[FEHLT]"}')
        self.stdout.write(f'VSBG-Einstellung: {dispute}')
