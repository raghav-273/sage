# apps/portal/views.py
"""
Portal views — the primary demonstration interface.

All views call service-layer functions directly (apps.documents.services,
apps.portal.health, services.generation.generation_service), the same
parallel-consumer relationship to apps.api established in Milestone 9A.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from apps.documents.models import Document
from apps.documents.serializers import DocumentUploadSerializer
from apps.documents.services import create_document_and_enqueue
from services.llm_client.generation_base import GenerationError
from services.retrieval.retrieval_service import RetrievalError
from services.generation.generation_service import generate_answer

from .answer_rendering import render_answer_with_numbered_citations
from .health import get_system_health
from .login_security import (
    challenge_required,
    generate_challenge,
    get_client_ip,
    record_failed_attempt,
    reset_failures,
    verify_challenge,
)

from .rate_limit import is_rate_limited, record_request

PAGE_SIZE = 20


def _processing_duration_display(document: Document) -> str | None:
    """Human-readable elapsed time for a terminal document. None if still in progress."""
    if not document.is_terminal:
        return None
    delta = document.updated_at - document.created_at
    total_seconds = int(delta.total_seconds())
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}m {seconds}s" if minutes else f"{seconds}s"


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
    """GET / — unchanged from Milestone 10."""
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
    """GET/POST /documents/upload/ — unchanged from the Milestone 10 fix."""
    errors = None
    if request.method == "POST":
        combined_data = request.POST.copy()
        combined_data.update(request.FILES)
        serializer = DocumentUploadSerializer(data=combined_data)
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
    GET /documents/<uuid>/ — replaces the Milestone 10 placeholder with
    metadata, error detail, and a self-canceling HTMX status poll.
    """
    document = get_object_or_404(Document, id=document_id)
    context = {"document": document, "processing_duration": _processing_duration_display(document)}
    return render(request, "portal/document_detail.html", context)


@login_required
def document_status_partial(request: HttpRequest, document_id: uuid.UUID) -> HttpResponse:
    """
    GET /documents/<uuid>/status/ — HTMX polling target. Returns only the
    status fragment, with hx-trigger present iff the document is still
    in progress — the mechanism that makes polling self-canceling.
    """
    document = get_object_or_404(Document, id=document_id)
    context = {"document": document, "processing_duration": _processing_duration_display(document)}
    return render(request, "portal/_document_status.html", context)


@login_required
def query_page(request: HttpRequest) -> HttpResponse:
    """GET /query/ — only READY documents appear in the selector."""
    ready_documents = Document.objects.filter(status=Document.Status.READY).order_by("name")
    return render(request, "portal/query.html", {"ready_documents": ready_documents})


@login_required
def query_submit(request: HttpRequest) -> HttpResponse:
    """
    POST /query/submit/ — HTMX partial endpoint, swapped into the query
    page's results panel. Calls generate_answer() directly — see the
    Milestone 11 design note on why this needs its own rate limiter.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    query_text = request.POST.get("query", "").strip()
    raw_document_ids = request.POST.getlist("document_ids")

    if not query_text:
        return render(request, "portal/_query_result.html", {"error": "Please enter a question."})

    try:
        document_ids = [uuid.UUID(d) for d in raw_document_ids] or None
    except ValueError:
        return render(request, "portal/_query_result.html", {"error": "Invalid document selection."})

    if is_rate_limited(request.user.id):
        return render(
            request, "portal/_query_result.html",
            {"error": "Too many questions in a short time. Please wait a moment and try again."},
        )
    record_request(request.user.id)

    try:
        result = generate_answer(query=query_text, document_ids=document_ids)
    except (RetrievalError, GenerationError) as exc:
        return render(request, "portal/_query_result.html", {"error": str(exc)})

    rendered_answer = (
        render_answer_with_numbered_citations(result) if result.has_valid_citations else None
    )
    return render(
        request, "portal/_query_result.html",
        {"result": result, "rendered_answer": rendered_answer},
    )


def custom_404(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def custom_500(request: HttpRequest) -> HttpResponse:
    return render(request, "errors/500.html", status=500)