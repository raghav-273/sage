# apps/api/serializers.py
"""
Serializers for the question-answering endpoint.

QueryResponseSerializer serializes services.generation.generation_service's
AnswerResult and Citation — plain dataclasses, not Django models. DRF's
default field-to-attribute resolution (getattr) handles this correctly
without any special configuration.
"""

from __future__ import annotations

from rest_framework import serializers


class QueryRequestSerializer(serializers.Serializer):
    query = serializers.CharField(allow_blank=False, max_length=2000)
    document_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_null=True, default=None
    )

    def validate_query(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("query must not be empty or whitespace only.")
        return value


class CitationSerializer(serializers.Serializer):
    chunk_id = serializers.UUIDField()
    document_id = serializers.UUIDField()
    page_number = serializers.IntegerField()
    section_identifier = serializers.CharField(allow_null=True)
    excerpt = serializers.CharField()
    confidence_score = serializers.FloatField()
    retrieval_method = serializers.CharField()
    image_path = serializers.CharField(allow_null=True)  # NEW 


class QueryResponseSerializer(serializers.Serializer):
    """
    Superset of the requested response shape: adds `query` (echoed back,
    for client-side correlation) and `rejected_citation_count` (already
    computed, useful diagnostic signal) alongside the four required
    fields. Consistent with every other response schema in this project.
    """

    query = serializers.CharField()
    answer_text = serializers.CharField()
    citations = CitationSerializer(many=True)
    has_valid_citations = serializers.BooleanField()
    retrieved_chunk_count = serializers.IntegerField()
    rejected_citation_count = serializers.IntegerField()