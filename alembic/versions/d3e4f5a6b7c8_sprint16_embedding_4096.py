"""sprint16_embedding_4096 — clause_chunks.embedding vector(1536)→vector(4096), HNSW 제거

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-23 10:00:00.000000

Sprint 16 1b: OpenAI(1536) → Upstage solar-embedding(4096) 전환.
4096-d 는 pgvector ANN 인덱스 한계(vector 2000 / halfvec 4000)를 초과하므로
HNSW 인덱스를 제거하고 exact(순차) 검색을 사용한다 (737 청크 규모 sub-ms).
컬럼 타입 변경 시 기존 1536 임베딩은 무효이므로 USING NULL 로 비운다 → `ica reindex --reset` 로 4096 재적재.
SQLite dev 환경은 skip (pgvector 미지원 — Chroma 사용).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | Sequence[str] | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """PostgreSQL: HNSW 제거 + embedding vector(4096) 로 변경(USING NULL). SQLite: skip."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # 4096-d 는 float ANN 인덱스 불가 → 인덱스 제거 후 재생성하지 않음(exact scan)
    op.execute("DROP INDEX IF EXISTS clause_chunks_embedding_hnsw_idx")
    op.execute(
        "ALTER TABLE clause_chunks "
        "ALTER COLUMN embedding TYPE vector(4096) USING NULL"
    )


def downgrade() -> None:
    """PostgreSQL: embedding vector(1536) 복귀 + HNSW 재생성. SQLite: skip."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "ALTER TABLE clause_chunks "
        "ALTER COLUMN embedding TYPE vector(1536) USING NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS clause_chunks_embedding_hnsw_idx "
        "ON clause_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
