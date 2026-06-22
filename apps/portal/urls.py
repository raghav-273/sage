# apps/portal/urls.py
from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard_placeholder, name="dashboard"),
    path("login/", views.PortalLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
]