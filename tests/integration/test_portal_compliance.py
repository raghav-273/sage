# tests/integration/test_portal_compliance.py
"""Integration tests for the Compliance Verification view."""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.documents.models import Document
from services.generation.generation_service import ComplianceResult


def _make_compliance_result(verdict: str = "COMPLIANT") -> ComplianceResult:
    from services.generation.citation_validator import Citation
    citation_id = uuid.uuid4()
    citations = [
        Citation(
            chunk_id=citation_id, document_id=uuid.uuid4(), page_number=42,
            section_identifier="4.3.2",
            excerpt="The minimum tensile strength shall not be less than 720 MPa.",
            confidence_score=0.91, retrieval_method="hybrid", image_path=None,
        )
    ] if verdict != "INSUFFICIENT EVIDENCE" else []
    return ComplianceResult(
        requirement="The proposed design uses fish plates with 720 MPa tensile strength.",
        verdict=verdict,
        answer_text=f"VERDICT: {verdict}\n\nReasoning. [CITE:{citation_id}]",
        rendered_answer=f"VERDICT: {verdict}\n\nReasoning. [1]",
        citations=citations,
        has_valid_citations=bool(citations),
        retrieved_chunk_count=1,
        rejected_citation_count=0,
    )


class ComplianceQueryPageTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="reviewer", password="test-pass-123")
        self.client.login(username="reviewer", password="test-pass-123")
        self.document = Document.objects.create(
            name="RDSO Spec", original_filename="rdso.pdf",
            file_path="documents/rdso.pdf", file_size_bytes=1,
            status=Document.Status.READY,
        )

    def test_page_loads(self) -> None:
        response = self.client.get(reverse("compliance-query-page", args=[self.document.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Compliance Verification")

    def test_non_ready_document_returns_404(self) -> None:
        pending_doc = Document.objects.create(
            name="Pending", original_filename="p.pdf",
            file_path="documents/p.pdf", file_size_bytes=1,
            status=Document.Status.PENDING,
        )
        response = self.client.get(reverse("compliance-query-page", args=[pending_doc.id]))
        self.assertEqual(response.status_code, 404)

    @mock.patch("apps.portal.views.generate_compliance_answer")
    def test_compliant_verdict_renders_green(self, mock_gen) -> None:
        mock_gen.return_value = _make_compliance_result("COMPLIANT")
        response = self.client.post(
            reverse("compliance-submit", args=[self.document.id]),
            {"requirement": "Fish plates at 720 MPa"},
        )
        self.assertContains(response, "COMPLIANT")
        self.assertContains(response, "badge-verified")

    @mock.patch("apps.portal.views.generate_compliance_answer")
    def test_non_compliant_verdict_renders_red(self, mock_gen) -> None:
        mock_gen.return_value = _make_compliance_result("NON-COMPLIANT")
        response = self.client.post(
            reverse("compliance-submit", args=[self.document.id]),
            {"requirement": "Fish plates at 680 MPa"},
        )
        self.assertContains(response, "NON-COMPLIANT")
        self.assertContains(response, "badge-not-found")

    @mock.patch("apps.portal.views.generate_compliance_answer")
    def test_insufficient_evidence_renders_amber(self, mock_gen) -> None:
        mock_gen.return_value = _make_compliance_result("INSUFFICIENT EVIDENCE")
        response = self.client.post(
            reverse("compliance-submit", args=[self.document.id]),
            {"requirement": "An obscure requirement"},
        )
        self.assertContains(response, "INSUFFICIENT EVIDENCE")
        self.assertContains(response, "badge-unverified")

    def test_empty_requirement_rejected(self) -> None:
        with mock.patch("apps.portal.views.generate_compliance_answer") as mock_gen:
            response = self.client.post(
                reverse("compliance-submit", args=[self.document.id]),
                {"requirement": "   "},
            )
            mock_gen.assert_not_called()
        self.assertContains(response, "Please enter a requirement")

    @mock.patch("apps.portal.views.generate_compliance_answer")
    def test_rate_limit_blocks_after_threshold(self, mock_gen) -> None:
        mock_gen.return_value = _make_compliance_result()
        for _ in range(8):
            self.client.post(
                reverse("compliance-submit", args=[self.document.id]),
                {"requirement": "a requirement"},
            )
        response = self.client.post(
            reverse("compliance-submit", args=[self.document.id]),
            {"requirement": "one more"},
        )
        self.assertContains(response, "Too many requests")

    def test_anonymous_access_redirects_to_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("compliance-query-page", args=[self.document.id]))
        self.assertEqual(response.status_code, 302)