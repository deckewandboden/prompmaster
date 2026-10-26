"""Read-only legal-language readiness matrix for Issue #87.

This audit neither approves nor publishes any legal content. Even a complete
technical matrix is NOT a legal sign-off or a deployment authorization.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.legal.readiness import build_readiness_report


class Command(BaseCommand):
    help = (
        'Read-only 6x9 legal translation readiness audit. Does not approve '
        'texts, enable feature flags, or authorize a release.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--json', action='store_true', dest='as_json',
            help='Emit a structured matrix without document bodies or reviewer details.',
        )
        parser.add_argument(
            '--strict', action='store_true',
            help='Exit nonzero if any required translation or active DE source is missing/invalid.',
        )

    def handle(self, *args, **options):
        report = build_readiness_report()
        statuses = report['summary']
        details = report['entries']
        source_errors = report['source_errors']
        technically_complete = report['status'] == 'TECHNICALLY_COMPLETE_EXTERNAL_SIGNOFF_REQUIRED'
        if options['as_json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            self.stdout.write(
                f"LEGAL_LOCALE_READINESS={report['status']}; "
                f"APPROVED={statuses['verified_approved']}/{len(details)}; "
                f"SOURCE_ERRORS={len(source_errors)}"
            )
            for item in details:
                if item['status'] != 'verified_approved':
                    self.stdout.write(
                        f"{item['document_type']}/{item['language']}: {item['status']}"
                    )
            self.stdout.write(
                'EXTERNAL_LEGAL_SIGNOFF=NOT_VERIFIED; '
                'DEPLOYMENT_AUTHORIZATION=NOT_GRANTED'
            )
        if options['strict'] and not technically_complete:
            raise CommandError(
                'Legal translation matrix incomplete; no approval or publication performed.'
            )
