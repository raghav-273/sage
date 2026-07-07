# apps/portal/urls.py
from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.PortalLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("documents/upload/", views.document_upload_page, name="document-upload-page"),

    path("query/", views.query_page, name="query-page"),
    path("query/submit/", views.query_submit, name="query-submit"),
    
    path("chunks/<uuid:chunk_id>/context/", views.chunk_context_partial, name="chunk-context-partial"),
    
    path("documents/<uuid:document_id>/", views.document_detail_page, name="document-detail-page"),
    path("documents/<uuid:document_id>/ask/", views.document_conversation_page, name="document-conversation-page"),
    path("documents/<uuid:document_id>/status/",views.document_status_partial,name="document-status-partial",),
    path("documents/<uuid:document_id>/ask/submit/", views.document_conversation_submit, name="document-conversation-submit"),
    path("documents/<uuid:document_id>/ask/clear/", views.document_conversation_clear, name="document-conversation-clear"),
    path("documents/<uuid:document_id>/ask/export.pdf", views.investigation_export_pdf, name="investigation-export-pdf"),
    path("documents/<uuid:document_id>/figures/", views.document_figures_page, name="document-figures-page"),
]