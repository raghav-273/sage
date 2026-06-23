# apps/portal/views.py
"""
Portal views — the primary demonstration interface.

dashboard, document_upload_page, and document_detail_page all call
service-layer functions directly (apps.documents.services,
apps.portal.health), the same parallel-consumer relationship to apps.api
established in Milestone 9A.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.documents.models import Document
from apps.documents.serializers import DocumentUploadSerializer
from apps.documents.services import create_document_and_enqueue

from .health import get_system_health
from .login_security import (
    challenge_required,
    generate_challenge,
    get_client_ip,
    record_failed_attempt,
    reset_failures,
    verify_challenge,
)

PAGE_SIZE = 20


class PortalLoginView(LoginView):
    """Unchanged from Milestone 9 — adaptive verification logic untouched."""

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
        ip_address = get_client_ip(self.request)
        record_failed_attempt(ip_address)
        return super().form_invalid(form)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """
    GET /  — replaces the Milestone 9A placeholder.

    Document table with search/status filtering and pagination, plus
    the system health section.
    """
    documents = Document.objects.annotate(chunk_count=Count("chunks")).order_by("-created_at")

    search_query = request.GET.get("q", "").strip()
    if search_query:
        documents = documents.filter(name__icontains=search_query)

    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        documents = documents.filter(status=status_filter)

    paginator = Paginator(documents, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "page_obj": page_obj,
        "search_query": search_query,
        "status_filter": status_filter,
        "status_choices": Document.Status.choices,
        "health_checks": get_system_health(),
        "total_documents": Document.objects.count(),
        "ready_documents": Document.objects.filter(status=Document.Status.READY).count(),
    }
    return render(request, "portal/dashboard.html", context)


@login_required
def document_upload_page(request: HttpRequest) -> HttpResponse:
    """
    GET/POST /documents/upload/

    Reuses DocumentUploadSerializer directly for validation — the exact
    same file-type/size rule the JSON API enforces, zero duplicated
    logic. Plain form POST + redirect, not HTMX — see design note above.
    """
    errors = None
    if request.method == "POST":
        serializer = DocumentUploadSerializer(data=request.POST, files=request.FILES)
        if serializer.is_valid():
            uploaded_file = serializer.validated_data["file"]
            name = serializer.validated_data.get("name") or uploaded_file.name
            document = create_document_and_enqueue(uploaded_file, name)
            return redirect("document-detail-page", document_id=document.id)
        errors = serializer.errors

    return render(request, "portal/document_upload.html", {"errors": errors})


@login_required
def document_detail_page(request: HttpRequest, document_id: uuid.UUID) -> HttpResponse:
    """
    GET /documents/<uuid>/

    Minimal placeholder — status + basic metadata only. Milestone 11
    replaces this template's content with the full timeline, error
    detail, and live-status polling.
    """
    document = get_object_or_404(Document, id=document_id)
    return render(request, "portal/document_detail_placeholder.html", {"document": document})


def custom_404(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def custom_500(request: HttpRequest) -> HttpResponse:
    return render(request, "errors/500.html", status=500)