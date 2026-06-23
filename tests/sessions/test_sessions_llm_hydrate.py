"""tests.sessions.test_sessions_llm_hydrate

app/sessions/llm._hydrate_citation_urls 단위 테스트.

테스트 대상:
    - chunks 의 metadata.document_id 있을 때 Citation 에 URL 주입
    - chunks 에 chunk_id 매칭 없을 때 원본 Citation 그대로 반환 (skip)
    - SQLite find_file_path_by_id 가 None 반환 시 URL 없이 반환
    - pdf_service.render_page 가 예외 → page_image_url 만 null, pdf_url 은 채워짐 (graceful)
    - find_file_path_by_id 자체 exception → 모든 Citation 그대로 (try/except 보호)

mock 정책:
    - app.infrastructure.core.database.session_scope: contextmanager 통째로 교체
      (_hydrate_citation_urls 가 함수 안에서 from app.infrastructure.core.database import session_scope
       형태로 지역 import 하므로 app.infrastructure.core.database 의 실 객체를 패치)
    - app.domains.documents.service.find_file_path_by_id: monkeypatch
    - app.infrastructure.pdfimage.service.render_page / page_image_url / pdf_url: monkeypatch
"""

from __future__ import annotations

from contextlib import contextmanager

from app.domains.sessions.llm import _hydrate_citation_urls
from app.domains.sessions.schemas import Citation

# ---------------------------------------------------------------------------
# 헬퍼 — Citation / chunk 빌더
# ---------------------------------------------------------------------------


def _make_citation(
    chunk_id: str = "c1",
    page: int = 5,
    page_image_url: str | None = None,
    pdf_url: str | None = None,
) -> Citation:
    return Citation(
        chunk_id=chunk_id,
        insurer="한화손해보험",
        product="개인용자동차보험",
        version="2026",
        doc_type="terms",
        clause="제3조",
        sub_no=None,
        text="보험금 지급 기준 조항 내용입니다.",
        page=page,
        page_image_url=page_image_url,
        pdf_url=pdf_url,
    )


def _make_chunk(
    chunk_id: str = "c1",
    document_id: int | None = 1,
    page_start: int | None = 5,
) -> dict:
    """_hydrate_citation_urls 에 전달할 chunk dict."""
    return {
        "id": chunk_id,
        "text": "보험금 지급 기준",
        "score": 0.9,
        "metadata": {
            "document_id": document_id,
            "page_start": page_start,
            "insurer_name": "한화손해보험",
        },
    }


# ---------------------------------------------------------------------------
# session_scope mock 헬퍼
# ---------------------------------------------------------------------------


def _make_fake_session_scope(fake_sql_session):
    """주어진 session 을 yield 하는 fake session_scope 팩토리."""

    @contextmanager
    def fake_session_scope():
        yield fake_sql_session

    return fake_session_scope


# ===========================================================================
# _hydrate_citation_urls
# ===========================================================================


class TestHydrateCitationUrls:
    """_hydrate_citation_urls 동작 검증.

    _hydrate_citation_urls 는 함수 내부에서 로컬 import 를 사용한다:
        from app.infrastructure.core.database import session_scope
        from app.domains.documents import service as doc_service
        from app.infrastructure.pdfimage import service as pdf_service

    따라서 monkeypatch 대상은 각 원본 모듈 경로를 직접 패치한다.
    """

    def test_document_id_in_metadata_injects_urls(self, monkeypatch, session):
        """chunks 의 document_id 가 있으면 Citation 에 page_image_url + pdf_url 주입."""
        # Arrange
        citations = [_make_citation(chunk_id="c1", page=5)]
        chunks = [_make_chunk(chunk_id="c1", document_id=1, page_start=5)]

        fake_file_path = "/data/raw/hanwha/auto/terms.pdf"
        expected_image_url = "/static/page_images/1/0005.png"
        expected_pdf_url = "/static/raw/hanwha/auto/terms.pdf"

        monkeypatch.setattr(
            "app.infrastructure.core.database.session_scope",
            _make_fake_session_scope(session),
        )
        monkeypatch.setattr(
            "app.domains.documents.service.find_file_path_by_id",
            lambda sql, doc_id: fake_file_path,
        )
        monkeypatch.setattr(
            "app.infrastructure.pdfimage.service.render_page",
            lambda doc_id, page, fp: None,
        )
        monkeypatch.setattr(
            "app.infrastructure.pdfimage.service.page_image_url",
            lambda doc_id, page: expected_image_url,
        )
        monkeypatch.setattr(
            "app.infrastructure.pdfimage.service.pdf_url",
            lambda fp: expected_pdf_url,
        )

        # Act
        result = _hydrate_citation_urls(citations, chunks)

        # Assert
        assert len(result) == 1
        assert result[0].page_image_url == expected_image_url
        assert result[0].pdf_url == expected_pdf_url

    def test_no_matching_chunk_id_returns_original_citation(
        self, monkeypatch, session
    ):
        """Citation 의 chunk_id 가 chunks 에 없으면 원본 그대로 반환."""
        citations = [_make_citation(chunk_id="unknown-id", page=3)]
        chunks = [_make_chunk(chunk_id="c1", document_id=1, page_start=3)]

        monkeypatch.setattr(
            "app.infrastructure.core.database.session_scope",
            _make_fake_session_scope(session),
        )
        monkeypatch.setattr(
            "app.domains.documents.service.find_file_path_by_id",
            lambda sql, doc_id: "/some/path.pdf",
        )

        result = _hydrate_citation_urls(citations, chunks)

        assert len(result) == 1
        assert result[0].chunk_id == "unknown-id"
        assert result[0].page_image_url is None
        assert result[0].pdf_url is None

    def test_find_file_path_returns_none_url_not_injected(
        self, monkeypatch, session
    ):
        """find_file_path_by_id 가 None 반환 → URL 주입 없이 원본 Citation 반환."""
        citations = [_make_citation(chunk_id="c1", page=2)]
        chunks = [_make_chunk(chunk_id="c1", document_id=1, page_start=2)]

        monkeypatch.setattr(
            "app.infrastructure.core.database.session_scope",
            _make_fake_session_scope(session),
        )
        # find_file_path_by_id → None (미존재 document_id)
        monkeypatch.setattr(
            "app.domains.documents.service.find_file_path_by_id",
            lambda sql, doc_id: None,
        )

        result = _hydrate_citation_urls(citations, chunks)

        assert len(result) == 1
        assert result[0].page_image_url is None
        assert result[0].pdf_url is None

    def test_render_page_exception_page_image_url_null_pdf_url_filled(
        self, monkeypatch, session
    ):
        """render_page 예외 → page_image_url=None, pdf_url 은 채워짐 (graceful degradation)."""
        citations = [_make_citation(chunk_id="c1", page=7)]
        chunks = [_make_chunk(chunk_id="c1", document_id=1, page_start=7)]

        fake_file_path = "/data/raw/hanwha/auto/terms.pdf"
        expected_pdf_url = "/static/raw/hanwha/auto/terms.pdf"

        monkeypatch.setattr(
            "app.infrastructure.core.database.session_scope",
            _make_fake_session_scope(session),
        )
        monkeypatch.setattr(
            "app.domains.documents.service.find_file_path_by_id",
            lambda sql, doc_id: fake_file_path,
        )
        # render_page 가 예외 발생
        def render_page_raises(doc_id, page, fp):
            raise RuntimeError("렌더링 실패")

        monkeypatch.setattr("app.infrastructure.pdfimage.service.render_page", render_page_raises)
        monkeypatch.setattr(
            "app.infrastructure.pdfimage.service.pdf_url",
            lambda fp: expected_pdf_url,
        )

        result = _hydrate_citation_urls(citations, chunks)

        assert len(result) == 1
        # page_image_url 은 None (렌더 실패)
        assert result[0].page_image_url is None
        # pdf_url 은 정상 주입
        assert result[0].pdf_url == expected_pdf_url

    def test_find_file_path_exception_returns_all_citations_unchanged(
        self, monkeypatch, session
    ):
        """session_scope 예외 → 모든 Citation 원본 그대로."""
        citations = [
            _make_citation(chunk_id="c1", page=1),
            _make_citation(chunk_id="c2", page=2),
        ]
        chunks = [
            _make_chunk(chunk_id="c1", document_id=1, page_start=1),
            _make_chunk(chunk_id="c2", document_id=2, page_start=2),
        ]

        # session_scope 자체가 예외 발생
        @contextmanager
        def boom_session_scope():
            raise RuntimeError("DB 연결 실패")
            yield  # type: ignore[misc]

        monkeypatch.setattr("app.infrastructure.core.database.session_scope", boom_session_scope)

        result = _hydrate_citation_urls(citations, chunks)

        # 예외 발생 시 원본 citations 그대로 반환
        assert len(result) == 2
        assert result[0].chunk_id == "c1"
        assert result[1].chunk_id == "c2"
        assert all(c.page_image_url is None for c in result)
        assert all(c.pdf_url is None for c in result)

    def test_no_document_id_in_metadata_returns_citations_unchanged(
        self, monkeypatch
    ):
        """chunks 의 metadata 에 document_id 없으면 빈 doc_ids → 조기 반환."""
        citations = [_make_citation(chunk_id="c1", page=1)]
        # document_id 없음
        chunks = [_make_chunk(chunk_id="c1", document_id=None, page_start=1)]

        # session_scope 는 호출되지 않아야 함
        called = []

        @contextmanager
        def should_not_be_called():
            called.append(True)
            yield None

        monkeypatch.setattr("app.infrastructure.core.database.session_scope", should_not_be_called)

        result = _hydrate_citation_urls(citations, chunks)

        # doc_ids 가 비어있으므로 조기 반환 — session_scope 호출 없음
        assert called == []
        assert len(result) == 1
        assert result[0].page_image_url is None

    def test_multiple_citations_partially_matched(self, monkeypatch, session):
        """일부 Citation 은 매칭 있음, 일부는 없음 — 각각 독립 처리."""
        citations = [
            _make_citation(chunk_id="c1", page=1),
            _make_citation(chunk_id="c_no_chunk", page=2),
        ]
        # c1 만 chunk 에 있음
        chunks = [_make_chunk(chunk_id="c1", document_id=1, page_start=1)]

        expected_image_url = "/static/page_images/1/0001.png"
        expected_pdf_url = "/static/raw/test.pdf"

        monkeypatch.setattr(
            "app.infrastructure.core.database.session_scope",
            _make_fake_session_scope(session),
        )
        monkeypatch.setattr(
            "app.domains.documents.service.find_file_path_by_id",
            lambda sql, doc_id: "/data/raw/test.pdf",
        )
        monkeypatch.setattr(
            "app.infrastructure.pdfimage.service.render_page",
            lambda doc_id, page, fp: None,
        )
        monkeypatch.setattr(
            "app.infrastructure.pdfimage.service.page_image_url",
            lambda doc_id, page: expected_image_url,
        )
        monkeypatch.setattr(
            "app.infrastructure.pdfimage.service.pdf_url",
            lambda fp: expected_pdf_url,
        )

        result = _hydrate_citation_urls(citations, chunks)

        assert len(result) == 2
        # c1: URL 주입됨
        c1 = next(c for c in result if c.chunk_id == "c1")
        assert c1.page_image_url == expected_image_url
        assert c1.pdf_url == expected_pdf_url

        # c_no_chunk: 원본 그대로
        c_no = next(c for c in result if c.chunk_id == "c_no_chunk")
        assert c_no.page_image_url is None
        assert c_no.pdf_url is None
