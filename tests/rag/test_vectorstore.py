"""tests.rag.test_vectorstore

app/rag/vectorstore.py 단위 테스트.

테스트 대상:
    - VectorStoreAdapter Protocol 만족 확인 (ChromaAdapter, PgVectorAdapter)
    - get_vector_store() 팩토리 분기 (Settings.effective_vector_store)
    - PgVectorAdapter URL 검증 (postgresql 아닌 URL 거부)

testcontainers 기반 real DB 통합 테스트는 별도 (test_vectorstore_pgvector.py,
선택 실행 — pytest -m pgvector_integration).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.domains.rag.vectorstore import (
    ChromaAdapter,
    PgVectorAdapter,
    VectorStoreAdapter,
    clear_cache,
    get_vector_store,
)

# ===========================================================================
# Protocol 만족 검증
# ===========================================================================


class TestAdaptersImplementProtocol:
    """ChromaAdapter, PgVectorAdapter 가 VectorStoreAdapter Protocol 을 만족."""

    def test_chroma_adapter_satisfies_protocol(self):
        adapter: VectorStoreAdapter = ChromaAdapter()
        assert hasattr(adapter, "upsert")
        assert hasattr(adapter, "query")
        assert hasattr(adapter, "delete_by_document")
        assert hasattr(adapter, "count")
        assert hasattr(adapter, "health")

    def test_pgvector_adapter_satisfies_protocol(self):
        adapter: VectorStoreAdapter = PgVectorAdapter(
            "postgresql://test:test@localhost/test"
        )
        assert hasattr(adapter, "upsert")
        assert hasattr(adapter, "query")
        assert hasattr(adapter, "delete_by_document")
        assert hasattr(adapter, "count")
        assert hasattr(adapter, "health")


# ===========================================================================
# PgVectorAdapter URL 검증
# ===========================================================================


class TestPgVectorAdapterInit:
    """PgVectorAdapter __init__ 의 URL 검증."""

    def test_rejects_sqlite_url(self):
        from app.infrastructure.core.exceptions import StorageError

        with pytest.raises(StorageError, match="PostgreSQL"):
            PgVectorAdapter("sqlite:///./app.db")

    def test_rejects_empty_url(self):
        from app.infrastructure.core.exceptions import StorageError

        with pytest.raises(StorageError, match="PostgreSQL"):
            PgVectorAdapter("")

    def test_accepts_postgresql_url(self):
        # 검증만 — 실제 연결 안 함 (lazy engine)
        adapter = PgVectorAdapter("postgresql://user:pw@localhost:5433/db")
        assert adapter._database_url.startswith("postgresql://")

    def test_accepts_postgresql_psycopg_url(self):
        adapter = PgVectorAdapter("postgresql+psycopg://user:pw@localhost:5433/db")
        assert adapter._database_url.startswith("postgresql+psycopg://")


# ===========================================================================
# get_vector_store 팩토리 분기
# ===========================================================================


class TestGetVectorStoreFactory:
    """effective_vector_store 에 따른 어댑터 선택."""

    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    def test_returns_chroma_when_effective_is_chroma(self):
        with patch("app.domains.rag.vectorstore.get_settings") as mock_settings:
            mock_settings.return_value.effective_vector_store = "chroma"
            mock_settings.return_value.database_url = ""
            adapter = get_vector_store()
            assert isinstance(adapter, ChromaAdapter)

    def test_returns_pgvector_when_effective_is_pgvector(self):
        with patch("app.domains.rag.vectorstore.get_settings") as mock_settings:
            mock_settings.return_value.effective_vector_store = "pgvector"
            mock_settings.return_value.database_url = (
                "postgresql://user:pw@localhost:5433/db"
            )
            adapter = get_vector_store()
            assert isinstance(adapter, PgVectorAdapter)

    def test_factory_cached(self):
        """get_vector_store 는 lru_cache 로 동일 인스턴스 반환."""
        with patch("app.domains.rag.vectorstore.get_settings") as mock_settings:
            mock_settings.return_value.effective_vector_store = "chroma"
            mock_settings.return_value.database_url = ""
            a1 = get_vector_store()
            a2 = get_vector_store()
            assert a1 is a2


# ===========================================================================
# Settings.effective_vector_store 자동 선택
# ===========================================================================


class TestEffectiveVectorStore:
    """Settings.effective_vector_store 자동 fallback."""

    def test_explicit_chroma(self, monkeypatch):
        monkeypatch.setenv("VECTOR_STORE", "chroma")
        monkeypatch.setenv("DATABASE_URL", "postgresql://x")
        from app.infrastructure.core.config import Settings

        s = Settings()
        assert s.effective_vector_store == "chroma"

    def test_explicit_pgvector(self, monkeypatch):
        monkeypatch.setenv("VECTOR_STORE", "pgvector")
        monkeypatch.setenv("DATABASE_URL", "")
        from app.infrastructure.core.config import Settings

        s = Settings()
        assert s.effective_vector_store == "pgvector"

    def test_fallback_postgresql_url_selects_pgvector(self, monkeypatch):
        monkeypatch.setenv("VECTOR_STORE", "")
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5433/d")
        from app.infrastructure.core.config import Settings

        s = Settings()
        assert s.effective_vector_store == "pgvector"

    def test_fallback_empty_database_url_selects_chroma(self, monkeypatch):
        monkeypatch.setenv("VECTOR_STORE", "")
        monkeypatch.setenv("DATABASE_URL", "")
        from app.infrastructure.core.config import Settings

        s = Settings()
        assert s.effective_vector_store == "chroma"

    def test_fallback_sqlite_url_selects_chroma(self, monkeypatch):
        monkeypatch.setenv("VECTOR_STORE", "")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
        from app.infrastructure.core.config import Settings

        s = Settings()
        assert s.effective_vector_store == "chroma"
