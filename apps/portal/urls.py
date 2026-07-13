# apps/portal/urls.py
from django.contrib.auth.views import LogoutView
from django.urls import path, re_path
from apps.portal.views import serve_media_file

from .views_password_reset import (SagePasswordResetCompleteView,SagePasswordResetConfirmView,SagePasswordResetDoneView,SagePasswordResetView,)

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.PortalLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("documents/upload/", views.document_upload_page, name="document-upload-page"),

    path("query/", views.query_page, name="query-page"),
    path("query/submit/", views.query_submit, name="query-submit"),
    
    path("comparison/", views.comparison_page, name="comparison-page"),
    path("comparison/submit/", views.comparison_submit, name="comparison-submit"),
    path("chunks/<uuid:chunk_id>/context/", views.chunk_context_partial, name="chunk-context-partial"),
    
    path("documents/<uuid:document_id>/", views.document_detail_page, name="document-detail-page"),
    path("documents/<uuid:document_id>/ask/", views.document_conversation_page, name="document-conversation-page"),
    path("documents/<uuid:document_id>/status/",views.document_status_partial,name="document-status-partial",),
    path("documents/<uuid:document_id>/ask/submit/", views.document_conversation_submit, name="document-conversation-submit"),
    path("documents/<uuid:document_id>/ask/clear/", views.document_conversation_clear, name="document-conversation-clear"),
    path("documents/<uuid:document_id>/ask/export.pdf", views.investigation_export_pdf, name="investigation-export-pdf"),
    path("documents/<uuid:document_id>/figures/", views.document_figures_page, name="document-figures-page"),
    path("documents/<uuid:document_id>/outline/", views.document_outline_page, name="document-outline-page"),
    path("documents/<uuid:document_id>/compliance/", views.compliance_query_page, name="compliance-query-page"),
    path("documents/<uuid:document_id>/compliance/submit/", views.compliance_submit, name="compliance-submit"),
    path("documents/<uuid:document_id>/clause/<path:section_identifier>/history/",views.clause_investigation_history_partial,name="clause-investigation-history"),
    
    path("password-reset/", SagePasswordResetView.as_view(), name="password_reset"),
    path("password-reset/sent/", SagePasswordResetDoneView.as_view(), name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/",SagePasswordResetConfirmView.as_view(),name="password_reset_confirm",),
    path("password-reset/complete/", SagePasswordResetCompleteView.as_view(), name="password_reset_complete"),
]

urlpatterns += [
    re_path(r"^media/(?P<path>.+)$",serve_media_file,name="serve-media-file",),
]