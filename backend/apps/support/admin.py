from django.contrib import admin

from .models import SupportMessage, SupportRequest


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0
    can_delete = False
    fields = (
        'created_at',
        'sender_type',
        'visibility',
        'author_user',
        'body',
        'notification_email',
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ('subject', 'category', 'status', 'user', 'company', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('subject', 'message', 'user__email', 'company__name')
    inlines = [SupportMessageInline]


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = (
        'support_request',
        'sender_type',
        'visibility',
        'author_user',
        'created_at',
    )
    list_filter = ('sender_type', 'visibility')
    search_fields = (
        'support_request__subject',
        'support_request__user__email',
        'body',
    )
    readonly_fields = (
        'support_request',
        'author_user',
        'sender_type',
        'visibility',
        'body',
        'notification_email',
        'created_at',
        'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
