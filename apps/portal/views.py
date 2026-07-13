# apps/portal/views.py
"""
Portal views — the primary demonstration interface.

All views call service-layer functions directly (apps.documents.services,
apps.portal.health, services.generation.generation_service), the same
parallel-consumer relationship to apps.api established in Milestone 9A.
"""

from __future__ import annotations

import uuid
import logging
import mimetypes
import os

from django.http import FileResponse, Http404
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from apps.chunks.models import DiagramAsset
from apps.documents.models import Document
from apps.documents.serializers import DocumentUploadSerializer
from apps.documents.services import create_document_and_enqueue
from apps.conversation.models import DocumentSession
from apps.conversation.services import ask_in_session, clear_session, get_or_create_active_session


from services.llm_client.generation_base import GenerationError
from services.retrieval.retrieval_service import RetrievalError
from services.documents.clause_navigator import build_document_outline, flatten_for_template, get_clause_investigation_history
from services.generation.generation_service import generate_answer, ComplianceResult, generate_compliance_answer, ComparisonResult, generate_comparison_answer
from services.generation.answer_rendering import render_answer_with_numbered_citations


from .login_security import (
    challenge_required, generate_challenge, get_client_ip,
    honeypot_triggered, is_locked_out, lockout_remaining_seconds,
    record_failed_attempt, reset_failures, verify_challenge,
)




from .health import get_system_health

from .turnstile import verify_turnstile
from .rate_limit import is_rate_limited, record_request



PAGE_SIZE = 20


@login_required
def document_figures_page(request: HttpRequest, document_id: uuid.UUID) -> HttpResponse:
    """
    GET /documents/<uuid>/figures/

    Gallery of all extracted figures for this document. Caption search
    is a simple icontains filter — no new retrieval infrastructure needed.
    DiagramAssets without captions are included (caption rendered as
    "No caption available") so no figures are silently hidden.
    """
    document = get_object_or_404(Document, id=document_id)
    search_query = request.GET.get("q", "").strip()

    figures = DiagramAsset.objects.filter(document=document).select_related("page").order_by("page__page_number")
    if search_query:
        figures = figures.filter(caption__icontains=search_query)

    return render(request, "portal/document_figures.html", {
        "document": document,
        "figures": figures,
        "search_query": search_query,
        "total_figures": DiagramAsset.objects.filter(document=document).count(),
    })

@login_required
def chunk_context_partial(request: HttpRequest, chunk_id: uuid.UUID) -> HttpResponse:
    """
    GET /chunks/<uuid>/context/ — HTMX citation panel target.

    Returns the cited chunk with up to 2 adjacent chunks (by chunk_index)
    on either side from the same document, so engineers can verify a citation
    in full reading context rather than in isolation.
    """
    from apps.chunks.models import ContentChunk

    chunk = get_object_or_404(
        ContentChunk.objects.select_related("document", "page", "diagram_asset"),
        id=chunk_id,
    )

    before = list(
        ContentChunk.objects
        .filter(document=chunk.document, chunk_index__lt=chunk.chunk_index)
        .select_related("page")
        .order_by("-chunk_index")[:2]
    )
    before.reverse()

    after = list(
        ContentChunk.objects
        .filter(document=chunk.document, chunk_index__gt=chunk.chunk_index)
        .select_related("page")
        .order_by("chunk_index")[:2]
    )

    return render(request, "portal/_citation_panel.html", {
        "chunk": chunk,
        "before": before,
        "after": after,
    })

@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """
    GET / — Library front page.

    Documents are shown as navigable knowledge objects, not status rows.
    Each carries: stats, quick actions, investigation activity.
    """
    from apps.conversation.models import DocumentSession

    documents_qs = Document.objects.annotate(
        chunk_count=Count("chunks", distinct=True),
        figure_count=Count("diagrams", distinct=True),
        session_count=Count("conversation_sessions", distinct=True),
    ).order_by("-created_at")

    search_query = request.GET.get("q", "").strip()
    if search_query:
        documents_qs = documents_qs.filter(name__icontains=search_query)

    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        documents_qs = documents_qs.filter(status=status_filter)

    paginator = Paginator(documents_qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    # Library-level summary
    ready_docs = Document.objects.filter(status=Document.Status.READY)
    from apps.chunks.models import ContentChunk
    total_clauses = ContentChunk.objects.filter(
        document__status=Document.Status.READY
    ).exclude(chunk_type=ContentChunk.ChunkType.CAPTION).count()
    total_figures = DiagramAsset.objects.filter(
        document__status=Document.Status.READY
    ).count()
    active_investigations = DocumentSession.objects.filter(is_active=True).count()

    context = {
        "page_obj": page_obj,
        "search_query": search_query,
        "status_filter": status_filter,
        "status_choices": Document.Status.choices,
        "health_checks": get_system_health(),
        # Library summary stats
        "total_documents": Document.objects.count(),
        "ready_documents": ready_docs.count(),
        "total_clauses": total_clauses,
        "total_figures": total_figures,
        "active_investigations": active_investigations,
    }
    return render(request, "portal/dashboard.html", context)

@login_required
def document_conversation_page(request: HttpRequest, document_id: uuid.UUID) -> HttpResponse:
    """
    GET /documents/<uuid>/ask/

    If no active session exists: show the investigation start form.
    If active session exists: show the investigation workspace.

    POST /documents/<uuid>/ask/ (starting a new investigation):
    Creates a session with the provided title and redirects back.
    """
    document = get_object_or_404(Document, id=document_id, status=Document.Status.READY)

    try:
        session = DocumentSession.objects.get(document=document, user=request.user, is_active=True)
    except DocumentSession.DoesNotExist:
        session = None

    if request.method == "POST" and session is None:
        title = request.POST.get("title", "").strip()
        session = DocumentSession.objects.create(
            document=document, user=request.user, is_active=True,
            title=title or f"Investigation — {document.name}",
        )
        return redirect("document-conversation-page", document_id=document.id)

    if session is None:
        return render(request, "portal/investigation_start.html", {"document": document})

    turns = session.turns.order_by("turn_index")
    return render(request, "portal/document_conversation.html", {
        "document": document,
        "session": session,
        "turns": turns,
    })


@login_required
def document_conversation_submit(request: HttpRequest, document_id: uuid.UUID) -> HttpResponse:
    """POST /documents/<uuid>/ask/submit/ — HTMX partial for a new finding."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    document = get_object_or_404(Document, id=document_id, status=Document.Status.READY)
    query_text = request.POST.get("query", "").strip()

    if not query_text:
        return render(request, "portal/_conversation_turn.html", {"error": "Please enter a question."})

    if is_rate_limited(request.user.id):
        return render(
            request, "portal/_conversation_turn.html",
            {"error": "Too many questions in a short time. Please wait a moment and try again."},
        )
    record_request(request.user.id)

    session = get_or_create_active_session(document, request.user)

    try:
        turn = ask_in_session(session, query_text)
    except (RetrievalError, GenerationError) as exc:
        return render(request, "portal/_conversation_turn.html", {"error": str(exc)})

    finding_number = session.turns.count()
    return render(request, "portal/_conversation_turn.html", {
        "turn": turn,
        "finding_number": finding_number,
    })


@login_required
def document_conversation_clear(request: HttpRequest, document_id: uuid.UUID) -> HttpResponse:
    """POST /documents/<uuid>/ask/clear/"""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    document = get_object_or_404(Document, id=document_id, status=Document.Status.READY)
    try:
        session = DocumentSession.objects.get(document=document, user=request.user, is_active=True)
        clear_session(session)
    except DocumentSession.DoesNotExist:
        pass

    return redirect("document-conversation-page", document_id=document.id)


@login_required
def investigation_export_pdf(request: HttpRequest, document_id: uuid.UUID) -> HttpResponse:
    """GET /documents/<uuid>/ask/export.pdf"""
    from django.http import HttpResponse as DjangoHttpResponse
    from services.export.investigation_pdf import generate_investigation_pdf

    document = get_object_or_404(Document, id=document_id, status=Document.Status.READY)
    try:
        session = DocumentSession.objects.get(document=document, user=request.user, is_active=True)
    except DocumentSession.DoesNotExist:
        return redirect("document-conversation-page", document_id=document.id)

    try:
        pdf_bytes = generate_investigation_pdf(session)
    except Exception as exc:
        logger.error("investigation_pdf_export_failed session_id=%s error=%s", session.id, exc)
        return render(request, "portal/document_conversation.html", {
            "document": document,
            "session": session,
            "turns": session.turns.order_by("turn_index"),
            "export_error": "PDF generation failed. Please try again.",
        })

    safe_title = "".join(c if c.isalnum() or c in "- " else "_" for c in session.title)
    filename = f"SAGE_Investigation_{safe_title or 'Report'}.pdf"

    response = DjangoHttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _processing_duration_display(document: Document) -> str | None:
    """Human-readable elapsed time for a terminal document. None if still in progress."""
    if not document.is_terminal:
        return None
    delta = document.updated_at - document.created_at
    total_seconds = int(delta.total_seconds())
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}m {seconds}s" if minutes else f"{seconds}s"


logger = logging.getLogger("apps.portal.views")

class PortalLoginView(LoginView):
    template_name = "portal/login.html"

    def _log_attempt(self,request,ip: str,success: bool,failure_reason: str = "",) -> None:
        """
        Writes to both LoginAttempt (deprecated, for backward compatibility)
        and AuditLog (current). Once the LoginAttempt table is formally
        cleaned up, the first write can be removed.
        """
        from apps.portal.models import LoginAttempt
        from services.audit.audit_service import log_event

        username_attempted = request.POST.get("username", "")[:255]
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

        # Legacy write — deprecated but retained for historical continuity.
        LoginAttempt.objects.create(
            ip_address=ip,
            username_attempted=username_attempted,
            success=success,
            failure_reason=failure_reason,
            user_agent=user_agent,
        )

        # Current write — unified AuditLog.
        if success:
            log_event(
                event_type="auth_login_success",
                actor=request.user if request.user.is_authenticated else None,
                detail={"username": username_attempted},
                request=request,
            )
        else:
            log_event(
                event_type="auth_login_failure",
                severity="warning",
                detail={"username": username_attempted, "reason": failure_reason},
                request=request,
                ip_address=ip,
                user_agent=user_agent,
            )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ip = get_client_ip(self.request)

        custom_message = getattr(self, "_login_error_message", None)
        if custom_message:
            context["login_error_message"] = custom_message
        elif self.request.method == "POST" and context["form"].errors:
            context["login_error_message"] = "Incorrect username or password."

        context["is_locked_out"] = is_locked_out(ip)
        context["lockout_minutes"] = (lockout_remaining_seconds(ip) + 59) // 60

        context["challenge_required"] = challenge_required(ip) and not context["is_locked_out"]
        context["turnstile_site_key"] = settings.TURNSTILE_SITE_KEY
        context["show_fallback_challenge"] = getattr(self, "_show_fallback_challenge", False)
        if context["show_fallback_challenge"]:
            question, token = generate_challenge()
            context["fallback_challenge_question"] = question
            context["fallback_challenge_token"] = token

        return context

    def form_valid(self, form):
        ip = get_client_ip(self.request)

        # Layer 1: IP lockout — hardest block, checked first
        if is_locked_out(ip):
            self._login_error_message = (
                f"This IP address is temporarily locked. "
                f"Try again in {(lockout_remaining_seconds(ip) + 59) // 60} minute(s)."
            )
            self._log_attempt(self.request, ip, False, "locked_out")
            return self.form_invalid(form)

        # Layer 2: Honeypot — silent rejection
        if honeypot_triggered(self.request):
            logger.warning("honeypot_triggered ip=%s", ip)
            self._log_attempt(self.request, ip, False, "honeypot")
            self._login_error_message = "Incorrect username or password."
            return self.form_invalid(form)

        # Layer 3: Turnstile / fallback challenge
        if challenge_required(ip):
            fallback_answer = self.request.POST.get("fallback_challenge_answer", "")

            if fallback_answer:
                fallback_token = self.request.POST.get("fallback_challenge_token", "")
                if not verify_challenge(fallback_token, fallback_answer):
                    self._login_error_message = "Verification failed. Please try again."
                    self._log_attempt(self.request, ip, False, "fallback_failed")
                    return self.form_invalid(form)
            else:
                turnstile_token = self.request.POST.get("cf-turnstile-response", "")

                if not turnstile_token:
                    logger.info("turnstile_token_absent_offering_fallback ip=%s", ip)
                    self._show_fallback_challenge = True
                    self._login_error_message = "Please complete the verification below."
                    self._log_attempt(self.request, ip, False, "turnstile_absent")
                    return self.form_invalid(form)

                turnstile_result = verify_turnstile(turnstile_token, ip)

                if turnstile_result is False:
                    self._login_error_message = "Verification failed. Please complete the security check."
                    self._log_attempt(self.request, ip, False, "turnstile_rejected")
                    return self.form_invalid(form)

                if turnstile_result is None:
                    logger.warning("turnstile_unreachable_offering_fallback ip=%s", ip)
                    self._show_fallback_challenge = True
                    self._login_error_message = (
                        "Our verification service is temporarily unavailable. "
                        "Please answer the question below instead."
                    )
                    return self.form_invalid(form)

        # All layers passed
        self._log_attempt(self.request, ip, True)
        reset_failures(ip)
        return super().form_valid(form)

    def form_invalid(self, form):
        ip = get_client_ip(self.request)
        # Only record_failed_attempt for bad credentials (not for security-layer rejections
        # which logged their own attempts above).
        if not getattr(self, "_login_error_message", None):
            self._login_error_message = "Incorrect username or password."
            record_failed_attempt(ip)
            self._log_attempt(self.request, ip, False, "bad_credentials")
        else:
            # Security-layer rejection — still increment failure count.
            record_failed_attempt(ip)
        return super().form_invalid(form)


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
    from apps.chunks.models import ContentChunk
    document = get_object_or_404(Document, id=document_id)
    text_chunk_count = ContentChunk.objects.filter(
        document=document
    ).exclude(chunk_type=ContentChunk.ChunkType.CAPTION).count()
    return render(request, "portal/document_detail.html", {
        "document": document,
        "processing_duration": _processing_duration_display(document),
        "text_chunk_count": text_chunk_count,
    })


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

    rendered_answer = render_answer_with_numbered_citations(result)
    return render(
        request, "portal/_query_result.html",
        {"result": result, "rendered_answer": rendered_answer},
    )


def custom_404(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def custom_500(request: HttpRequest) -> HttpResponse:
    return render(request, "errors/500.html", status=500)


@login_required
def document_outline_page(request: HttpRequest, document_id: uuid.UUID) -> HttpResponse:
    """
    GET /documents/<uuid>/outline/

    Clause Navigator: hierarchical outline of sections and clauses extracted
    from section_identifier values already stored on ContentChunk records.
    """
    document = get_object_or_404(Document, id=document_id)
    outline = build_document_outline(document_id)
    flat_rows = flatten_for_template(outline.root_nodes)

    return render(request, "portal/document_outline.html", {
        "document": document,
        "outline": outline,
        "flat_rows": flat_rows,
    })


@login_required
def compliance_query_page(request: HttpRequest, document_id: uuid.UUID) -> HttpResponse:
    """GET /documents/<uuid>/compliance/"""
    document = get_object_or_404(Document, id=document_id, status=Document.Status.READY)
    return render(request, "portal/compliance_query.html", {"document": document})


@login_required
def compliance_submit(request: HttpRequest, document_id: uuid.UUID) -> HttpResponse:
    """
    POST /documents/<uuid>/compliance/submit/ — HTMX partial.

    Shares the portal rate limiter with the query and conversation pages —
    all three ultimately call Gemini; separate budgets per path would
    silently exceed the provider's actual ceiling.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    document = get_object_or_404(Document, id=document_id, status=Document.Status.READY)
    requirement = request.POST.get("requirement", "").strip()

    if not requirement:
        return render(request, "portal/_compliance_result.html",
                      {"error": "Please enter a requirement to verify."})

    if is_rate_limited(request.user.id):
        return render(request, "portal/_compliance_result.html",
                      {"error": "Too many requests. Please wait a moment and try again."})
    record_request(request.user.id)

    try:
        result = generate_compliance_answer(
            requirement=requirement,
            document_ids=[document.id],
        )
    except (RetrievalError, GenerationError) as exc:
        return render(request, "portal/_compliance_result.html", {"error": str(exc)})

    return render(request, "portal/_compliance_result.html",
                  {"result": result, "document": document})
    

@login_required
def comparison_page(request: HttpRequest) -> HttpResponse:
    """
    GET /comparison/

    Cross-document comparison entry point. Accepts ?document_a=<uuid> and
    ?document_b=<uuid> to pre-select documents when navigating from a
    document detail page.
    """
    ready_documents = Document.objects.filter(
        status=Document.Status.READY
    ).order_by("name")

    return render(request, "portal/comparison.html", {
        "ready_documents": ready_documents,
        "preselect_a": request.GET.get("document_a", ""),
        "preselect_b": request.GET.get("document_b", ""),
    })


@login_required
def comparison_submit(request: HttpRequest) -> HttpResponse:
    """POST /comparison/submit/ — HTMX partial for comparison results."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    query = request.POST.get("query", "").strip()
    doc_a_str = request.POST.get("document_a_id", "").strip()
    doc_b_str = request.POST.get("document_b_id", "").strip()

    if not query:
        return render(request, "portal/_comparison_result.html",
                      {"error": "Please enter a comparison query."})

    if not doc_a_str or not doc_b_str:
        return render(request, "portal/_comparison_result.html",
                      {"error": "Please select both documents to compare."})

    try:
        doc_a_id = uuid.UUID(doc_a_str)
        doc_b_id = uuid.UUID(doc_b_str)
    except ValueError:
        return render(request, "portal/_comparison_result.html",
                      {"error": "Invalid document selection."})

    if doc_a_id == doc_b_id:
        return render(request, "portal/_comparison_result.html",
                      {"error": "Please select two different documents."})

    if is_rate_limited(request.user.id):
        return render(request, "portal/_comparison_result.html",
                      {"error": "Too many requests. Please wait a moment and try again."})
    record_request(request.user.id)

    try:
        result = generate_comparison_answer(
            query=query,
            document_a_id=doc_a_id,
            document_b_id=doc_b_id,
        )
    except (RetrievalError, GenerationError) as exc:
        return render(request, "portal/_comparison_result.html", {"error": str(exc)})
    except Exception as exc:
        logger.error("comparison_submit_error query=%r error=%s", query, exc)
        return render(request, "portal/_comparison_result.html",
                      {"error": "An unexpected error occurred. Please try again."})

    return render(request, "portal/_comparison_result.html", {"result": result})

@login_required
def clause_investigation_history_partial(
    request: HttpRequest,
    document_id: uuid.UUID,
    section_identifier: str,
) -> HttpResponse:
    """
    GET /documents/<uuid>/clause/<str:section_identifier>/history/

    HTMX partial — returns investigation history for one clause.
    section_identifier arrives URL-encoded (e.g. "4.3.2"); decode it.
    """
    import urllib.parse
    section_identifier = urllib.parse.unquote(section_identifier)
    document = get_object_or_404(Document, id=document_id)
    history = get_clause_investigation_history(document.id, section_identifier)

    return render(request, "portal/_clause_history.html", {
        "document": document,
        "section_identifier": section_identifier,
        "history": history,
    })
    
@login_required
def serve_media_file(request: HttpRequest, path: str) -> HttpResponse:
    """
    Authenticated media file serving.

    Replaces Django's static() URL helper (which only works with runserver
    + DEBUG=True) with a view that works in all modes including gunicorn
    over HTTPS. Authentication is enforced — no media file is accessible
    without a valid session.

    Path traversal is prevented by resolving the absolute path and
    confirming it sits within MEDIA_ROOT before opening.
    """
    from django.conf import settings

    media_root = Path(settings.MEDIA_ROOT).resolve()
    requested = (media_root / path).resolve()

    # Prevent path traversal attacks
    try:
        requested.relative_to(media_root)
    except ValueError:
        raise Http404

    if not requested.exists() or not requested.is_file():
        raise Http404

    content_type, _ = mimetypes.guess_type(str(requested))
    content_type = content_type or "application/octet-stream"

    response = FileResponse(
        open(requested, "rb"),
        content_type=content_type,
    )
    # Allow inline display in browser (for images and PDFs)
    filename = requested.name
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Content-Length"] = requested.stat().st_size
    return response

