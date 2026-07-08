# services/documents/clause_navigator.py
"""
Builds a hierarchical document outline from ContentChunk.section_identifier data.

Pure aggregation — no DB writes, no new models.

Design rationale:
    ContentChunk.section_identifier already stores parsed clause identifiers
    (e.g. "4.3.2") for every text chunk. This service groups, normalises,
    and tree-structures those identifiers, then annotates each node with a
    citation count derived from ConversationTurn.citations (JSON field).
    The result is a navigable document outline that reflects both the
    structural content and the investigation history for each clause.

Limitations:
    - Identifiers must be numeric dot-notation once prefixes are stripped.
      ("Clause 4.3.2", "Section 7.1", "4.3.2" → all normalise cleanly;
      lettered sub-clauses like "4.3.2(a)" do not and are excluded.)
    - Citation count aggregates from the Python side after fetching turns,
      because querying into a JSON array in Django without raw SQL is
      impractical for this scale. Fine for typical investigation volumes.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

_PREFIX_PATTERN = re.compile(
    r"^(?:clause|section|cl\.?|sec\.?)\s+", re.IGNORECASE
)


@dataclass
class ClauseNode:
    """One node in the document clause hierarchy."""

    identifier: str        # normalised, e.g. "4.3.2"
    depth: int             # 0 = top-level section
    chunk_count: int = 0
    citation_count: int = 0
    first_chunk_excerpt: str = ""
    first_chunk_id: uuid.UUID | None = None
    children: list["ClauseNode"] = field(default_factory=list)

    @property
    def css_id(self) -> str:
        """Safe HTML id: "4.3.2" → "clause-4-3-2"."""
        return f"clause-{self.identifier.replace('.', '-')}"


@dataclass
class DocumentOutline:
    document_id: uuid.UUID
    root_nodes: list[ClauseNode]
    total_clauses: int
    total_citations: int
    has_clauses: bool


def normalize_identifier(raw: str) -> str | None:
    """
    Returns a purely numeric dot-separated identifier, or None if the raw
    value cannot be reduced to that form.
    """
    cleaned = _PREFIX_PATTERN.sub("", raw.strip())
    return cleaned if re.match(r"^\d+(\.\d+)*$", cleaned) else None


def _sort_key(identifier: str) -> list[int]:
    return [int(p) for p in identifier.split(".")]


def _parent_identifier(identifier: str) -> str | None:
    parts = identifier.rsplit(".", 1)
    return parts[0] if len(parts) > 1 else None


def flatten_for_template(nodes: list[ClauseNode]) -> list[dict]:
    """
    Returns a flat list suitable for a Django template {% for %} loop.
    Each item carries the node plus rendering helpers (indent, collapse id).
    """
    result: list[dict] = []

    def _traverse(node_list: list[ClauseNode]) -> None:
        for node in node_list:
            result.append({
                "node": node,
                "has_children": bool(node.children),
                "indent_rem": node.depth * 1.4,
                "collapse_id": node.css_id,
            })
            _traverse(node.children)

    _traverse(nodes)
    return result


def build_document_outline(document_id: uuid.UUID) -> DocumentOutline:
    """
    Builds a hierarchical outline of clauses for a document.

    Steps:
        1. Fetch all non-caption ContentChunks with section_identifier set.
        2. Normalise and group identifiers → chunk counts.
        3. Count citations per clause from ConversationTurn.citations (JSON).
        4. Build a ClauseNode tree and sort it numerically.
    """
    from apps.chunks.models import ContentChunk
    from apps.conversation.models import ConversationTurn, DocumentSession

    chunks = list(
        ContentChunk.objects
        .filter(document_id=document_id, section_identifier__isnull=False)
        .exclude(section_identifier="")
        .exclude(chunk_type=ContentChunk.ChunkType.CAPTION)
        .order_by("chunk_index")
        .values("id", "section_identifier", "chunk_text")
    )

    node_data: dict[str, dict] = {}
    for chunk in chunks:
        normalized = normalize_identifier(chunk["section_identifier"])
        if normalized is None:
            continue
        if normalized not in node_data:
            node_data[normalized] = {
                "chunk_count": 0,
                "first_chunk_id": chunk["id"],
                "first_chunk_excerpt": chunk["chunk_text"][:250],
            }
        node_data[normalized]["chunk_count"] += 1

    if not node_data:
        return DocumentOutline(
            document_id=document_id, root_nodes=[],
            total_clauses=0, total_citations=0, has_clauses=False,
        )

    citation_counts: dict[str, int] = defaultdict(int)
    sessions = DocumentSession.objects.filter(document_id=document_id)
    for turn in ConversationTurn.objects.filter(session__in=sessions).values("citations"):
        for citation in turn["citations"] or []:
            section = citation.get("section_identifier")
            if section:
                normalized = normalize_identifier(section)
                if normalized:
                    citation_counts[normalized] += 1

    sorted_ids = sorted(node_data.keys(), key=_sort_key)
    nodes: dict[str, ClauseNode] = {}
    for identifier in sorted_ids:
        data = node_data[identifier]
        nodes[identifier] = ClauseNode(
            identifier=identifier,
            depth=identifier.count("."),
            chunk_count=data["chunk_count"],
            citation_count=citation_counts.get(identifier, 0),
            first_chunk_excerpt=data["first_chunk_excerpt"],
            first_chunk_id=data["first_chunk_id"],
        )

    root_nodes: list[ClauseNode] = []
    for identifier, node in nodes.items():
        parent_id = _parent_identifier(identifier)
        if parent_id and parent_id in nodes:
            nodes[parent_id].children.append(node)
        else:
            root_nodes.append(node)

    def _sort_recursive(node_list: list[ClauseNode]) -> None:
        node_list.sort(key=lambda n: _sort_key(n.identifier))
        for n in node_list:
            _sort_recursive(n.children)

    _sort_recursive(root_nodes)

    return DocumentOutline(
        document_id=document_id,
        root_nodes=root_nodes,
        total_clauses=len(nodes),
        total_citations=sum(citation_counts.values()),
        has_clauses=True,
    )