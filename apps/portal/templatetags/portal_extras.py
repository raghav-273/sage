# apps/portal/templatetags/portal_extras.py
from django import template

register = template.Library()

_BADGE_CLASSES = {
    "PENDING": "secondary",
    "QUEUED": "info",
    "EXTRACTING": "info",
    "CHUNKING": "info",
    "EMBEDDING": "info",
    "READY": "success",
    "FAILED": "danger",
}


@register.filter
def status_badge_class(status: str) -> str:
    """Maps a Document.Status value to a Bootstrap badge color class."""
    return _BADGE_CLASSES.get(status, "secondary")