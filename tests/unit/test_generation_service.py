# tests/unit/test_generation_service.py
"""
Unit tests for services.generation.generation_service.

Uses TransactionTestCase, not TestCase: generate_answer() calls retrieve(),
which runs vector_search and keyword_search concurrently in separate
threads via ThreadPoolExecutor, each with its own DB connection.
TestCase's uncommitted-transaction isolation makes fixture data invisible
to those other connections; TransactionTestCase commits it.

Fake GenerationClient and EmbeddingClient are injected throughout — these
tests must never call Gemini or load the real embedding model.
"""

from __future__ import annotations

import os
import unittest
import uuid
from unittest import mock

from django.test import TransactionTestCase

from apps.chunks.models import ContentChunk
from apps.documents.models import Document, DocumentPage
from services.generation.generation_service import generate_answer
from services.llm_client.base import EmbeddingClient
from services.llm_client.generation_base import (
    GenerationClient,
    GenerationError,
    get_generation_client,
)

DIM = 384


def _one_hot(index: int) -> list[float]:
    vec = [0.0] * DIM
    vec[index] = 1.0
    return vec


class _FakeEmbeddingClient(EmbeddingClient):
    EMBEDDING_DIMENSIONS = DIM

    def __init__(self, fixed_vector: list[float]) -> None:
        self._fixed_vector = fixed_vector

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        return [self._fixed_vector for _ in batch]


class _FakeGenerationClient(GenerationClient):
    """Returns a fixed response, regardless of prompt. Records prompts for inspection."""

    def __init__(self, fixed_response: str) -> None:
        self._fixed_response = fixed_response
        self.last_system_prompt: str | None = None
        self.last_user_prompt: str | None = None

    def _generate_once(
        self, system_prompt: str, user_prompt: str, temperature: float, max_output_tokens: int
    ) -> str:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        return self._fixed_response


def _make_document(status: str = Document.Status.READY) -> Document:
    return Document.objects.create(
        name="test-doc", original_filename="test.pdf",
        file_path="documents/test.pdf", file_size_bytes=100, status=status,
    )


def _make_page(document: Document, page_number: int = 1) -> DocumentPage:
    return DocumentPage.objects.create(document=document, page_number=page_number, raw_text="text")


def _make_chunk(
    document: Document, page: DocumentPage, chunk_index: int, chunk_text: str, embedding: list[float]
) -> ContentChunk:
    return ContentChunk.objects.create(
        document=document, page=page, chunk_index=chunk_index, chunk_text=chunk_text, embedding=embedding,
    )


class GenerateAnswerTests(TransactionTestCase):
    def setUp(self) -> None:
        self.document = _make_document()
        self.page = _make_page(self.document)
        self.chunk = _make_chunk(
            self.document, self.page, 0,
            "The minimum tensile strength for rail joints is 720 MPa.",
            embedding=_one_hot(0),
        )
        self.embedding_client = _FakeEmbeddingClient(_one_hot(0))

    def test_empty_retrieval_skips_generation(self) -> None:
        generation_client = _FakeGenerationClient("should never be returned")
        nonexistent_document_id = uuid.uuid4()

        result = generate_answer(
            "tensile strength",
            document_ids=[nonexistent_document_id],
            generation_client=generation_client,
            embedding_client=self.embedding_client,
        )

        self.assertEqual(result.answer_text, "")
        self.assertEqual(result.citations, [])
        self.assertFalse(result.has_valid_citations)
        self.assertEqual(result.retrieved_chunk_count, 0)
        self.assertIsNone(generation_client.last_user_prompt)  # generate() never called

    def test_valid_citation_passes_through(self) -> None:
        fixed_response = f"720 MPa is required. [CITE:{self.chunk.id}]"
        generation_client = _FakeGenerationClient(fixed_response)

        result = generate_answer(
            "tensile strength", generation_client=generation_client, embedding_client=self.embedding_client,
        )

        self.assertEqual(result.answer_text, fixed_response)
        self.assertTrue(result.has_valid_citations)
        self.assertEqual(len(result.citations), 1)
        self.assertEqual(result.citations[0].chunk_id, self.chunk.id)
        self.assertEqual(result.rejected_citation_count, 0)
        self.assertEqual(result.retrieved_chunk_count, 1)

    def test_invalid_citation_is_rejected(self) -> None:
        fake_id = uuid.uuid4()
        fixed_response = f"720 MPa is required. [CITE:{fake_id}]"
        generation_client = _FakeGenerationClient(fixed_response)

        result = generate_answer(
            "tensile strength", generation_client=generation_client, embedding_client=self.embedding_client,
        )

        self.assertEqual(result.citations, [])
        self.assertEqual(result.rejected_citation_count, 1)

    def test_zero_valid_citations_sets_flag_false(self) -> None:
        generation_client = _FakeGenerationClient("An answer with no citation markers.")

        result = generate_answer(
            "tensile strength", generation_client=generation_client, embedding_client=self.embedding_client,
        )

        self.assertFalse(result.has_valid_citations)
        self.assertEqual(result.citations, [])

    def test_retrieved_chunks_are_passed_into_prompt(self) -> None:
        generation_client = _FakeGenerationClient(f"answer [CITE:{self.chunk.id}]")

        generate_answer(
            "tensile strength", generation_client=generation_client, embedding_client=self.embedding_client,
        )

        self.assertIn(str(self.chunk.id), generation_client.last_user_prompt)
        self.assertIn("tensile strength", generation_client.last_user_prompt)


class GetGenerationClientFactoryTests(unittest.TestCase):
    """
    Tests the GENERATION_PROVIDER environment-driven factory in
    generation_base.py. Pure env-var logic — no database needed, so this
    uses plain unittest.TestCase rather than a Django test case.
    """

    def test_unset_provider_raises(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GENERATION_PROVIDER", None)
            with self.assertRaises(GenerationError):
                get_generation_client()

    def test_unsupported_provider_raises(self) -> None:
        with mock.patch.dict(os.environ, {"GENERATION_PROVIDER": "not-a-real-provider"}):
            with self.assertRaises(GenerationError):
                get_generation_client()

    def test_gemini_provider_without_api_key_raises(self) -> None:
        with mock.patch.dict(os.environ, {"GENERATION_PROVIDER": "gemini"}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            with self.assertRaises(GenerationError):
                get_generation_client()

    def test_gemini_provider_with_api_key_constructs_client(self) -> None:
        from services.llm_client.gemini_generation_client import GeminiGenerationClient

        with mock.patch.dict(
            os.environ, {"GENERATION_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key-not-real"}
        ):
            client = get_generation_client()
            self.assertIsInstance(client, GeminiGenerationClient)