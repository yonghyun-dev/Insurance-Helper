"""tests.chunks.test_chunks_service

app/chunks/service.py 단위 테스트.

테스트 대상:
    - replace_chunks_for_document: 청크 교체 (삭제 + INSERT)
    - get_chunk_with_relations: 청크 + 부모/형제 조회
    - count_chunks: 전체 청크 개수
    - ProcessedPdf: 반환 구조 확인 (parse_pdf mock 기반)
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.domains.chunks.schemas import Chunk, ChunkType
from app.domains.chunks.service import (
    ProcessedPdf,
    count_chunks,
    get_chunk_with_relations,
    list_chunks,
    process_pdf,
    replace_chunks_for_document,
)

from tests.conftest import make_raw_document


def _make_chunk(
    document_id: int = 1,
    chunk_type: ChunkType = ChunkType.ARTICLE,
    clause_no: str = "제1조",
    token_count: int = 100,
    text: str = "보험약관 내용입니다. " * 5,
) -> Chunk:
    """테스트용 Chunk 생성 헬퍼."""
    return Chunk(
        id=str(uuid.uuid4()),
        chunk_type=chunk_type,
        clause_no=clause_no,
        page_start=1,
        page_end=1,
        token_count=token_count,
        text=text,
        document_id=document_id,
    )


def _insert_chunks_to_db(session, document_id: int, chunks: list[Chunk]) -> None:
    """테스트용: 청크를 직접 DB에 INSERT."""
    from app.domains.chunks.crud import insert_chunks
    insert_chunks(session, document_id, chunks)
    session.flush()


def _create_test_document(session) -> int:
    """테스트용 문서 레코드를 생성하고 document_id 를 반환한다."""
    from datetime import date

    from app.domains.documents.models import Document, Insurer, Product, ProductVersion

    insurer = Insurer(id="test_ins", name="테스트보험")
    session.add(insurer)

    product = Product(id="test_prod", insurer_id="test_ins", area="auto", name="테스트상품")
    session.add(product)

    version = ProductVersion(
        product_id="test_prod",
        valid_from=date(2026, 1, 1),
        version_label="2026-01-01_present",
        is_active=True,
    )
    session.add(version)
    session.flush()

    doc = Document(
        version_id=version.id,
        doc_type="terms",
        file_path="/tmp/test.pdf",
        file_sha256="a" * 64,
        page_count=10,
        parser_version="0.1.0",
    )
    session.add(doc)
    session.flush()
    return doc.id


# ===========================================================================
# replace_chunks_for_document
# ===========================================================================


class TestReplaceChunksForDocument:
    """청크 교체 로직 검증."""

    def test_insert_new_chunks_returns_counts(self, session):
        # 신규 INSERT — (0, N) 반환
        doc_id = _create_test_document(session)
        chunks = [_make_chunk(document_id=doc_id) for _ in range(3)]

        deleted, inserted = replace_chunks_for_document(session, doc_id, chunks)

        assert deleted == 0
        assert inserted == 3

    def test_replace_existing_chunks_deletes_old_and_inserts_new(self, session):
        # 기존 청크 삭제 후 새 청크 INSERT
        doc_id = _create_test_document(session)
        old_chunks = [_make_chunk(document_id=doc_id) for _ in range(2)]
        _insert_chunks_to_db(session, doc_id, old_chunks)

        new_chunks = [_make_chunk(document_id=doc_id) for _ in range(4)]
        deleted, inserted = replace_chunks_for_document(session, doc_id, new_chunks)

        assert deleted == 2
        assert inserted == 4

    def test_chunks_persisted_after_replace(self, session):
        # 교체 후 새 청크가 DB에 존재해야 함
        doc_id = _create_test_document(session)
        chunk = _make_chunk(document_id=doc_id)
        replace_chunks_for_document(session, doc_id, [chunk])

        result = list_chunks(session, doc_id)
        assert len(result) == 1
        assert result[0].id == chunk.id

    def test_replace_with_empty_list_deletes_all(self, session):
        # 빈 리스트로 교체 → 기존 청크 모두 삭제
        doc_id = _create_test_document(session)
        chunks = [_make_chunk(document_id=doc_id) for _ in range(3)]
        _insert_chunks_to_db(session, doc_id, chunks)

        deleted, inserted = replace_chunks_for_document(session, doc_id, [])

        assert deleted == 3
        assert inserted == 0


# ===========================================================================
# get_chunk_with_relations
# ===========================================================================


class TestGetChunkWithRelations:
    """청크 + 부모/형제 조회 검증."""

    def test_nonexistent_chunk_returns_none(self, session):
        # 없는 chunk_id → None
        result = get_chunk_with_relations(session, "nonexistent-id")
        assert result is None

    def test_chunk_without_parent_returns_none_parent(self, session):
        # 부모 없는 청크 → parent = None
        doc_id = _create_test_document(session)
        chunk = _make_chunk(document_id=doc_id)
        _insert_chunks_to_db(session, doc_id, [chunk])

        result = get_chunk_with_relations(
            session, chunk.id, include_parent=True, include_siblings=True
        )

        assert result is not None
        assert result.parent is None

    def test_chunk_with_parent_returns_parent(self, session):
        # 부모 있는 청크 → parent 포함
        from app.domains.chunks.models import ClauseChunk

        doc_id = _create_test_document(session)

        parent_chunk = _make_chunk(document_id=doc_id, clause_no="제1조")
        _insert_chunks_to_db(session, doc_id, [parent_chunk])

        # 자식 청크 직접 생성 (parent_chunk_id 포함)
        child_chunk = _make_chunk(document_id=doc_id, clause_no="제1조")
        child_row = ClauseChunk(
            id=child_chunk.id,
            document_id=doc_id,
            parent_chunk_id=parent_chunk.id,
            chunk_type=child_chunk.chunk_type.value,
            clause_no=child_chunk.clause_no,
            page_start=1,
            page_end=1,
            token_count=100,
            text=child_chunk.text,
        )
        session.add(child_row)
        session.flush()

        result = get_chunk_with_relations(
            session, child_chunk.id, include_parent=True
        )

        assert result is not None
        assert result.parent is not None
        assert result.parent.id == parent_chunk.id

    def test_siblings_returned_when_include_siblings(self, session):
        # 형제 포함 요청 시 형제 청크 반환
        from app.domains.chunks.models import ClauseChunk

        doc_id = _create_test_document(session)
        parent_chunk = _make_chunk(document_id=doc_id)
        _insert_chunks_to_db(session, doc_id, [parent_chunk])

        # 자식 2개 생성 (같은 parent_chunk_id)
        child_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        for cid in child_ids:
            row = ClauseChunk(
                id=cid,
                document_id=doc_id,
                parent_chunk_id=parent_chunk.id,
                chunk_type="paragraph",
                clause_no="제1조",
                page_start=1,
                page_end=1,
                token_count=50,
                text="항 내용입니다. " * 5,
            )
            session.add(row)
        session.flush()

        result = get_chunk_with_relations(
            session, child_ids[0], include_siblings=True
        )

        assert result is not None
        assert len(result.siblings) == 1  # 자신 제외 형제 1개


# ===========================================================================
# count_chunks
# ===========================================================================


class TestCountChunks:
    """전체 청크 개수 조회 검증."""

    def test_empty_db_returns_zero(self, session):
        # 빈 DB → 0
        assert count_chunks(session) == 0

    def test_after_insert_count_increases(self, session):
        # INSERT 후 개수 증가
        doc_id = _create_test_document(session)
        chunks = [_make_chunk(document_id=doc_id) for _ in range(5)]
        _insert_chunks_to_db(session, doc_id, chunks)

        assert count_chunks(session) == 5

    def test_after_delete_count_decreases(self, session):
        # DELETE 후 개수 감소
        doc_id = _create_test_document(session)
        chunks = [_make_chunk(document_id=doc_id) for _ in range(3)]
        _insert_chunks_to_db(session, doc_id, chunks)

        replace_chunks_for_document(session, doc_id, [])  # 모두 삭제

        assert count_chunks(session) == 0


# ===========================================================================
# process_pdf — ProcessedPdf 반환 구조 (mock 기반)
# ===========================================================================


class TestProcessPdf:
    """process_pdf 결과 구조 검증 (parse_pdf, recognize_structure, chunk_document mock)."""

    def test_process_pdf_returns_processed_pdf(self, tmp_path):
        # process_pdf → ProcessedPdf 인스턴스 반환
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF fake")

        raw = make_raw_document(
            ["제1조 (보험금 지급)\n보험사고 발생 시 지급합니다. " * 10],
            parser_version="0.1.0",
        )

        with patch("app.domains.chunks.service.parse_pdf", return_value=raw):
            result = process_pdf(pdf_path)

        assert isinstance(result, ProcessedPdf)
        assert result.page_count == 1
        assert result.parser_version == "0.1.0"
        # chunks 는 빈 리스트일 수 있음 (MIN_CHUNK_TOKENS 필터)
        assert isinstance(result.chunks, list)

    def test_process_pdf_chunks_have_no_document_id(self, tmp_path):
        # process_pdf 결과 청크의 document_id 는 None (ingest 단계에서 채워야 함)
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF fake")

        raw = make_raw_document(
            ["제1조 (보험금 지급)\n보험사고 발생 시 지급합니다. " * 20],
        )

        with patch("app.domains.chunks.service.parse_pdf", return_value=raw):
            result = process_pdf(pdf_path)

        for chunk in result.chunks:
            assert chunk.document_id is None
