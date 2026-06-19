# apps/documents/admin.py
"""Django admin registration for the documents app."""

from django.contrib import admin

from .models import Document, DocumentPage


class DocumentPageInline(admin.TabularInline):
    """Read-only inline preview of pages on the Document change page."""

    model = DocumentPage
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("page_number", "has_images", "has_tables", "created_at")
    readonly_fields = ("page_number", "has_images", "has_tables", "created_at")

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "status",
        "page_count",
        "file_size_bytes",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("name", "original_filename", "id")
    readonly_fields = ("id", "file_size_bytes", "created_at", "updated_at")
    ordering = ("-created_at",)
    inlines = [DocumentPageInline]


@admin.register(DocumentPage)
class DocumentPageAdmin(admin.ModelAdmin):
    list_display = ("document", "page_number", "has_images", "has_tables", "created_at")
    list_filter = ("has_images", "has_tables")
    search_fields = ("document__name", "raw_text")
    readonly_fields = ("id", "created_at")
    ordering = ("document", "page_number")