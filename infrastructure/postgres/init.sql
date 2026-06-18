-- infrastructure/postgres/init.sql
--
-- Activates the pgvector extension in the SAGE database.
-- Executed once on first container startup by the PostgreSQL Docker entrypoint.
--
-- Prerequisites:
--   - Image: pgvector/pgvector:pg16 (extension compiled and installed)
--   - User: POSTGRES_USER must be a superuser (default in the official image)
--
-- Idempotent: IF NOT EXISTS ensures this is safe to re-run manually.

CREATE EXTENSION IF NOT EXISTS vector;