# apps/chunks/admin.py
"""Django admin registration for the chunks app."""

from django.contrib import admin

from .models import ContentChunk, DiagramAsset


@admin.register(ContentChunk)
class ContentChunkAdmin(admin.ModelAdmin):
    list_display = (
        "document",
        "chunk_index",
        "chunk_type",
        "section_identifier",
        "token_count",
        "has_embedding",
    )
    list_filter = ("chunk_type",)
    search_fields = ("chunk_text", "section_identifier", "document__name")
    readonly_fields = ("id", "created_at")
    ordering = ("document", "chunk_index")

    @admin.display(boolean=True, description="Embedded")
    def has_embedding(self, obj: ContentChunk) -> bool:
        return obj.embedding is not None


@admin.register(DiagramAsset)
class DiagramAssetAdmin(admin.ModelAdmin):
    list_display = ("document", "page", "image_format", "width_px", "height_px", "created_at")
    search_fields = ("caption", "ocr_text", "document__name")
    readonly_fields = ("id", "created_at")
    ordering = ("document", "page")