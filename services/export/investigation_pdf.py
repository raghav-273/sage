# services/export/investigation_pdf.py
"""
Generates a formal PDF investigation report from a DocumentSession.

Uses reportlab (pure Python — no system library dependencies, unlike
weasyprint which requires libcairo). The output is an A4 engineering
evidence report suitable for attaching to project records or compliance
documentation.
"""

from __future__ import annotations

import datetime
from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.conversation.models import ConversationTurn, DocumentSession


def _status_label(turn: ConversationTurn) -> str:
    if turn.has_valid_citations:
        return "VERIFIED"
    elif turn.retrieved_chunk_count > 0:
        return "UNVERIFIED"
    return "NOT FOUND"


def generate_investigation_pdf(session: DocumentSession) -> bytes:
    """
    Returns the investigation report as PDF bytes.

    Raises ImportError if reportlab is not installed (signals a
    missing dependency rather than silently returning empty content).
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    NAVY = colors.HexColor("#1f2d3d")
    ACCENT = colors.HexColor("#2563eb")
    LIGHT_GREY = colors.HexColor("#f4f5f7")
    MID_GREY = colors.HexColor("#6c757d")
    GREEN = colors.HexColor("#1e7e34")
    AMBER = colors.HexColor("#8a6d1d")
    RED = colors.HexColor("#a72a1f")

    base_styles = getSampleStyleSheet()

    styles = {
        "institution": ParagraphStyle(
            "institution", fontName="Helvetica-Bold", fontSize=14,
            textColor=NAVY, spaceAfter=2,
        ),
        "report_type": ParagraphStyle(
            "report_type", fontName="Helvetica", fontSize=9,
            textColor=MID_GREY, spaceAfter=16, letterSpacing=1,
        ),
        "section_label": ParagraphStyle(
            "section_label", fontName="Helvetica-Bold", fontSize=7,
            textColor=MID_GREY, spaceAfter=4, letterSpacing=1,
        ),
        "meta_value": ParagraphStyle(
            "meta_value", fontName="Helvetica", fontSize=9,
            textColor=NAVY, spaceAfter=2,
        ),
        "finding_label": ParagraphStyle(
            "finding_label", fontName="Helvetica-Bold", fontSize=8,
            textColor=colors.white, spaceAfter=0,
        ),
        "question": ParagraphStyle(
            "question", fontName="Helvetica-Bold", fontSize=10,
            textColor=NAVY, spaceAfter=6,
        ),
        "status_verified": ParagraphStyle(
            "status_verified", fontName="Helvetica-Bold", fontSize=8,
            textColor=GREEN, spaceAfter=8,
        ),
        "status_unverified": ParagraphStyle(
            "status_unverified", fontName="Helvetica-Bold", fontSize=8,
            textColor=AMBER, spaceAfter=8,
        ),
        "status_notfound": ParagraphStyle(
            "status_notfound", fontName="Helvetica-Bold", fontSize=8,
            textColor=RED, spaceAfter=8,
        ),
        "answer": ParagraphStyle(
            "answer", fontName="Helvetica", fontSize=9,
            textColor=colors.black, leading=14, spaceAfter=8,
        ),
        "ref_label": ParagraphStyle(
            "ref_label", fontName="Helvetica-Bold", fontSize=7,
            textColor=MID_GREY, spaceAfter=4, letterSpacing=1,
        ),
        "ref_item": ParagraphStyle(
            "ref_item", fontName="Courier", fontSize=8,
            textColor=colors.black, spaceAfter=2, leftIndent=12,
        ),
        "ref_excerpt": ParagraphStyle(
            "ref_excerpt", fontName="Helvetica-Oblique", fontSize=8,
            textColor=MID_GREY, spaceAfter=6, leftIndent=12,
        ),
        "footer": ParagraphStyle(
            "footer", fontName="Helvetica", fontSize=7,
            textColor=MID_GREY, alignment=TA_CENTER,
        ),
    }

    buffer = BytesIO()
    turns = list(session.turns.order_by("turn_index"))

    def _add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MID_GREY)
        page_text = f"Page {canvas.getPageNumber()}"
        canvas.drawRightString(A4[0] - 2.5 * cm, 1.2 * cm, page_text)
        canvas.drawString(
            2.5 * cm, 1.2 * cm,
            "SAGE Engineering Evidence System — Investigation Report"
        )
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2.5 * cm,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
    )

    story = []

    # ── Header ──────────────────────────────────────────────────────────
    story.append(Paragraph("SAGE", styles["institution"]))
    story.append(Paragraph("STANDARDS AND GUIDELINES ENGINE", styles["report_type"]))
    story.append(HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=12))

    report_title = Paragraph(
        "INVESTIGATION REPORT",
        ParagraphStyle("rt", fontName="Helvetica-Bold", fontSize=16,
                       textColor=NAVY, alignment=TA_CENTER, spaceAfter=16),
    )
    story.append(report_title)

    # ── Metadata table ───────────────────────────────────────────────────
    meta_rows = [
        ["Investigation", session.title or "Untitled"],
        ["Document", session.document.name],
        ["Analyst", session.user.username],
        ["Started", session.created_at.strftime("%Y-%m-%d %H:%M")],
        ["Generated", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")],
        ["Total Findings", str(len(turns))],
    ]

    meta_data = [
        [
            Paragraph(row[0], styles["section_label"]),
            Paragraph(row[1], styles["meta_value"]),
        ]
        for row in meta_rows
    ]

    meta_table = Table(meta_data, colWidths=[4 * cm, 12 * cm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#dee2e6")),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.8 * cm))

    if not turns:
        story.append(Paragraph(
            "No findings have been recorded in this investigation.",
            ParagraphStyle("empty", fontName="Helvetica-Oblique", fontSize=9,
                           textColor=MID_GREY, alignment=TA_CENTER),
        ))
    else:
        story.append(HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=12))

    # ── Findings ─────────────────────────────────────────────────────────
    for i, turn in enumerate(turns, start=1):
        # Finding header
        finding_header = Table(
            [[Paragraph(f"FINDING {i}", styles["finding_label"])]],
            colWidths=[16 * cm],
        )
        finding_header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(finding_header)
        story.append(Spacer(1, 0.2 * cm))

        # Question
        story.append(Paragraph(turn.query_text, styles["question"]))

        # Status
        status = _status_label(turn)
        if status == "VERIFIED":
            story.append(Paragraph("✓ VERIFIED — Evidence supports this finding.", styles["status_verified"]))
        elif status == "UNVERIFIED":
            story.append(Paragraph("⚠ UNVERIFIED — No citation could be validated.", styles["status_unverified"]))
        else:
            story.append(Paragraph("✗ NOT FOUND — Insufficient evidence in the document.", styles["status_notfound"]))

        # Answer
        story.append(Paragraph(turn.answer_text, styles["answer"]))

        # Citations
        citations = turn.citations or []
        if citations:
            story.append(Paragraph("REFERENCES", styles["ref_label"]))
            for j, citation in enumerate(citations, start=1):
                page = citation.get("page_number", "?")
                section = citation.get("section_identifier", "")
                excerpt = citation.get("excerpt", "")
                ref_line = f"[{j}] Page {page}"
                if section:
                    ref_line += f", Section {section}"
                story.append(Paragraph(ref_line, styles["ref_item"]))
                if excerpt:
                    story.append(Paragraph(f'"{excerpt[:160]}..."' if len(excerpt) > 160 else f'"{excerpt}"',
                                           styles["ref_excerpt"]))

        story.append(Spacer(1, 0.4 * cm))
        story.append(HRFlowable(
            width="100%", thickness=0.5,
            color=colors.HexColor("#dee2e6"), spaceAfter=8,
        ))

    doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
    return buffer.getvalue()