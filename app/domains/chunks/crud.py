"""app.domains.chunks.crud

파일 경로: app/chunks/crud.py
목적: ClauseChunk SQLite CRUD 헬퍼.
주요 의존성: sqlalchemy
"""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.domains.chunks.models import ClauseChunk
from app.domains.chunks.schemas import Chunk


def delete_chunks_by_document(session: Session, document_id: int) -> int:
    """문서 단위로 청크를 모두 삭제 (재처리 시 사용)."""
    stmt = delete(ClauseChunk).where(ClauseChunk.document_id == document_id)
    result = session.execute(stmt)
    session.flush()
    return result.rowcount or 0


def insert_chunks(session: Session, document_id: int, chunks: list[Chunk]) -> None:
    """청크 리스트를 SQLite 에 일괄 INSERT.

    Chroma upsert 전에 호출. document_id 는 호출자가 채워 전달한다.
    """
    rows = [
        ClauseChunk(
            id=c.id,
            document_id=document_id,
            parent_chunk_id=c.parent_chunk_id,
            insurer_id=c.insurer_id,
            product_id=c.product_id,
            area=c.area,
            doc_type=c.doc_type,
            chunk_type=c.chunk_type.value,
            clause_no=c.clause_no,
            sub_no=c.sub_no,
            page_start=c.page_start,
            page_end=c.page_end,
            token_count=c.token_count,
            text=c.text,
            summary=c.summary,
            tags_json=",".join(c.tags) if c.tags else None,
        )
        for c in chunks
    ]
    session.add_all(rows)
    session.flush()
