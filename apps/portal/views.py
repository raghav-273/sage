# apps/portal/views.py
"""
Portal views. dashboard_placeholder exists only to give login something
real to redirect to and to prove route protection works — Milestone 10
replaces its template content, not its existence or URL.

Login/logout themselves use Django's built-in LoginView/LogoutView,
wired directly in urls.py — no custom view needed, and it's both less
code and more secure than anything hand-rolled here.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


@login_required
def dashboard_placeholder(request: HttpRequest) -> HttpResponse:
    return render(request, "portal/dashboard_placeholder.html")


def custom_404(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def custom_500(request: HttpRequest) -> HttpResponse:
    return render(request, "errors/500.html", status=500)