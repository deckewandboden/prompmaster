"""Read-only legal-language readiness matrix for Issue #87.

This audit neither approves nor publishes any legal content. Even a complete
technical matrix is NOT a legal sign-off or a deployment authorization.
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.legal.models import LegalDocument, LegalDocumentTranslation


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
        now = timezone.now()
        kinds = tuple(code for code, _label in LegalDocument.DOC_TYPES)
        languages = tuple(code for code, _label in LegalDocumentTranslation.LANGUAGES)
        sources = {
            kind: list(LegalDocument.objects.filter(
                doc_type=kind, active=True, valid_from__lte=now,
            ).order_by('-valid_from'))
            for kind in kinds
        }
        valid_ids = [rows[0].pk for rows in sources.values() if len(rows) == 1]
        translations = {
            (row.document_id, row.language): row
            for row in LegalDocumentTranslation.objects.filter(
                document_id__in=valid_ids,
            )
        }

        details = []
        source_errors = []
        statuses = {
            'verified_approved': 0, 'missing': 0, 'draft': 0,
            'review': 0, 'stale_approved': 0, 'source_unavailable': 0,
        }
        for kind in kinds:
            rows = sources[kind]
            if len(rows) != 1:
                source_errors.append({
                    'document_type': kind,
                    'reason': 'no_valid_active_german_source' if not rows
                              else 'ambiguous_active_german_source',
                })
            for language in languages:
                item = {
                    'document_type': kind,
                    'language': language,
                    'status': 'source_unavailable',
                }
                if len(rows) == 1:
                    doc = rows[0]
                    item['source_version'] = doc.version
                    translation = translations.get((doc.pk, language))
                    if translation is None:
                        item['status'] = 'missing'
                    elif translation.status == 'approved':
                        item['status'] = (
                            'verified_approved' if translation.is_publishable()
                            else 'stale_approved'
                        )
                    elif translation.status in ('draft', 'review'):
                        item['status'] = translation.status
                    else:
                        item['status'] = 'stale_approved'
                statuses[item['status']] += 1
                details.append(item)

        technically_complete = (
            len(source_errors) == 0
            and statuses['verified_approved'] == len(kinds) * len(languages)
        )
        report = {
            'audit': 'issue87_legal_locale_readiness_v1',
            'generated_at_utc': now.isoformat(),
            'status': (
                'TECHNICALLY_COMPLETE_EXTERNAL_SIGNOFF_REQUIRED'
                if technically_complete else 'BLOCKED'
            ),
            'required_document_types': list(kinds),
            'required_translation_languages': list(languages),
            'total_required_translations': len(kinds) * len(languages),
            'summary': statuses,
            'source_errors': source_errors,
            'feature_flags': {
                'LEGAL_TRANSLATIONS_PUBLIC_ENABLED': bool(
                    settings.LEGAL_TRANSLATIONS_PUBLIC_ENABLED
                ),
                'LEGAL_CHECKOUT_SNAPSHOT_REQUIRED': bool(
                    settings.LEGAL_CHECKOUT_SNAPSHOT_REQUIRED
                ),
            },
            'external_legal_signoff_verified_by_audit': False,
            'production_deployment_authorized_by_audit': False,
            'entries': details,
        }

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
