"""app.domains.chunks.service

파일 경로: app/chunks/service.py
목적: 약관 청크 도메인의 비즈니스 로직 진입점.

원칙(domain-architecture):
    - router/CLI/다른 도메인 service 는 본 service 만 호출. crud/models 직접 참조 금지
    - 본 도메인의 내부 모듈(parser/structure/chunker)은 도메인 내부 유틸로 service 가 조합

현재 함수:
    - `process_pdf(pdf_path, max_tokens)`: PDF 1개 → 의미 단위 Chunk 리스트
    - `replace_chunks_for_document(session, document_id, chunks)`: 문서 단위 청크 교체
      (ingestion 도메인의 단일 write 진입점 — 기존 청크 삭제 + 새 청크 INSERT)
    - `list_chunks(session, document_id)`: 특정 문서의 청크 메타 리스트
    - `get_chunk(session, chunk_id)`: 청크 단건 조회
    - `get_chunk_with_relations(session, chunk_id)`: 청크 + 부모 + 형제 (inspect CLI 용)
    - `count_chunks(session)`: 전체 청크 개수

`ChunkInspection` 는 inspect CLI 가 단발성으로 소비하는 컨테이너라 schemas.py(외부 노출용
pydantic) 가 아닌 도메인 service 내부 dataclass 로 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.chunks import crud as _crud
from app.domains.chunks.chunker import DEFAULT_MAX_TOKENS, chunk_document
from app.domains.chunks.models import ClauseChunk
from app.domains.chunks.parser import parse_pdf
from app.domains.chunks.schemas import Chunk, ChunkRead
from app.domains.chunks.structure import recognize_structure


@dataclass
class ChunkInspection:
    """`get_chunk_with_relations` 결과 — inspect CLI 가 소비한다."""

    chunk: ChunkRead
    parent: ChunkRead | None
    siblings: list[ChunkRead]


@dataclass
class ProcessedPdf:
    """`process_pdf` 결과 — 청크 + 파서 메타를 한 번에 반환해 중복 파싱을 방지."""

    chunks: list[Chunk]
    page_count: int
    parser_version: str


def process_pdf(pdf_path: Path | str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> ProcessedPdf:
    """PDF 1개를 파싱·구조 인식·청킹까지 한 번에 수행해 결과 객체를 반환한다.

    Args:
        pdf_path: 처리할 PDF 경로.
        max_tokens: 1청크 최대 토큰 수 (기본 1000).

    Returns:
        ProcessedPdf(chunks, page_count, parser_version).
        chunks 의 `document_id` 는 비어 있어 ingest 단계에서 채워야 한다.
    """
    raw = parse_pdf(pdf_path)
    struct = recognize_structure(raw)
    return ProcessedPdf(
        chunks=chunk_document(struct, max_tokens=max_tokens),
        page_count=raw.page_count,
        parser_version=raw.parser_version,
    )


def replace_chunks_for_document(
    session: Session, document_id: int, chunks: list[Chunk]
) -> tuple[int, int]:
    """문서의 기존 청크를 모두 삭제하고 새 청크 리스트로 교체.

    ingestion 도메인이 재처리 시 호출하는 단일 진입점. 호출자는 chunks 의
    document_id 가 인자와 일치하도록 미리 채운다.

    Returns:
        (deleted_count, inserted_count)
    """
    deleted = _crud.delete_chunks_by_document(session, document_id)
    _crud.insert_chunks(session, document_id, chunks)
    return deleted, len(chunks)


def list_chunks(session: Session, document_id: int) -> list[ChunkRead]:
    """특정 문서의 청크 메타 리스트 (페이지 순)."""
    stmt = (
        select(ClauseChunk)
        .where(ClauseChunk.document_id == document_id)
        .order_by(ClauseChunk.page_start, ClauseChunk.id)
    )
    rows = session.scalars(stmt).all()
    return [ChunkRead.model_validate(row) for row in rows]


def get_chunk(session: Session, chunk_id: str) -> ChunkRead | None:
    """청크 단건 조회."""
    row = session.get(ClauseChunk, chunk_id)
    return ChunkRead.model_validate(row) if row else None


def get_chunk_with_relations(
    session: Session,
    chunk_id: str,
    *,
    include_parent: bool = False,
    include_siblings: bool = False,
) -> ChunkInspection | None:
    """청크 + 부모/형제 동시 조회 (inspect CLI 용)."""
    target = session.get(ClauseChunk, chunk_id)
    if target is None:
        return None

    parent_read: ChunkRead | None = None
    if include_parent and target.parent_chunk_id:
        parent_row = session.get(ClauseChunk, target.parent_chunk_id)
        if parent_row:
            parent_read = ChunkRead.model_validate(parent_row)

    siblings: list[ChunkRead] = []
    if include_siblings and target.parent_chunk_id:
        stmt = (
            select(ClauseChunk)
            .where(
                ClauseChunk.parent_chunk_id == target.parent_chunk_id,
                ClauseChunk.id != target.id,
            )
            .order_by(ClauseChunk.page_start, ClauseChunk.id)
        )
        siblings = [ChunkRead.model_validate(r) for r in session.scalars(stmt).all()]

    return ChunkInspection(
        chunk=ChunkRead.model_validate(target),
        parent=parent_read,
        siblings=siblings,
    )


def count_chunks(session: Session) -> int:
    """SQLite 에 적재된 청크 총 개수."""
    return session.scalar(select(func.count()).select_from(ClauseChunk)) or 0


@dataclass
class ChunkQuality:
    """적재 품질 점검 결과 (ica verify 용)."""

    total: int
    with_clause_no: int
    empty_text: int
    by_type: dict[str, int]


def chunk_quality_stats(session: Session) -> ChunkQuality:
    """청크 메타 완전성/텍스트 품질 집계 — 인덱싱 검증용.

    - with_clause_no: clause_no 가 채워진 청크 수(조항 인식률)
    - empty_text: 본문이 비었거나 공백뿐인 청크 수(파싱 품질)
    - by_type: chunk_type 분포
    """
    rows = session.scalars(select(ClauseChunk)).all()
    total = len(rows)
    with_clause_no = sum(1 for r in rows if r.clause_no)
    empty_text = sum(1 for r in rows if not (r.text or "").strip())
    by_type: dict[str, int] = {}
    for r in rows:
        by_type[r.chunk_type] = by_type.get(r.chunk_type, 0) + 1
    return ChunkQuality(
        total=total,
        with_clause_no=with_clause_no,
        empty_text=empty_text,
        by_type=by_type,
    )
