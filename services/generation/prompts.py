# services/generation/prompts.py
"""
System prompt and context-assembly helpers for citation-grounded generation.

The [CITE:chunk_id] marker format defined here is the contract that
citation_validator.py's regex parses against. Changing the format
requires updating both files together.
"""

from __future__ import annotations

from services.retrieval.retrieval_service import RetrievedChunk

SYSTEM_PROMPT = """You are an engineering document assistant. Answer the user's question using only the provided context chunks.

Rules:
1. For every factual claim, insert [CITE:chunk_id] immediately after the claim, using the exact chunk_id shown in the context below.
   Example: "The minimum tensile strength shall not be less than 720 MPa. [CITE:123e4567-e89b-12d3-a456-426614174000]"
2. Use only the chunk_ids provided in the context. Do not invent chunk_ids.
3. If the context does not contain sufficient information to answer the question, respond exactly:
   "The provided documents do not contain sufficient information to answer this question."
4. Do not speculate beyond the provided context. Do not add general engineering knowledge not present in the context.
5. Multiple citations per sentence are permitted when a claim draws on more than one source.
"""


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    """
    Formats retrieved chunks into the context block included in the user prompt.

    Each chunk is labeled with its chunk_id so the model can reference it
    exactly via [CITE:chunk_id]. No token budgeting is applied — retrieval's
    top_k already bounds the number of chunks.
    """
    if not chunks:
        return ""

    sections = []
    for chunk in chunks:
        section_label = f" | Section {chunk.section_identifier}" if chunk.section_identifier else ""
        sections.append(
            f"[CHUNK_ID: {chunk.chunk_id}]\n"
            f"Page {chunk.page_number}{section_label}\n"
            f"{chunk.chunk_text}"
        )

    return "\n---\n".join(sections)


def build_user_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    """Assembles the full user-turn prompt: context block + the question."""
    context_block = build_context_block(chunks)
    return f"Context:\n{context_block}\n\nQuestion: {query}"