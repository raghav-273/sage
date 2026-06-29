# apps/conversation/admin.py
from django.contrib import admin

from .models import ConversationTurn, DocumentSession


class ConversationTurnInline(admin.TabularInline):
    model = ConversationTurn
    extra = 0
    can_delete = False
    fields = ("turn_index", "query_text", "has_valid_citations", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(DocumentSession)
class DocumentSessionAdmin(admin.ModelAdmin):
    list_display = ("document", "user", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [ConversationTurnInline]


@admin.register(ConversationTurn)
class ConversationTurnAdmin(admin.ModelAdmin):
    list_display = ("session", "turn_index", "query_text", "has_valid_citations", "created_at")
    readonly_fields = ("id", "created_at")