"""app.domains.chunks.models

파일 경로: app/chunks/models.py
목적: 약관 청크 SQLAlchemy 2.0 ORM 모델.
주요 객체:
    - ClauseChunk: 청크 1건 (Chroma ID 와 동일 UUID)
주요 의존성: sqlalchemy

설계 참고:
    - docs/design/data-model.md `clause_chunks` 테이블 섹션
    - chunk_type CHECK: article / paragraph / item / table / annex / other
    - SQLite 가 source of truth — Chroma 메타는 단방향 복제 (정합성은 service 트랜잭션이 책임)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.core.database import Base

if TYPE_CHECKING:
    from app.domains.documents.models import Document

CHUNK_TYPES: tuple[str, ...] = ("article", "paragraph", "item", "table", "annex", "other")


def _chunk_type_check_sql() -> str:
    quoted = ",".join(f"'{c}'" for c in CHUNK_TYPES)
    return f"chunk_type IN ({quoted})"


class ClauseChunk(Base):
    """약관 의미 단위 청크. Chroma 컬렉션의 메타·임베딩과 동일 ID 로 연동된다."""

    __tablename__ = "clause_chunks"
    __table_args__ = (
        CheckConstraint(_chunk_type_check_sql(), name="ck_chunks_chunk_type"),
        Index("idx_chunks_document", "document_id"),
        Index("idx_chunks_parent", "parent_chunk_id"),
        Index("idx_chunks_clause", "document_id", "clause_no"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    parent_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("clause_chunks.id"), nullable=True
    )
    chunk_type: Mapped[str] = mapped_column(String(16), nullable=False)
    clause_no: Mapped[str | None] = mapped_column(String(64))
    sub_no: Mapped[str | None] = mapped_column(String(32))
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    tags_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
    parent: Mapped[ClauseChunk | None] = relationship(
        remote_side="ClauseChunk.id", back_populates="children"
    )
    children: Mapped[list[ClauseChunk]] = relationship(back_populates="parent")
