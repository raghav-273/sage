# apps/portal/views.py
"""
Portal views.

PortalLoginView extends Django's built-in LoginView with adaptive human
verification: a plain-text challenge appears only after repeated failed
attempts from the same IP, never on a normal login. See
apps/portal/login_security.py for the failure-tracking and challenge
logic itself — this view just wires it into Django's login flow.

dashboard_placeholder exists only to give login something real to
redirect to and to prove route protection works — Milestone 10 replaces
its template content, not its existence or URL.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .login_security import (
    challenge_required,
    generate_challenge,
    get_client_ip,
    record_failed_attempt,
    reset_failures,
    verify_challenge,
)


class PortalLoginView(LoginView):
    """
    POST /login/

    Adds adaptive verification on top of Django's standard login flow:
    after LOGIN_CHALLENGE_FAILURE_THRESHOLD failures from the same IP
    within the configured window, a signed plain-text challenge must
    also be answered correctly. Below the threshold, login behaves
    exactly as it did before this change — no added friction.
    """

    template_name = "portal/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ip_address = get_client_ip(self.request)
        if challenge_required(ip_address):
            question, token = generate_challenge()
            context["challenge_required"] = True
            context["challenge_question"] = question
            context["challenge_token"] = token
        return context

    def form_valid(self, form):
        # form_valid means username/password were correct. If a challenge
        # is currently required for this IP, it must ALSO be answered
        # correctly before the login is allowed to succeed.
        ip_address = get_client_ip(self.request)
        if challenge_required(ip_address):
            token = self.request.POST.get("challenge_token", "")
            answer = self.request.POST.get("challenge_answer", "")
            if not verify_challenge(token, answer):
                form.add_error(None, "Verification failed. Please answer the question correctly.")
                return self.form_invalid(form)

        reset_failures(ip_address)
        return super().form_valid(form)

    def form_invalid(self, form):
        # Reached for wrong username/password (Django's normal flow) and
        # for a wrong challenge answer (the explicit call above). Either
        # way, it's a failed attempt and counts toward the threshold.
        ip_address = get_client_ip(self.request)
        record_failed_attempt(ip_address)
        return super().form_invalid(form)


@login_required
def dashboard_placeholder(request: HttpRequest) -> HttpResponse:
    return render(request, "portal/dashboard_placeholder.html")


def custom_404(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def custom_500(request: HttpRequest) -> HttpResponse:
    return render(request, "errors/500.html", status=500)