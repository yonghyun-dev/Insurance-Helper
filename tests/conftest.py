"""tests.conftest

공통 pytest 픽스처 모음.

- in-memory SQLite 세션
- 임시 Settings (chroma_db_path, sqlite_db_path 를 tmp_path 로 격리)
- 합성 RawDocument / StructuredDocument 빌더
- OpenAI 임베딩 mock (모든 테스트에서 실제 API 호출 없음)
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from app.domains.chunks.schemas import (
    ChunkType,
    RawDocument,
    RawPage,
    RawTable,
    StructuredDocument,
    StructureNode,
)
from app.infrastructure.core.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# DB 픽스처 — in-memory SQLite
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _disable_audit_in_tests(monkeypatch):
    """Sprint 8 — 모든 테스트에서 audit DB 호출 비활성화 (production engine 충돌 회피).

    audit 자체 테스트는 monkeypatch.setenv("AUDIT_ENABLED", "true") 로 재활성화 가능.
    """
    monkeypatch.setenv("AUDIT_ENABLED", "false")
    # 약관 파서 기본은 upstage(네트워크) — 단위 테스트는 오프라인 PyMuPDF 경로로 고정.
    # Upstage Document Parse 경로는 라이브 스모크로 검증한다.
    monkeypatch.setenv("TERMS_PARSER", "pymupdf")
    # 데모 페르소나 자동 시드 off — 테스트 DB 격리(앱 lifespan seed 차단).
    monkeypatch.setenv("DEMO_SEED_ON_STARTUP", "false")
    import app.infrastructure.core.config as _cfg
    import app.infrastructure.llm.client as _llm

    _cfg.get_settings.cache_clear()
    _llm.clear_cache()
    yield
    _cfg.get_settings.cache_clear()
    _llm.clear_cache()


@pytest.fixture()
def engine():
    """테스트 전용 in-memory SQLite 엔진 (매 테스트마다 독립)."""
    eng = create_engine("sqlite:///:memory:", future=True, echo=False)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def session(engine):
    """in-memory 엔진에 묶인 세션. 테스트 후 자동 롤백."""
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    sess = factory()
    yield sess
    sess.rollback()
    sess.close()


# ---------------------------------------------------------------------------
# Settings 픽스처 — 경로 격리
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_settings(tmp_path, monkeypatch):
    """tmp_path 기반 Settings 를 반환한다.

    get_settings() 캐시를 우회하기 위해 lru_cache 를 초기화하고
    환경 변수로 경로를 주입한다.
    """
    import app.infrastructure.core.config as _cfg

    _cfg.get_settings.cache_clear()

    db_path = tmp_path / "test.db"
    chroma_path = tmp_path / "chroma_db"
    raw_path = tmp_path / "raw"

    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("CHROMA_DB_PATH", str(chroma_path))
    monkeypatch.setenv("RAW_DATA_PATH", str(raw_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = _cfg.Settings(
        sqlite_db_path=db_path,
        chroma_db_path=chroma_path,
        raw_data_path=raw_path,
        openai_api_key="test-key-not-real",
        log_level="DEBUG",
    )
    yield settings

    _cfg.get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 합성 RawDocument 빌더 헬퍼
# ---------------------------------------------------------------------------


def make_raw_document(
    pages_text: list[str],
    file_path: str = "test.pdf",
    parser_version: str = "0.1.0",
    tables_per_page: dict[int, list[RawTable]] | None = None,
) -> RawDocument:
    """테스트용 RawDocument 를 합성 텍스트로 생성한다.

    Args:
        pages_text: 페이지별 텍스트 리스트 (인덱스 0 = 1페이지).
        file_path: 가상 파일 경로.
        parser_version: 파서 버전 태그.
        tables_per_page: {페이지번호: [RawTable, ...]} 형태의 표 데이터.

    Returns:
        RawDocument 인스턴스.
    """
    tables_per_page = tables_per_page or {}
    pages = [
        RawPage(
            page=i + 1,
            text=text,
            raw_text=text,
            tables=tables_per_page.get(i + 1, []),
        )
        for i, text in enumerate(pages_text)
    ]
    return RawDocument(
        file_path=file_path,
        page_count=len(pages),
        pages=pages,
        parser_version=parser_version,
    )


@pytest.fixture()
def raw_document_factory():
    """make_raw_document 를 픽스처로 노출."""
    return make_raw_document


# ---------------------------------------------------------------------------
# 합성 StructuredDocument 빌더 헬퍼
# ---------------------------------------------------------------------------


def make_article_node(
    clause_no: str = "제1조",
    text: str = "제1조 (테스트)\n본문 내용입니다.",
    page: int = 1,
) -> StructureNode:
    """ARTICLE 타입 StructureNode 를 생성한다."""
    return StructureNode(
        id=str(uuid.uuid4()),
        chunk_type=ChunkType.ARTICLE,
        clause_no=clause_no,
        sub_no=None,
        page_start=page,
        page_end=page,
        text=text,
    )


def make_structured_document(
    nodes: list[StructureNode],
    root_ids: list[str] | None = None,
    file_path: str = "test.pdf",
) -> StructuredDocument:
    """StructuredDocument 를 직접 조립한다."""
    if root_ids is None:
        root_ids = [n.id for n in nodes if n.parent_id is None]
    return StructuredDocument(
        file_path=file_path,
        parser_version="0.1.0",
        nodes=nodes,
        root_ids=root_ids,
    )


@pytest.fixture()
def article_node_factory():
    return make_article_node


@pytest.fixture()
def structured_document_factory():
    return make_structured_document


# ---------------------------------------------------------------------------
# 공통 보험 문서 메타 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture()
def document_meta() -> dict:
    """register_document 호출용 공통 파라미터."""
    return {
        "insurer_id": "test_insurer",
        "insurer_name": "테스트보험",
        "area": "auto",
        "product_id": "test_product",
        "product_name": "테스트상품",
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "version_label": "2026-01-01_present",
        "doc_type": "terms",
        "file_path": "/fake/path/terms.pdf",
        "file_sha256": "abc" * 21 + "ab",  # 64자 hex
        "page_count": 10,
        "parser_version": "0.1.0",
    }
