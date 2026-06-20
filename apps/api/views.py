# apps/api/views.py
"""
View for the question-answering endpoint. Pure orchestration — all
domain logic lives in services.generation.generation_service.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from services.generation.generation_service import generate_answer
from services.llm_client.generation_base import GenerationError
from services.retrieval.retrieval_service import RetrievalError

from .serializers import QueryRequestSerializer, QueryResponseSerializer


class QueryView(APIView):
    """
    POST /api/query/

    Returns a cited answer, or an explicit refusal (has_valid_citations
    is False, citations is empty) when the documents don't support one —
    that refusal is a 200, not an error, since the system behaved
    correctly. RetrievalError/GenerationError (external dependency
    failures — Gemini down, DB issue) are the actual error case, mapped
    to 503.
    """

    def post(self, request, *args, **kwargs) -> Response:
        request_serializer = QueryRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        try:
            result = generate_answer(
                query=request_serializer.validated_data["query"],
                document_ids=request_serializer.validated_data.get("document_ids"),
            )
        except (RetrievalError, GenerationError) as exc:
            return Response(
                {"error": str(exc), "code": "GENERATION_FAILED"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(QueryResponseSerializer(result).data)