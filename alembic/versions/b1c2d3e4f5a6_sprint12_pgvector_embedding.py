"""sprint12_pgvector_embedding — clause_chunks.embedding vector(1536) + HNSW

Revision ID: b1c2d3e4f5a6
Revises: afc2f2f931bf
Create Date: 2026-05-26 09:30:00.000000

Sprint 12 (REQ-13): Chroma → pgvector 전환.
PostgreSQL 에서만 embedding 컬럼 + HNSW 인덱스 + vector 확장 생성.
SQLite dev 환경은 skip (pgvector 미지원 — Chroma 그대로 사용).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "afc2f2f931bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """PostgreSQL: vector 확장 + embedding 컬럼 + HNSW 인덱스. SQLite: skip."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite (dev) 환경에서는 pgvector 미지원 — Chroma backend 그대로 사용
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "ALTER TABLE clause_chunks ADD COLUMN IF NOT EXISTS embedding vector(1536)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS clause_chunks_embedding_hnsw_idx "
        "ON clause_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    """PostgreSQL: HNSW 인덱스 + embedding 컬럼 제거. vector 확장은 유지 (다른 곳 사용 가능)."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS clause_chunks_embedding_hnsw_idx")
    op.execute("ALTER TABLE clause_chunks DROP COLUMN IF EXISTS embedding")
