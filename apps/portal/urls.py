# apps/portal/urls.py
from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.PortalLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("documents/upload/", views.document_upload_page, name="document-upload-page"),
    path("documents/<uuid:document_id>/", views.document_detail_page, name="document-detail-page"),
]