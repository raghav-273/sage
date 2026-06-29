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