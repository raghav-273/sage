 # apps/documents/urls.py
from django.urls import path

from .views import DocumentDetailView, DocumentUploadView

urlpatterns = [
    path("", DocumentUploadView.as_view(), name="document-upload"),
    path("<uuid:id>/", DocumentDetailView.as_view(), name="document-detail"),
]