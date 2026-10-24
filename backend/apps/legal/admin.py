from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError

from .models import (
    ConsumerContractDeclaration, DeletionRequest, LegalAcceptance,
    LegalDocument, LegalDocumentTranslation, RetentionPolicy,
)


@admin.register(LegalDocumentTranslation)
class LegalDocumentTranslationAdmin(admin.ModelAdmin):
    list_display = ('document', 'language', 'status', 'approved_by', 'approved_at')
    list_filter = ('status', 'language', 'document__doc_type')
    search_fields = ('document__version', 'approval_reference')
    actions = ('submit_for_review', 'approve_with_recorded_reference')
    readonly_fields = (
        'status', 'approved_by', 'approved_at', 'source_sha256', 'content_sha256',
    )
    fields = (
        'document', 'language', 'content', 'status', 'approval_reference',
        'approved_by', 'approved_at', 'source_sha256', 'content_sha256',
    )

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == 'approved':
            return tuple(field.name for field in obj._meta.fields)
        return super().get_readonly_fields(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop('delete_selected', None)
        if not request.user.has_perm('legal.approve_legal_translation'):
            actions.pop('approve_with_recorded_reference', None)
        return actions

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status == 'approved':
            return False
        return super().has_delete_permission(request, obj)

    @admin.action(description='Send legal translation draft for review')
    def submit_for_review(self, request, queryset):
        # A bulk update bypasses save() and would omit the fingerprints of
        # the exact documents sent to legal review.
        count = 0
        for translation in queryset.filter(status='draft').select_related('document'):
            try:
                translation.status = 'review'
                translation.save()
                count += 1
            except ValidationError as error:
                self.message_user(request, f'{translation}: {error}', level=messages.ERROR)
        self.message_user(request, f'{count} translation(s) submitted for review.')

    @admin.action(description='Approve reviewed translations with recorded legal sign-off')
    def approve_with_recorded_reference(self, request, queryset):
        if not request.user.has_perm('legal.approve_legal_translation'):
            raise PermissionDenied
        count = 0
        for translation in queryset.select_related('document'):
            try:
                translation.approve(
                    reviewer=request.user,
                    reference=translation.approval_reference,
                )
                count += 1
            except ValidationError as error:
                self.message_user(
                    request, f'{translation}: {error}', level=messages.ERROR,
                )
        self.message_user(request, f'{count} translation(s) approved.')


admin.site.register(LegalDocument)
admin.site.register(LegalAcceptance)
admin.site.register(RetentionPolicy)
admin.site.register(DeletionRequest)
admin.site.register(ConsumerContractDeclaration)
