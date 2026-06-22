# apps/portal/urls.py
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard_placeholder, name="dashboard"),
    path("login/", LoginView.as_view(template_name="portal/login.html"), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
]