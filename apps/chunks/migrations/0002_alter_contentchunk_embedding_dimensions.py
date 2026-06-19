# apps/chunks/migrations/0002_alter_contentchunk_embedding_dimensions.py
"""
Reduces ContentChunk.embedding from vector(1536) to vector(384).

Context: the embedding provider changed from OpenAI text-embedding-3-small
(1536 dimensions, paid API) to a locally-run sentence-transformers model,
BAAI/bge-small-en-v1.5 (384 dimensions, native — free, no API key, no
network call at inference time).

NOT backward-compatible for existing embedding VALUES: a 1536-dimensional
vector cannot be reinterpreted as 384-dimensional. Any ContentChunk rows
with a previously-populated embedding have that embedding cleared to NULL
by this migration's first operation. No ContentChunk rows are deleted —
chunk_text, section_identifier, token_count, and every other field are
untouched. Embeddings must be regenerated after this migration runs.
"""

import pgvector.django
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("chunks", "0001_initial"),
    ]

    operations = [
        # Step 1: clear existing 1536-dim vectors. pgvector enforces the
        # column's declared dimension; ALTER COLUMN TYPE to vector(384)
        # fails on any row still holding a 1536-dim value.
        migrations.RunSQL(
            sql="UPDATE chunks_contentchunk SET embedding = NULL WHERE embedding IS NOT NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Step 2: change the column's declared dimension.
        migrations.AlterField(
            model_name="contentchunk",
            name="embedding",
            field=pgvector.django.VectorField(blank=True, dimensions=384, null=True),
        ),
    ]