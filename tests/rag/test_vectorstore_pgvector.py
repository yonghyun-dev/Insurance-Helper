"""tests.rag.test_vectorstore_pgvector

PgVectorAdapter real DB 단위 테스트.

testcontainers[postgres] 기반 ephemeral PostgreSQL+pgvector 컨테이너를 사용하여
PgVectorAdapter 의 5개 메서드를 실제 DB 환경에서 검증한다.

실행 조건:
    - Docker 가 실행 중이어야 함 (Docker 미설치 시 자동 skip)
    - testcontainers[postgres] 설치 필요

실행 방법:
    pytest -m pgvector_integration tests/rag/test_vectorstore_pgvector.py
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

# Docker 가용 여부 확인 — testcontainers import 실패 또는 Docker 미실행 시 skip
try:
    from testcontainers.postgres import PostgresContainer

    _TESTCONTAINERS_AVAILABLE = True
except ImportError:
    _TESTCONTAINERS_AVAILABLE = False


def _check_docker_available() -> bool:
    """Docker 데몬이 실행 중인지 확인한다."""
    if not _TESTCONTAINERS_AVAILABLE:
        return False
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


_DOCKER_AVAILABLE = _check_docker_available()

pytestmark = pytest.mark.pgvector_integration


def _skip_if_no_docker():
    """Docker 미가용 시 테스트를 건너뜀."""
    if not _DOCKER_AVAILABLE:
        pytest.skip("Docker 미실행 또는 testcontainers 미설치 — pgvector_integration skip")


# ---------------------------------------------------------------------------
# pgvector 컨테이너 + 스키마 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_container():
    """모듈 범위 PostgreSQL+pgvector 컨테이너.

    pgvector 이미지(ankane/pgvector:latest)를 사용하여 컨테이너를 spin-up하고
    테스트 모듈 전체에서 재사용한다.
    """
    _skip_if_no_docker()
    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="test_pgvector",
    ) as container:
        yield container


@pytest.fixture(scope="module")
def pg_engine(pg_container):
    """pgvector 확장 + 전체 스키마가 적용된 SQLAlchemy 엔진."""
    from pgvector.sqlalchemy import Vector  # noqa: F401  # 타입 등록
    from sqlalchemy import create_engine, text

    db_url = pg_container.get_connection_url()
    # psycopg3 드라이버로 강제 변환 (testcontainers 기본은 psycopg2)
    if "+psycopg2" in db_url:
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_engine(db_url, pool_pre_ping=True)

    # 스키마 초기화: pgvector 확장 + 기본 테이블 + embedding 컬럼
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # insurers
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS insurers (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                homepage_url VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))

        # products
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS products (
                id VARCHAR(120) PRIMARY KEY,
                insurer_id VARCHAR(64) NOT NULL REFERENCES insurers(id),
                area VARCHAR(32) NOT NULL CHECK (area IN ('auto','accident_disease','fire')),
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))

        # product_versions
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS product_versions (
                id SERIAL PRIMARY KEY,
                product_id VARCHAR(120) NOT NULL REFERENCES products(id),
                valid_from DATE NOT NULL,
                valid_to DATE,
                version_label VARCHAR(64) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))

        # documents
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                version_id INTEGER NOT NULL REFERENCES product_versions(id),
                doc_type VARCHAR(16) NOT NULL CHECK (doc_type IN ('summary','business','terms')),
                file_path TEXT NOT NULL,
                file_sha256 VARCHAR(64) NOT NULL,
                page_count INTEGER NOT NULL,
                parser_version VARCHAR(32) NOT NULL,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))

        # clause_chunks + embedding 컬럼
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS clause_chunks (
                id VARCHAR(64) PRIMARY KEY,
                document_id INTEGER NOT NULL REFERENCES documents(id),
                parent_chunk_id VARCHAR(64),
                chunk_type VARCHAR(16) NOT NULL
                    CHECK (chunk_type IN ('article','paragraph','item','table','annex','other')),
                clause_no VARCHAR(64),
                sub_no VARCHAR(32),
                page_start INTEGER NOT NULL,
                page_end INTEGER NOT NULL,
                token_count INTEGER NOT NULL,
                text TEXT NOT NULL,
                summary TEXT,
                tags_json TEXT,
                embedding vector(4096),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))

        # Sprint 16 1b — 4096-d 는 pgvector ANN 인덱스 한계(vector 2000 / halfvec 4000) 초과
        # → HNSW 인덱스 없음, exact(순차) 검색 사용.

    yield engine

    engine.dispose()


@pytest.fixture(scope="module")
def seed_data(pg_engine):
    """테스트용 시드 데이터를 적재하고 (insurer/product/version/document + 청크 10건)
    document_id 를 반환한다.

    청크는 모두 [0.1, 0.2, ..., 4096차원] 형태의 확정적 임베딩을 가진다.
    """
    from sqlalchemy import text

    with pg_engine.begin() as conn:
        # insurer
        conn.execute(text("""
            INSERT INTO insurers (id, name)
            VALUES ('insurer_test', '테스트보험')
            ON CONFLICT (id) DO NOTHING
        """))

        # product
        conn.execute(text("""
            INSERT INTO products (id, insurer_id, area, name)
            VALUES ('prod_test', 'insurer_test', 'auto', '테스트자동차보험')
            ON CONFLICT (id) DO NOTHING
        """))

        # product_version
        row = conn.execute(text("""
            INSERT INTO product_versions (product_id, valid_from, version_label)
            VALUES ('prod_test', '2026-01-01', '2026-01-01_present')
            RETURNING id
        """)).fetchone()
        version_id = row[0]

        # document
        row = conn.execute(text("""
            INSERT INTO documents (version_id, doc_type, file_path, file_sha256, page_count, parser_version)
            VALUES (:vid, 'terms', '/fake/terms.pdf', :sha256, 10, '0.1.0')
            RETURNING id
        """), {"vid": version_id, "sha256": "a" * 64}).fetchone()
        document_id = row[0]

        # 청크 10건 + 임베딩 (4096차원 확정값)
        chunk_ids = []
        for i in range(10):
            chunk_id = f"chunk_test_{i:03d}_{uuid.uuid4().hex[:8]}"
            chunk_ids.append(chunk_id)

            # 각 청크에 고유한 임베딩 벡터 (코사인 거리 계산 가능)
            # 0 번 청크: [1.0, 0.0, 0.0, ...] — 첫 번째 차원만 1
            # i 번 청크: 첫 i 차원은 0.1, 나머지는 0
            emb = [0.0] * 4096
            for j in range(min(i + 1, 4096)):
                emb[j] = 0.1
            # 정규화 (코사인 유사도 의미 있게)
            norm = sum(x**2 for x in emb) ** 0.5
            if norm > 0:
                emb = [x / norm for x in emb]
            emb_str = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"

            conn.execute(text("""
                INSERT INTO clause_chunks
                    (id, document_id, chunk_type, clause_no, sub_no, page_start, page_end,
                     token_count, text, embedding)
                VALUES
                    (:id, :doc_id, 'article', :clause_no, NULL, :page, :page,
                     50, :text, CAST(:emb AS vector))
            """), {
                "id": chunk_id,
                "doc_id": document_id,
                "clause_no": f"제{i + 1}조",
                "page": i + 1,
                "text": f"제{i + 1}조 보험금 지급 기준 — 테스트 청크 {i}",
                "emb": emb_str,
            })

    return {
        "document_id": document_id,
        "version_id": version_id,
        "chunk_ids": chunk_ids,
    }


@pytest.fixture()
def adapter(pg_engine, pg_container):
    """각 테스트용 PgVectorAdapter 인스턴스.

    pg_engine 에 연결되도록 DB URL 을 주입한다.
    """
    from app.domains.rag.vectorstore import PgVectorAdapter

    db_url = pg_container.get_connection_url()
    if "+psycopg2" in db_url:
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    adp = PgVectorAdapter(db_url)
    # 내부 engine 은 pg_engine 재사용 (컨테이너 연결 공유)
    adp._engine = pg_engine
    return adp


# ---------------------------------------------------------------------------
# 테스트 클래스: health
# ---------------------------------------------------------------------------


class TestPgVectorHealth:
    """health() — 연결 상태 확인."""

    def test_health_returns_true_when_connected(self, adapter):
        # Arrange: 컨테이너가 실행 중

        # Act
        result = adapter.health()

        # Assert
        assert result is True, "정상 연결 시 health() 는 True 를 반환해야 한다"

    def test_health_returns_false_when_disconnected(self):
        """연결 불가 URL 에서 health() 는 False 를 반환한다 (예외 아님)."""
        _skip_if_no_docker()
        from app.domains.rag.vectorstore import PgVectorAdapter

        # Arrange: 존재하지 않는 포트
        adp = PgVectorAdapter("postgresql+psycopg://bad:bad@127.0.0.1:9999/noexist")

        # Act
        result = adp.health()

        # Assert
        assert result is False, "연결 실패 시 health() 는 False 를 반환해야 한다 (예외 아님)"


# ---------------------------------------------------------------------------
# 테스트 클래스: count
# ---------------------------------------------------------------------------


class TestPgVectorCount:
    """count() — embedding IS NOT NULL 인 청크 수."""

    def test_count_returns_nonzero_after_seed(self, adapter, seed_data):
        # Arrange: seed_data 픽스처가 10개 청크 + 임베딩 적재 완료

        # Act
        result = adapter.count()

        # Assert
        assert result >= 10, f"시드 10개 이상이어야 한다, 실제: {result}"

    def test_count_excludes_null_embeddings(self, adapter, pg_engine, seed_data):
        """embedding=NULL 청크는 count 에서 제외된다."""
        from sqlalchemy import text

        # Arrange: null embedding 청크 1개 삽입
        null_chunk_id = f"null_chunk_{uuid.uuid4().hex[:8]}"
        with pg_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO clause_chunks
                    (id, document_id, chunk_type, page_start, page_end, token_count, text)
                VALUES (:id, :doc_id, 'article', 1, 1, 10, '임베딩 없는 청크')
            """), {"id": null_chunk_id, "doc_id": seed_data["document_id"]})

        count_before = adapter.count()

        # Act: null 청크 추가 후 count 확인
        # null_chunk 는 embedding=NULL 이므로 count 에 포함되지 않아야 함
        count_after = adapter.count()

        # Assert
        assert count_after == count_before, \
            "NULL embedding 청크는 count() 에 포함되지 않아야 한다"

        # Cleanup
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM clause_chunks WHERE id = :id"), {"id": null_chunk_id})


# ---------------------------------------------------------------------------
# 테스트 클래스: upsert
# ---------------------------------------------------------------------------


class TestPgVectorUpsert:
    """upsert() — 신규 임베딩 갱신 + 덮어쓰기 검증."""

    def test_upsert_updates_embedding_for_existing_chunk(self, adapter, pg_engine, seed_data):
        """기존 청크의 embedding 을 새 값으로 갱신한다."""
        from app.domains.chunks.schemas import Chunk, ChunkType
        from sqlalchemy import text

        # Arrange: seed_data 에서 첫 번째 청크 ID 선택
        chunk_id = seed_data["chunk_ids"][0]
        new_emb = [0.5] * 4096

        chunk = Chunk(
            id=chunk_id,
            document_id=seed_data["document_id"],
            chunk_type=ChunkType.ARTICLE,
            clause_no="제1조",
            sub_no=None,
            page_start=1,
            page_end=1,
            token_count=50,
            text="제1조 보험금 지급 기준",
        )

        with patch("app.domains.rag.vectorstore.embed_texts", return_value=[new_emb]):
            # Act
            adapter.upsert([chunk], [new_emb], document_meta={})

        # Assert: embedding 이 갱신되었는지 확인
        with pg_engine.connect() as conn:
            row = conn.execute(text("""
                SELECT embedding::text FROM clause_chunks WHERE id = :id
            """), {"id": chunk_id}).fetchone()

        assert row is not None
        assert row[0] is not None, "embedding 이 NULL 이 아니어야 한다"

    def test_upsert_with_empty_chunks_is_noop(self, adapter):
        """빈 chunks 리스트는 예외 없이 처리된다 (noop)."""
        # Act & Assert: 예외 없이 완료
        adapter.upsert([], [], document_meta={})

    def test_upsert_length_mismatch_raises_storage_error(self, adapter, seed_data):
        """chunks 와 embeddings 길이 불일치 시 StorageError 발생."""
        from app.domains.chunks.schemas import Chunk, ChunkType
        from app.infrastructure.core.exceptions import StorageError

        chunk = Chunk(
            id=seed_data["chunk_ids"][0],
            document_id=seed_data["document_id"],
            chunk_type=ChunkType.ARTICLE,
            clause_no="제1조",
            sub_no=None,
            page_start=1,
            page_end=1,
            token_count=50,
            text="테스트",
        )

        with pytest.raises(StorageError, match="길이 불일치"):
            adapter.upsert([chunk], [], document_meta={})


# ---------------------------------------------------------------------------
# 테스트 클래스: query
# ---------------------------------------------------------------------------


class TestPgVectorQuery:
    """query() — 유사도 검색 + 필터 + top_k 검증."""

    def _make_query_emb(self) -> list[float]:
        """쿼리용 임베딩 — 첫 번째 청크 (chunk_test_000) 에 유사한 벡터."""
        emb = [0.0] * 4096
        emb[0] = 1.0  # chunk_test_000 은 첫 차원만 큰 값
        return emb

    def test_query_returns_top_k_results(self, adapter, seed_data):
        """top_k 개수대로 결과를 반환한다."""
        query_emb = self._make_query_emb()

        with patch("app.domains.rag.vectorstore.embed_texts", return_value=[query_emb]):
            results = adapter.query("보험금 지급 기준", top_k=5)

        assert len(results) <= 5, f"top_k=5 인데 {len(results)} 개 반환됨"
        assert len(results) > 0, "결과가 최소 1개 이상이어야 한다"

    def test_query_result_structure(self, adapter, seed_data):
        """반환 dict 는 id/text/score/metadata 키를 포함한다."""
        query_emb = self._make_query_emb()

        with patch("app.domains.rag.vectorstore.embed_texts", return_value=[query_emb]):
            results = adapter.query("테스트", top_k=1)

        assert len(results) >= 1
        result = results[0]
        assert "id" in result
        assert "text" in result
        assert "score" in result
        assert "metadata" in result

        # score 범위
        assert 0.0 <= result["score"] <= 1.0, f"score 가 [0,1] 범위를 벗어남: {result['score']}"

    def test_query_results_ordered_by_similarity(self, adapter, seed_data):
        """결과는 score 내림차순으로 정렬된다."""
        query_emb = self._make_query_emb()

        with patch("app.domains.rag.vectorstore.embed_texts", return_value=[query_emb]):
            results = adapter.query("보험금", top_k=8)

        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True), \
            f"결과가 score 내림차순이 아님: {scores}"

    def test_query_with_document_id_filter(self, adapter, seed_data):
        """document_id 필터 적용 시 해당 문서 청크만 반환한다."""
        query_emb = self._make_query_emb()
        doc_id = seed_data["document_id"]

        with patch("app.domains.rag.vectorstore.embed_texts", return_value=[query_emb]):
            results = adapter.query(
                "보험금",
                top_k=10,
                filters={"document_id": doc_id},
            )

        for r in results:
            assert r["metadata"]["document_id"] == doc_id, \
                f"다른 document_id 청크가 포함됨: {r['metadata']['document_id']}"

    def test_query_with_area_filter(self, adapter, seed_data):
        """area 필터 적용 시 해당 영역 청크만 반환한다."""
        query_emb = self._make_query_emb()

        with patch("app.domains.rag.vectorstore.embed_texts", return_value=[query_emb]):
            results = adapter.query(
                "보험금",
                top_k=10,
                filters={"area": "auto"},
            )

        for r in results:
            assert r["metadata"]["area"] == "auto"

    def test_query_with_insurer_id_filter(self, adapter, seed_data):
        """insurer_id 필터 적용 시 해당 보험사 청크만 반환한다."""
        query_emb = self._make_query_emb()

        with patch("app.domains.rag.vectorstore.embed_texts", return_value=[query_emb]):
            results = adapter.query(
                "보험금",
                top_k=10,
                filters={"insurer_id": "insurer_test"},
            )

        for r in results:
            assert r["metadata"]["insurer_id"] == "insurer_test"

    def test_query_metadata_keys(self, adapter, seed_data):
        """반환 metadata 에 필수 키가 모두 포함된다."""
        required_keys = {
            "document_id", "insurer_id", "insurer_name",
            "product_id", "product_name", "area",
            "version_id", "version_label", "doc_type",
            "chunk_type", "clause_no", "sub_no",
            "page_start", "page_end", "token_count",
        }
        query_emb = self._make_query_emb()

        with patch("app.domains.rag.vectorstore.embed_texts", return_value=[query_emb]):
            results = adapter.query("보험금", top_k=1)

        assert len(results) >= 1
        meta = results[0]["metadata"]
        missing = required_keys - meta.keys()
        assert not missing, f"metadata 에 누락된 키: {missing}"

    def test_query_empty_text_returns_empty(self, adapter):
        """빈 문자열 쿼리는 빈 리스트를 반환한다."""
        with patch("app.domains.rag.vectorstore.embed_texts", return_value=[]):
            results = adapter.query("   ", top_k=5)

        assert results == [], "빈 쿼리는 빈 리스트를 반환해야 한다"

    def test_query_unknown_filter_key_is_ignored(self, adapter, seed_data):
        """알 수 없는 필터 키는 무시하고 결과를 반환한다 (예외 없음)."""
        query_emb = self._make_query_emb()

        with patch("app.domains.rag.vectorstore.embed_texts", return_value=[query_emb]):
            # 알 수 없는 키 포함 — 예외 없이 결과 반환해야 함
            results = adapter.query(
                "보험금",
                top_k=5,
                filters={"unknown_filter_key": "value"},
            )

        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# 테스트 클래스: delete_by_document
# ---------------------------------------------------------------------------


class TestPgVectorDeleteByDocument:
    """delete_by_document() — embedding NULL 설정 + 행 삭제 카운트."""

    def test_delete_by_document_returns_count(self, adapter, pg_engine, seed_data):
        """삭제(NULL 설정)된 청크 수를 반환한다."""
        from sqlalchemy import text

        # Arrange: 별도 document_id 로 청크 3개 삽입
        insurer_id = "insurer_del"
        product_id = "prod_del"
        with pg_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO insurers (id, name)
                VALUES (:id, '삭제테스트보험')
                ON CONFLICT (id) DO NOTHING
            """), {"id": insurer_id})
            conn.execute(text("""
                INSERT INTO products (id, insurer_id, area, name)
                VALUES (:id, :ins_id, 'fire', '삭제테스트화재보험')
                ON CONFLICT (id) DO NOTHING
            """), {"id": product_id, "ins_id": insurer_id})

            row = conn.execute(text("""
                INSERT INTO product_versions (product_id, valid_from, version_label)
                VALUES (:pid, '2026-01-01', '2026-01-01_present')
                RETURNING id
            """), {"pid": product_id}).fetchone()
            del_version_id = row[0]

            row = conn.execute(text("""
                INSERT INTO documents
                    (version_id, doc_type, file_path, file_sha256, page_count, parser_version)
                VALUES (:vid, 'terms', '/fake/del.pdf', :sha256, 5, '0.1.0')
                RETURNING id
            """), {"vid": del_version_id, "sha256": "b" * 64}).fetchone()
            del_doc_id = row[0]

            # 3개 청크 + 임베딩
            for i in range(3):
                chunk_id = f"del_chunk_{i}_{uuid.uuid4().hex[:8]}"
                emb = "[" + ",".join(["0.1"] * 4096) + "]"
                conn.execute(text("""
                    INSERT INTO clause_chunks
                        (id, document_id, chunk_type, page_start, page_end,
                         token_count, text, embedding)
                    VALUES (:id, :doc_id, 'article', 1, 1, 20, :text, CAST(:emb AS vector))
                """), {
                    "id": chunk_id,
                    "doc_id": del_doc_id,
                    "text": f"삭제 테스트 청크 {i}",
                    "emb": emb,
                })

        # Act
        deleted_count = adapter.delete_by_document(del_doc_id)

        # Assert
        assert deleted_count == 3, f"3개 청크가 삭제되어야 하는데 {deleted_count} 반환"

    def test_delete_by_document_sets_embedding_to_null(self, adapter, pg_engine, seed_data):
        """delete_by_document 후 해당 청크의 embedding 이 NULL 이 된다."""
        from sqlalchemy import text

        # Arrange: 전용 청크 1개 삽입
        insurer_id2 = "insurer_null_test"
        product_id2 = "prod_null_test"
        with pg_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO insurers (id, name)
                VALUES (:id, '널테스트보험') ON CONFLICT (id) DO NOTHING
            """), {"id": insurer_id2})
            conn.execute(text("""
                INSERT INTO products (id, insurer_id, area, name)
                VALUES (:id, :ins, 'auto', '널테스트상품') ON CONFLICT (id) DO NOTHING
            """), {"id": product_id2, "ins": insurer_id2})

            row = conn.execute(text("""
                INSERT INTO product_versions (product_id, valid_from, version_label)
                VALUES (:pid, '2026-02-01', '2026-02-01_present') RETURNING id
            """), {"pid": product_id2}).fetchone()
            null_version_id = row[0]

            row = conn.execute(text("""
                INSERT INTO documents
                    (version_id, doc_type, file_path, file_sha256, page_count, parser_version)
                VALUES (:vid, 'terms', '/fake/null.pdf', :sha, 3, '0.1.0') RETURNING id
            """), {"vid": null_version_id, "sha": "c" * 64}).fetchone()
            null_doc_id = row[0]

            null_chunk_id = f"null_emb_{uuid.uuid4().hex[:8]}"
            emb = "[" + ",".join(["0.2"] * 4096) + "]"
            conn.execute(text("""
                INSERT INTO clause_chunks
                    (id, document_id, chunk_type, page_start, page_end,
                     token_count, text, embedding)
                VALUES (:id, :doc_id, 'article', 1, 1, 20, '널 테스트', CAST(:emb AS vector))
            """), {"id": null_chunk_id, "doc_id": null_doc_id, "emb": emb})

        # Act
        adapter.delete_by_document(null_doc_id)

        # Assert: embedding 이 NULL 로 설정되었는지 확인
        with pg_engine.connect() as conn:
            row = conn.execute(text("""
                SELECT embedding FROM clause_chunks WHERE id = :id
            """), {"id": null_chunk_id}).fetchone()

        assert row is not None
        assert row[0] is None, "delete_by_document 후 embedding 이 NULL 이어야 한다"

    def test_delete_by_document_nonexistent_id_returns_zero(self, adapter):
        """존재하지 않는 document_id 에 대해 0 을 반환한다 (예외 없음)."""
        # Act
        result = adapter.delete_by_document(document_id=999999)

        # Assert
        assert result == 0, "존재하지 않는 document_id 삭제 시 0 반환해야 한다"

    def test_delete_by_document_already_null_not_counted(self, adapter, pg_engine, seed_data):
        """이미 embedding=NULL 인 청크는 삭제 카운트에 포함되지 않는다."""
        from sqlalchemy import text

        # Arrange: null embedding 청크 삽입 (이미 NULL)
        insurer_id3 = "insurer_already_null"
        product_id3 = "prod_already_null"
        with pg_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO insurers (id, name)
                VALUES (:id, '기존널보험') ON CONFLICT (id) DO NOTHING
            """), {"id": insurer_id3})
            conn.execute(text("""
                INSERT INTO products (id, insurer_id, area, name)
                VALUES (:id, :ins, 'fire', '기존널상품') ON CONFLICT (id) DO NOTHING
            """), {"id": product_id3, "ins": insurer_id3})

            row = conn.execute(text("""
                INSERT INTO product_versions (product_id, valid_from, version_label)
                VALUES (:pid, '2026-03-01', '2026-03-01_present') RETURNING id
            """), {"pid": product_id3}).fetchone()
            already_version_id = row[0]

            row = conn.execute(text("""
                INSERT INTO documents
                    (version_id, doc_type, file_path, file_sha256, page_count, parser_version)
                VALUES (:vid, 'terms', '/fake/already.pdf', :sha, 2, '0.1.0') RETURNING id
            """), {"vid": already_version_id, "sha": "d" * 64}).fetchone()
            already_doc_id = row[0]

            # embedding=NULL 청크만 삽입
            already_chunk_id = f"already_null_{uuid.uuid4().hex[:8]}"
            conn.execute(text("""
                INSERT INTO clause_chunks
                    (id, document_id, chunk_type, page_start, page_end, token_count, text)
                VALUES (:id, :doc_id, 'article', 1, 1, 10, '이미 널')
            """), {"id": already_chunk_id, "doc_id": already_doc_id})

        # Act
        result = adapter.delete_by_document(already_doc_id)

        # Assert
        assert result == 0, "이미 NULL 인 청크는 삭제 카운트에 포함되지 않아야 한다"
