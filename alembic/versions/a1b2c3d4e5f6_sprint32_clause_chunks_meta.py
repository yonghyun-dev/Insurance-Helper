"""sprint32_clause_chunks_meta

Revision ID: a1b2c3d4e5f6
Revises: f4a5b6c7d8e9
Create Date: 2026-07-09 12:00:00.000000

Sprint 32 T3: clause_chunks 에 문서 메타(insurer_id/product_id/area/doc_type) 비정규 부착.
- 기존엔 documents→product_versions→products JOIN 으로만 획득 — Chroma(업서트 시 복제)와
  pgvector(JOIN)의 필터 정합이 백엔드마다 갈릴 여지가 있었다.
- upgrade 는 기존 행을 JOIN backfill 로 채운다 (재인제스트 불필요).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("clause_chunks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("insurer_id", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("product_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("area", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("doc_type", sa.String(length=32), nullable=True))
        batch_op.create_index("idx_chunks_insurer", ["insurer_id"])
        batch_op.create_index("idx_chunks_area", ["area"])

    # 기존 행 backfill — documents JOIN (SQLite 는 UPDATE...FROM 대신 상관 서브쿼리)
    op.execute(
        """
        UPDATE clause_chunks SET
          insurer_id = (
            SELECT p.insurer_id FROM documents d
            JOIN product_versions pv ON pv.id = d.version_id
            JOIN products p ON p.id = pv.product_id
            WHERE d.id = clause_chunks.document_id),
          product_id = (
            SELECT p.id FROM documents d
            JOIN product_versions pv ON pv.id = d.version_id
            JOIN products p ON p.id = pv.product_id
            WHERE d.id = clause_chunks.document_id),
          area = (
            SELECT p.area FROM documents d
            JOIN product_versions pv ON pv.id = d.version_id
            JOIN products p ON p.id = pv.product_id
            WHERE d.id = clause_chunks.document_id),
          doc_type = (
            SELECT d.doc_type FROM documents d WHERE d.id = clause_chunks.document_id)
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("clause_chunks", schema=None) as batch_op:
        batch_op.drop_index("idx_chunks_area")
        batch_op.drop_index("idx_chunks_insurer")
        batch_op.drop_column("doc_type")
        batch_op.drop_column("area")
        batch_op.drop_column("product_id")
        batch_op.drop_column("insurer_id")
