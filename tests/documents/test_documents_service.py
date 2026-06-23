"""tests.documents.test_documents_service

app/documents/service.py + crud.py 단위 테스트.

테스트 대상:
    - register_document: 신규 / 해시 동일 / 해시 변경 시나리오
    - count_documents: 빈 DB / INSERT 후 카운트
    - list_insurers, list_products, list_versions: 목록 조회
    - find_document_id_by_sha: 해시 기반 문서 조회
"""

from __future__ import annotations

from datetime import date

from app.domains.documents.service import (
    count_documents,
    find_document_id_by_sha,
    find_file_path_by_id,
    list_insurers,
    list_products,
    list_versions,
    register_document,
)

# ===========================================================================
# register_document
# ===========================================================================


class TestRegisterDocument:
    """register_document 3가지 시나리오 검증."""

    def _register(self, session, overrides: dict | None = None) -> tuple[int, int, bool]:
        """기본 파라미터로 register_document 호출."""
        params = dict(
            insurer_id="hanwha",
            insurer_name="한화손해보험",
            area="auto",
            product_id="hanwha_auto_standard",
            product_name="한화 자동차보험 표준",
            valid_from=date(2026, 1, 1),
            valid_to=None,
            version_label="2026-01-01_present",
            doc_type="terms",
            file_path="/data/raw/hanwha/auto/standard/2026-01-01_present/terms.pdf",
            file_sha256="a" * 64,
            page_count=100,
            parser_version="0.1.0",
        )
        if overrides:
            params.update(overrides)
        return register_document(session, **params)

    def test_new_document_returns_changed_true(self, session):
        # 신규 문서 등록 → changed = True
        doc_id, version_id, changed = self._register(session)
        assert changed is True
        assert isinstance(doc_id, int)
        assert isinstance(version_id, int)

    def test_same_hash_and_parser_returns_changed_false(self, session):
        # 동일 해시 + 동일 파서 버전 → changed = False (재처리 불필요)
        self._register(session)
        _, _, changed = self._register(session)
        assert changed is False

    def test_different_hash_returns_changed_true(self, session):
        # 해시 변경 → changed = True (재처리 필요)
        self._register(session, {"file_sha256": "a" * 64})
        _, _, changed = self._register(session, {"file_sha256": "b" * 64})
        assert changed is True

    def test_different_parser_version_returns_changed_true(self, session):
        # 파서 버전 변경 → changed = True
        self._register(session, {"parser_version": "0.1.0"})
        _, _, changed = self._register(session, {"parser_version": "0.2.0"})
        assert changed is True

    def test_register_creates_insurer_record(self, session):
        # 보험사 레코드가 생성됨
        self._register(session)
        insurers = list_insurers(session)
        assert any(i.id == "hanwha" for i in insurers)

    def test_register_twice_does_not_duplicate_insurer(self, session):
        # 같은 보험사로 2번 등록해도 1개만 존재
        self._register(session)
        self._register(session, {"file_sha256": "b" * 64})
        insurers = list_insurers(session)
        hanwha_count = sum(1 for i in insurers if i.id == "hanwha")
        assert hanwha_count == 1

    def test_register_returns_same_doc_id_for_same_document(self, session):
        # 동일 (version_id, doc_type) 조회 → 같은 document_id
        doc_id1, _, _ = self._register(session)
        doc_id2, _, _ = self._register(session)
        assert doc_id1 == doc_id2


# ===========================================================================
# count_documents
# ===========================================================================


class TestCountDocuments:
    """문서 개수 조회 검증."""

    def test_empty_db_returns_zero(self, session):
        assert count_documents(session) == 0

    def test_after_register_count_increases(self, session):
        register_document(
            session,
            insurer_id="ins1",
            insurer_name="보험1",
            area="auto",
            product_id="prod1",
            product_name="상품1",
            valid_from=date(2026, 1, 1),
            valid_to=None,
            version_label="2026-01-01_present",
            doc_type="terms",
            file_path="/tmp/a.pdf",
            file_sha256="c" * 64,
            page_count=5,
            parser_version="0.1.0",
        )
        assert count_documents(session) == 1

    def test_multiple_registers_increment_count(self, session):
        # doc_type 이 다르면 별도 문서로 카운트
        for i, doc_type in enumerate(["terms", "summary"]):
            register_document(
                session,
                insurer_id="ins1",
                insurer_name="보험1",
                area="auto",
                product_id="prod1",
                product_name="상품1",
                valid_from=date(2026, 1, 1),
                valid_to=None,
                version_label="2026-01-01_present",
                doc_type=doc_type,
                file_path=f"/tmp/{doc_type}.pdf",
                file_sha256=chr(ord("d") + i) * 64,
                page_count=5,
                parser_version="0.1.0",
            )
        assert count_documents(session) == 2


# ===========================================================================
# list_insurers / list_products / list_versions
# ===========================================================================


class TestListHelpers:
    """목록 조회 헬퍼 검증."""

    def _setup_data(self, session) -> None:
        """테스트 데이터 셋업."""
        for insurer_id, area, product_id in [
            ("hanwha", "auto", "hanwha_auto"),
            ("samsung", "fire", "samsung_fire"),
        ]:
            register_document(
                session,
                insurer_id=insurer_id,
                insurer_name=f"{insurer_id} 보험",
                area=area,
                product_id=product_id,
                product_name=f"{product_id} 상품",
                valid_from=date(2026, 1, 1),
                valid_to=None,
                version_label="2026-01-01_present",
                doc_type="terms",
                file_path=f"/tmp/{product_id}.pdf",
                file_sha256=insurer_id.encode().hex().ljust(64, "0")[:64],
                page_count=10,
                parser_version="0.1.0",
            )

    def test_list_insurers_returns_all(self, session):
        self._setup_data(session)
        result = list_insurers(session)
        insurer_ids = {i.id for i in result}
        assert "hanwha" in insurer_ids
        assert "samsung" in insurer_ids

    def test_list_products_filter_by_insurer(self, session):
        self._setup_data(session)
        result = list_products(session, insurer_id="hanwha")
        assert len(result) == 1
        assert result[0].id == "hanwha_auto"

    def test_list_products_filter_by_area(self, session):
        self._setup_data(session)
        result = list_products(session, area="fire")
        assert len(result) == 1
        assert result[0].area == "fire"

    def test_list_products_no_filter_returns_all(self, session):
        self._setup_data(session)
        result = list_products(session)
        assert len(result) == 2

    def test_list_versions_for_product(self, session):
        self._setup_data(session)
        result = list_versions(session, "hanwha_auto")
        assert len(result) == 1
        assert result[0].version_label == "2026-01-01_present"

    def test_list_versions_empty_for_unknown_product(self, session):
        result = list_versions(session, "nonexistent_product")
        assert result == []


# ===========================================================================
# find_document_id_by_sha
# ===========================================================================


class TestFindDocumentIdBySha:
    """해시 기반 문서 조회 검증."""

    def test_existing_sha_returns_document_id(self, session):
        # 등록된 해시 → document_id 반환
        sha = "e" * 64
        doc_id, _, _ = register_document(
            session,
            insurer_id="ins1",
            insurer_name="보험1",
            area="auto",
            product_id="prod1",
            product_name="상품1",
            valid_from=date(2026, 1, 1),
            valid_to=None,
            version_label="2026-01-01_present",
            doc_type="terms",
            file_path="/tmp/t.pdf",
            file_sha256=sha,
            page_count=5,
            parser_version="0.1.0",
        )
        result = find_document_id_by_sha(session, sha)
        assert result == doc_id

    def test_unknown_sha_returns_none(self, session):
        # 없는 해시 → None
        result = find_document_id_by_sha(session, "f" * 64)
        assert result is None


# ===========================================================================
# find_file_path_by_id
# ===========================================================================


class TestFindFilePathById:
    """document_id 로 file_path 조회 검증 (Sprint 5 Citation hydrate 용)."""

    def _register(self, session, file_path: str = "/data/raw/test.pdf") -> int:
        """테스트용 문서 등록 후 document_id 반환."""
        doc_id, _, _ = register_document(
            session,
            insurer_id="ins_fp",
            insurer_name="파일경로보험",
            area="auto",
            product_id="prod_fp",
            product_name="파일경로상품",
            valid_from=date(2026, 1, 1),
            valid_to=None,
            version_label="2026-01-01_present",
            doc_type="terms",
            file_path=file_path,
            file_sha256="g" * 64,
            page_count=10,
            parser_version="0.1.0",
        )
        return doc_id

    def test_existing_document_id_returns_file_path(self, session):
        """존재하는 document_id → file_path 반환."""
        file_path = "/data/raw/hanwha/auto/terms.pdf"
        doc_id = self._register(session, file_path=file_path)

        result = find_file_path_by_id(session, doc_id)

        assert result == file_path

    def test_nonexistent_document_id_returns_none(self, session):
        """존재하지 않는 document_id → None 반환."""
        result = find_file_path_by_id(session, document_id=99999)

        assert result is None

    def test_returns_correct_file_path_for_specific_document(self, session):
        """여러 문서 등록 후 특정 id 의 file_path 정확히 반환."""
        path_a = "/data/raw/hanwha/auto/terms.pdf"
        path_b = "/data/raw/samsung/fire/summary.pdf"

        doc_id_a = self._register(session, file_path=path_a)

        # 두 번째 문서 (다른 해시 + 타입으로 별도 등록)
        doc_id_b, _, _ = register_document(
            session,
            insurer_id="ins_fp2",
            insurer_name="두번째보험",
            area="fire",
            product_id="prod_fp2",
            product_name="두번째상품",
            valid_from=date(2026, 1, 1),
            valid_to=None,
            version_label="2026-01-01_present",
            doc_type="summary",
            file_path=path_b,
            file_sha256="h" * 64,
            page_count=5,
            parser_version="0.1.0",
        )

        # 각각 올바른 경로 반환
        assert find_file_path_by_id(session, doc_id_a) == path_a
        assert find_file_path_by_id(session, doc_id_b) == path_b
