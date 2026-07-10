# services/generation/prompts.py
"""
System prompt and context-assembly helpers for citation-grounded generation.

The [CITE:chunk_id] marker format defined here is the contract that
citation_validator.py's regex parses against. The context label below
is deliberately NOT bracket-shaped like the citation marker itself
(Source ID, not [CHUNK_ID: ...]) — an earlier version used a bracketed
label visually similar to the citation tag, which is suspected to have
caused the model to copy that format (including its space after the
colon) rather than the instructed marker format. See project history
for the incident this was found from.
"""

from __future__ import annotations

from services.retrieval.retrieval_service import RetrievedChunk

SYSTEM_PROMPT = """You are an engineering document assistant. Answer the user's question using only the provided context chunks.

Rules:
1. For every factual claim, insert a citation marker immediately after the claim, in EXACTLY this format, with no space after the colon:
   [CITE:source_id]
   Copy the Source ID value shown in the context below character-for-character. Do not add a space inside the brackets, and do not use any other format.
   Example: "The minimum tensile strength shall not be less than 720 MPa. [CITE:123e4567-e89b-12d3-a456-426614174000]"
2. Use only the Source IDs provided in the context. Do not invent IDs.
3. If the context does not contain sufficient information to answer the question, respond exactly:
   "The provided documents do not contain sufficient information to answer this question."
4. Do not speculate beyond the provided context. Do not add general engineering knowledge not present in the context.
5. Multiple citations per sentence are permitted when a claim draws on more than one source.
"""


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    """Formats retrieved chunks into the context block included in the user prompt."""
    if not chunks:
        return ""

    sections = []
    for chunk in chunks:
        section_label = f" | Section {chunk.section_identifier}" if chunk.section_identifier else ""
        sections.append(
            f"Source ID: {chunk.chunk_id}\n"
            f"Page {chunk.page_number}{section_label}\n"
            f"{chunk.chunk_text}"
        )

    return "\n---\n".join(sections)


def build_user_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    """Assembles the full user-turn prompt: context block + the question."""
    context_block = build_context_block(chunks)
    return f"Context:\n{context_block}\n\nQuestion: {query}"


# Added to the bottom of the existing file:

CONVERSATIONAL_SYSTEM_PROMPT = SYSTEM_PROMPT + (
    "\n6. A \"Previous conversation\" section may appear before the Context "
    "below. It exists only to help you understand follow-up questions "
    "(e.g. \"what about its safety margin?\"). Citations must still come "
    "only from the Context chunks — never from the previous conversation "
    "itself."
)


def build_conversational_user_prompt(
    query: str,
    chunks: list[RetrievedChunk],
    prior_turns: list[tuple[str, str]],
) -> str:
    """
    Same as build_user_prompt, with prior conversation turns prepended.

    Retrieval itself does NOT see prior_turns — only the raw follow-up
    text is embedded and searched (a deliberate, accepted trade-off; see
    Milestone 13B design notes — query rewriting before retrieval would
    handle pronoun-heavy follow-ups more robustly, at the cost of one
    extra Gemini call per turn on a provider already known to have
    capacity issues).
    """
    context_block = build_context_block(chunks)

    history_block = ""
    if prior_turns:
        history_lines = [f"User: {q}\nAssistant: {a}" for q, a in prior_turns]
        history_block = (
            "Previous conversation in this session:\n"
            + "\n---\n".join(history_lines)
            + "\n\n"
        )

    return f"{history_block}Context:\n{context_block}\n\nQuestion: {query}"


COMPLIANCE_SYSTEM_PROMPT = """You are an engineering compliance verification assistant.

Your task: determine whether the provided requirement, design statement, or technical specification COMPLIES with the engineering standards documented in the context below.

Rules:
1. Your FIRST line must be exactly one of:
   VERDICT: COMPLIANT
   VERDICT: NON-COMPLIANT
   VERDICT: INSUFFICIENT EVIDENCE
2. After the verdict, provide 2-4 sentences of reasoning referencing specific clauses.
3. For every factual claim, insert [CITE:{chunk_id}] immediately after it, using the Source IDs in the context. No spaces inside the marker.
4. Use only the Source IDs provided. Do not invent IDs.
5. COMPLIANT: the requirement is fully supported by the documented standard.
   NON-COMPLIANT: the requirement contradicts or falls below the documented standard.
   INSUFFICIENT EVIDENCE: the documents do not contain enough information to determine compliance.
"""


def build_compliance_user_prompt(requirement: str, chunks) -> str:
    """Assembles the compliance-check prompt: context block + requirement."""
    context_block = build_context_block(chunks)
    return f"Context:\n{context_block}\n\nRequirement to verify:\n{requirement}"



COMPARISON_SYSTEM_PROMPT = """You are an engineering document comparison assistant.

The context below contains chunks from TWO documents, clearly labeled DOCUMENT A and DOCUMENT B.

Your task: compare both documents' treatment of the query topic.

Structure your response using EXACTLY these four section headers, each on its own line, with the ## prefix:
## Agreements
## Conflicts
## Only in Document A
## Only in Document B

Rules:
1. For every factual claim, insert [CITE:{chunk_id}] immediately after it, using the Source IDs shown in the context. No space inside the marker.
2. Use only the Source IDs provided. Do not invent IDs.
3. If a section has no relevant content, write: "None identified in the retrieved clauses."
4. Do not speculate beyond the provided context.
5. Be specific — reference clause identifiers, measured values, and tolerances where visible.
6. Same value appearing in both documents → Agreements. Differing values or contradictory requirements → Conflicts.
"""


def build_comparison_context_block(
    chunks_a: list,
    doc_a_name: str,
    chunks_b: list,
    doc_b_name: str,
) -> str:
    """
    Builds a context block that clearly separates Document A and Document B chunks
    so the model can attribute each citation to the correct source.
    """

    def _format_chunk(chunk) -> str:
        section_label = (
            f" | Section {chunk.section_identifier}" if chunk.section_identifier else ""
        )
        return (
            f"Source ID: {chunk.chunk_id}\n"
            f"Page {chunk.page_number}{section_label}\n"
            f"{chunk.chunk_text}"
        )

    parts = []

    if chunks_a:
        parts.append(
            f"=== DOCUMENT A: {doc_a_name} ===\n"
            + "\n---\n".join(_format_chunk(c) for c in chunks_a)
        )
    else:
        parts.append(
            f"=== DOCUMENT A: {doc_a_name} ===\n"
            "(No relevant clauses retrieved for this document.)"
        )

    if chunks_b:
        parts.append(
            f"=== DOCUMENT B: {doc_b_name} ===\n"
            + "\n---\n".join(_format_chunk(c) for c in chunks_b)
        )
    else:
        parts.append(
            f"=== DOCUMENT B: {doc_b_name} ===\n"
            "(No relevant clauses retrieved for this document.)"
        )

    return "\n\n".join(parts)


def build_comparison_user_prompt(
    query: str,
    chunks_a: list,
    doc_a_name: str,
    chunks_b: list,
    doc_b_name: str,
) -> str:
    context_block = build_comparison_context_block(
        chunks_a, doc_a_name, chunks_b, doc_b_name
    )
    return f"Context:\n{context_block}\n\nComparison query: {query}"