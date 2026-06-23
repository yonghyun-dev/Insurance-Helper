"""tests.rag.test_vectorstore_equivalence

Chroma ↔ pgvector 검색 결과 동등성 회귀 테스트.

동일 시드 데이터(청크 + 임베딩)를 양 backend 에 적재하고,
10개 자연어 질의에 대해 top-8 결과의 ID 기준 overlap ≥ 7/8 을 검증한다.

조건:
    - @pytest.mark.pgvector_integration (Docker 필요)
    - score 절대값은 미세 차이 허용 (≤ 0.05)
    - 결과 순서는 overlap 검증만 (완전 일치 요구 없음)

실행 방법:
    pytest -m pgvector_integration tests/rag/test_vectorstore_equivalence.py
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest

try:
    from testcontainers.postgres import PostgresContainer

    _TESTCONTAINERS_AVAILABLE = True
except ImportError:
    _TESTCONTAINERS_AVAILABLE = False


def _check_docker_available() -> bool:
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
    if not _DOCKER_AVAILABLE:
        pytest.skip("Docker 미실행 또는 testcontainers 미설치 — pgvector_integration skip")


# ---------------------------------------------------------------------------
# 테스트용 확정적 임베딩 정의
#
# 20개 시드 청크에 대해 각각 고유하고 구별 가능한 4096차원 임베딩을 생성한다.
# 임베딩은 normalize 되어 있으므로 코사인 유사도가 의미 있다.
# ---------------------------------------------------------------------------

_DIM = 4096
_NUM_CHUNKS = 20
_NUM_QUERIES = 10


def _make_chunk_embedding(chunk_idx: int) -> list[float]:
    """chunk_idx 에 대한 확정적 4096차원 임베딩.

    각 청크는 서로 구별 가능한 고유한 방향을 가지며,
    동시에 청크 간에 점진적으로 감소하는 유사도를 갖도록 설계한다.

    청크 i의 임베딩 = 기저 차원 i (강한 신호) + 인접 청크와의 약한 공유 신호.
    이렇게 하면 쿼리 i 에 대해 청크 0..._NUM_CHUNKS 가 다양한 유사도를 가져
    top-8 선택이 결정적이 된다.
    """
    import math

    emb = [0.0] * _DIM
    # 1. 각 청크마다 고유한 주 차원 (20개 청크 × 간격 50차원 = 1000차원 사용)
    primary_dim = (chunk_idx * 50) % _DIM
    emb[primary_dim] = 0.8

    # 2. 공유 신호: 모든 청크가 첫 번째 차원에 약한 공통 성분을 가짐
    #    (쿼리와 여러 청크 간 비-제로 유사도 보장)
    emb[0] = 0.5 - chunk_idx * 0.02  # chunk_idx 가 작을수록 첫 차원 기여가 큼

    # 3. 인접 청크 간 약한 연관성 (연속 청크는 비슷한 내용)
    if chunk_idx > 0:
        prev_dim = ((chunk_idx - 1) * 50) % _DIM
        emb[prev_dim] = 0.1 * math.exp(-0.3 * 1)  # 인접 청크와 약한 공유

    # 4. 정규화
    norm = sum(x**2 for x in emb) ** 0.5
    if norm > 0:
        emb = [x / norm for x in emb]
    return emb


def _make_query_embedding(query_idx: int) -> list[float]:
    """query_idx 에 대한 쿼리 임베딩.

    쿼리 i 는 청크 i 와 가장 유사하며 다른 청크와도 적당한 유사도를 가진다.
    청크 임베딩 기반에 쿼리 특화 약간의 perturbation 추가.
    """
    import math

    emb = list(_make_chunk_embedding(query_idx))

    # 쿼리는 해당 청크와 거의 동일하지만 인접 청크들과도 일정 유사도를 가짐
    # (top-8 에 청크 i-3 ... i+4 가 포함되도록)
    for offset in range(-3, 5):
        neighbor_idx = query_idx + offset
        if 0 <= neighbor_idx < _NUM_CHUNKS and offset != 0:
            neighbor_dim = (neighbor_idx * 50) % _DIM
            # 거리에 따라 지수적으로 감소하는 유사도 추가
            weight = 0.3 * math.exp(-0.4 * abs(offset))
            emb[neighbor_dim] = emb[neighbor_dim] + weight

    # 재정규화
    norm = sum(x**2 for x in emb) ** 0.5
    if norm > 0:
        emb = [x / norm for x in emb]
    return emb


# 청크 데이터 (20개)
_CHUNK_TEXTS = [
    "제1조 보험의 목적 — 이 보험계약의 보험의 목적은 피보험자의 자동차입니다.",
    "제2조 보험 기간 — 이 보험계약의 보험 기간은 계약서에 기재된 기간입니다.",
    "제3조 보험금 지급 사유 — 자동차 사고로 인한 손해를 보상합니다.",
    "제4조 보험금 청구 절차 — 사고 발생 시 즉시 보험사에 통보해야 합니다.",
    "제5조 면책 조항 — 고의 사고는 보상하지 않습니다.",
    "제6조 자기부담금 — 사고 건당 자기부담금을 공제합니다.",
    "제7조 과실 비율 — 사고 과실 비율에 따라 보험금이 조정됩니다.",
    "제8조 타 보험 중복 — 중복 보험 가입 시 비례 보상합니다.",
    "제9조 계약 해지 — 보험료 미납 시 계약이 해지될 수 있습니다.",
    "제10조 분쟁 해결 — 분쟁은 금융감독원 조정을 통해 해결합니다.",
    "제11조 화재 손해 보상 — 화재로 인한 건물 손해를 보상합니다.",
    "제12조 폭발 손해 — 가스 폭발로 인한 손해도 보상합니다.",
    "제13조 수해 보상 — 홍수 및 태풍으로 인한 손해를 보상합니다.",
    "제14조 도난 손해 — 강도 및 절도로 인한 손해를 보상합니다.",
    "제15조 상해 보험금 — 상해로 인한 입원 치료비를 보상합니다.",
    "제16조 진단비 — 중대 질병 진단 시 진단비를 지급합니다.",
    "제17조 수술비 — 수술 시 수술비를 지급합니다.",
    "제18조 장해 급여 — 영구 장해 시 장해급여를 지급합니다.",
    "제19조 사망 보험금 — 피보험자 사망 시 사망보험금을 지급합니다.",
    "제20조 약관 변경 — 약관 변경 시 보험계약자에게 통보합니다.",
]

_QUERY_TEXTS = [
    "자동차 사고 보험금은 얼마나 받을 수 있나요",
    "보험 기간이 언제까지인가요",
    "보험금 청구는 어떻게 하나요",
    "고의 사고도 보상받을 수 있나요",
    "자기부담금이 얼마인가요",
    "과실 비율에 따른 보험금 계산",
    "보험 계약을 해지하려면",
    "분쟁이 생기면 어떻게 하나요",
    "화재 손해 보상 기준",
    "중대 질병 진단비 지급 조건",
]


# ---------------------------------------------------------------------------
# 모듈 레벨 픽스처 (PostgreSQL 컨테이너)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def equiv_pg_container():
    """동등성 테스트 전용 PostgreSQL+pgvector 컨테이너."""
    _skip_if_no_docker()
    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="equiv",
        password="equiv",
        dbname="test_equiv",
    ) as container:
        yield container


@pytest.fixture(scope="module")
def equiv_pg_engine(equiv_pg_container):
    """동등성 테스트용 엔진 + 스키마."""
    from pgvector.sqlalchemy import Vector  # noqa: F401
    from sqlalchemy import create_engine, text

    db_url = equiv_pg_container.get_connection_url()
    if "+psycopg2" in db_url:
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_engine(db_url, pool_pre_ping=True)

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS insurers (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                homepage_url VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS products (
                id VARCHAR(120) PRIMARY KEY,
                insurer_id VARCHAR(64) NOT NULL REFERENCES insurers(id),
                area VARCHAR(32) NOT NULL CHECK (area IN ('auto','accident_disease','fire')),
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
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
        # Sprint 16 1b — 4096-d 는 pgvector ANN 인덱스 한계 초과 → HNSW 없음(exact scan).

    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def equiv_seed(equiv_pg_engine) -> dict[str, Any]:
    """동등성 테스트용 시드: chunk_id 목록 + document_id.

    20개 청크에 대해 확정적 임베딩을 양 backend 에 동시 적재한다.
    """
    from sqlalchemy import text

    chunk_ids: list[str] = []
    embeddings: list[list[float]] = []

    with equiv_pg_engine.begin() as conn:
        # 기준 데이터
        conn.execute(text("""
            INSERT INTO insurers (id, name)
            VALUES ('equiv_insurer', '동등성테스트보험') ON CONFLICT (id) DO NOTHING
        """))
        conn.execute(text("""
            INSERT INTO products (id, insurer_id, area, name)
            VALUES ('equiv_prod', 'equiv_insurer', 'auto', '동등성테스트자동차보험')
            ON CONFLICT (id) DO NOTHING
        """))
        row = conn.execute(text("""
            INSERT INTO product_versions (product_id, valid_from, version_label)
            VALUES ('equiv_prod', '2026-01-01', '2026-01-01_equiv') RETURNING id
        """)).fetchone()
        version_id = row[0]

        row = conn.execute(text("""
            INSERT INTO documents
                (version_id, doc_type, file_path, file_sha256, page_count, parser_version)
            VALUES (:vid, 'terms', '/equiv/terms.pdf', :sha, 20, '0.1.0') RETURNING id
        """), {"vid": version_id, "sha": "e" * 64}).fetchone()
        document_id = row[0]

        # 청크 20개 + 임베딩
        for i in range(_NUM_CHUNKS):
            chunk_id = f"equiv_chunk_{i:02d}_{uuid.uuid4().hex[:8]}"
            chunk_ids.append(chunk_id)
            emb = _make_chunk_embedding(i)
            embeddings.append(emb)
            emb_str = "[" + ",".join(f"{x:.8f}" for x in emb) + "]"

            conn.execute(text("""
                INSERT INTO clause_chunks
                    (id, document_id, chunk_type, clause_no, sub_no,
                     page_start, page_end, token_count, text, embedding)
                VALUES
                    (:id, :doc_id, 'article', :clause, NULL,
                     :page, :page, 80, :text, CAST(:emb AS vector))
            """), {
                "id": chunk_id,
                "doc_id": document_id,
                "clause": f"제{i + 1}조",
                "page": i + 1,
                "text": _CHUNK_TEXTS[i],
                "emb": emb_str,
            })

    return {
        "chunk_ids": chunk_ids,
        "embeddings": embeddings,
        "document_id": document_id,
    }


@pytest.fixture(scope="module")
def chroma_adapter(tmp_path_factory):
    """동등성 테스트용 ChromaAdapter (격리된 tmp chroma_db)."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    chroma_path = tmp_path_factory.mktemp("equiv_chroma")

    # Chroma 클라이언트 직접 생성 (격리)
    client = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(
        name="equiv_test",
        metadata={"hnsw:space": "cosine"},
    )
    return collection


@pytest.fixture(scope="module")
def chroma_with_seed(chroma_adapter, equiv_seed):
    """Chroma 에 동일 시드 데이터를 적재한다."""
    chunk_ids = equiv_seed["chunk_ids"]
    embeddings = equiv_seed["embeddings"]

    # Chroma upsert
    chroma_adapter.upsert(
        ids=chunk_ids,
        documents=[_CHUNK_TEXTS[i] for i in range(_NUM_CHUNKS)],
        embeddings=embeddings,
        metadatas=[
            {
                "chunk_idx": i,
                "clause_no": f"제{i + 1}조",
                "text": _CHUNK_TEXTS[i],
            }
            for i in range(_NUM_CHUNKS)
        ],
    )
    return chroma_adapter


@pytest.fixture(scope="module")
def pgvector_adapter(equiv_pg_engine, equiv_pg_container):
    """동등성 테스트용 PgVectorAdapter."""
    from app.domains.rag.vectorstore import PgVectorAdapter

    db_url = equiv_pg_container.get_connection_url()
    if "+psycopg2" in db_url:
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    adp = PgVectorAdapter(db_url)
    adp._engine = equiv_pg_engine
    return adp


# ---------------------------------------------------------------------------
# 동등성 검증 헬퍼
# ---------------------------------------------------------------------------


def _query_chroma(collection, query_emb: list[float], top_k: int = 8) -> list[str]:
    """Chroma 에서 top-k 청크 ID 목록 반환."""
    result = collection.query(
        query_embeddings=[query_emb],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    return result["ids"][0] if result["ids"] else []


def _query_pgvector(adapter, query_emb: list[float], top_k: int = 8) -> list[str]:
    """pgvector 에서 top-k 청크 ID 목록 반환 (embed_texts 는 mock)."""
    with patch("app.domains.rag.vectorstore.embed_texts", return_value=[query_emb]):
        results = adapter.query("쿼리텍스트", top_k=top_k)
    return [r["id"] for r in results]


# ---------------------------------------------------------------------------
# 동등성 테스트
# ---------------------------------------------------------------------------


class TestChromaPgvectorEquivalence:
    """Chroma ↔ pgvector 검색 결과 동등성.

    동일 임베딩으로 양 backend 를 쿼리하여 top-8 결과의 ID overlap ≥ 7/8 를 검증한다.
    """

    def test_top8_overlap_per_query(
        self,
        chroma_with_seed,
        pgvector_adapter,
        equiv_seed,
    ):
        """10개 쿼리 각각 top-8 overlap ≥ 7/8 을 만족한다."""
        _skip_if_no_docker()

        overlap_results = []

        for q_idx in range(_NUM_QUERIES):
            query_emb = _make_query_embedding(q_idx)

            chroma_ids = set(_query_chroma(chroma_with_seed, query_emb, top_k=8))
            pgvector_ids = set(_query_pgvector(pgvector_adapter, query_emb, top_k=8))

            overlap_count = len(chroma_ids & pgvector_ids)
            overlap_results.append({
                "query_idx": q_idx,
                "query_text": _QUERY_TEXTS[q_idx],
                "chroma_ids": sorted(chroma_ids),
                "pgvector_ids": sorted(pgvector_ids),
                "overlap": overlap_count,
            })

            assert overlap_count >= 7, (
                f"쿼리 {q_idx} ({_QUERY_TEXTS[q_idx]}): "
                f"top-8 overlap = {overlap_count}/8 (기준: ≥ 7)\n"
                f"  Chroma: {sorted(chroma_ids)}\n"
                f"  pgvector: {sorted(pgvector_ids)}"
            )

    def test_top1_exact_match(
        self,
        chroma_with_seed,
        pgvector_adapter,
        equiv_seed,
    ):
        """각 청크와 동일한 임베딩으로 쿼리 시 top-1 결과가 양 backend 에서 동일하다.

        확정적 임베딩 환경에서 top-1 은 반드시 일치해야 한다.
        """
        _skip_if_no_docker()

        mismatches = []
        for q_idx in range(min(_NUM_QUERIES, _NUM_CHUNKS)):
            query_emb = _make_query_embedding(q_idx)
            expected_chunk_id = equiv_seed["chunk_ids"][q_idx]

            chroma_top1 = _query_chroma(chroma_with_seed, query_emb, top_k=1)
            pgvector_top1 = _query_pgvector(pgvector_adapter, query_emb, top_k=1)

            if chroma_top1 and pgvector_top1 and chroma_top1[0] != pgvector_top1[0]:
                mismatches.append({
                        "query_idx": q_idx,
                        "chroma_top1": chroma_top1[0],
                        "pgvector_top1": pgvector_top1[0],
                        "expected": expected_chunk_id,
                    })

        assert not mismatches, (
            f"top-1 불일치 {len(mismatches)}건:\n" +
            "\n".join(
                f"  q{m['query_idx']}: chroma={m['chroma_top1']} pgvector={m['pgvector_top1']}"
                for m in mismatches
            )
        )

    def test_score_difference_within_tolerance(
        self,
        chroma_with_seed,
        pgvector_adapter,
        equiv_seed,
    ):
        """공통 결과 청크에 대한 score 절대값 차이가 ≤ 0.05 이다.

        Chroma 와 pgvector 는 cosine similarity 계산 방식이 약간 다를 수 있어
        완전 일치보다 0.05 오차를 허용한다.
        """
        _skip_if_no_docker()

        for q_idx in range(_NUM_QUERIES):
            query_emb = _make_query_embedding(q_idx)

            chroma_results = chroma_with_seed.query(
                query_embeddings=[query_emb],
                n_results=8,
                include=["distances"],
            )
            pgvector_results_raw = []
            with patch("app.domains.rag.vectorstore.embed_texts", return_value=[query_emb]):
                pgvector_results_raw = pgvector_adapter.query("쿼리", top_k=8)

            # Chroma: distance → cosine similarity = 1 - distance
            chroma_id_to_score: dict[str, float] = {}
            if chroma_results["ids"]:
                for cid, dist in zip(
                    chroma_results["ids"][0],
                    chroma_results["distances"][0],
                    strict=False,
                ):
                    chroma_id_to_score[cid] = max(0.0, 1.0 - dist)

            pgvector_id_to_score: dict[str, float] = {
                r["id"]: r["score"] for r in pgvector_results_raw
            }

            # 공통 ID 에 대해 score 차이 검증
            common_ids = set(chroma_id_to_score) & set(pgvector_id_to_score)
            for cid in common_ids:
                diff = abs(chroma_id_to_score[cid] - pgvector_id_to_score[cid])
                assert diff <= 0.05, (
                    f"쿼리 {q_idx}, 청크 {cid}: "
                    f"score 차이 {diff:.4f} > 0.05 "
                    f"(chroma={chroma_id_to_score[cid]:.4f}, "
                    f"pgvector={pgvector_id_to_score[cid]:.4f})"
                )

    def test_both_backends_return_nonempty_results(
        self,
        chroma_with_seed,
        pgvector_adapter,
        equiv_seed,
    ):
        """양 backend 모두 시드 데이터에 대해 비어있지 않은 결과를 반환한다."""
        _skip_if_no_docker()

        query_emb = _make_query_embedding(0)

        chroma_ids = _query_chroma(chroma_with_seed, query_emb, top_k=8)
        pgvector_ids = _query_pgvector(pgvector_adapter, query_emb, top_k=8)

        assert len(chroma_ids) > 0, "Chroma 가 빈 결과를 반환함"
        assert len(pgvector_ids) > 0, "pgvector 가 빈 결과를 반환함"

    def test_aggregate_overlap_across_queries(
        self,
        chroma_with_seed,
        pgvector_adapter,
        equiv_seed,
    ):
        """10개 쿼리 전체 평균 overlap rate ≥ 87.5% (= 7/8)."""
        _skip_if_no_docker()

        total_overlap = 0
        total_possible = 0

        for q_idx in range(_NUM_QUERIES):
            query_emb = _make_query_embedding(q_idx)

            chroma_ids = set(_query_chroma(chroma_with_seed, query_emb, top_k=8))
            pgvector_ids = set(_query_pgvector(pgvector_adapter, query_emb, top_k=8))

            # 두 backend 모두 결과가 있는 경우만 계산
            if chroma_ids and pgvector_ids:
                total_overlap += len(chroma_ids & pgvector_ids)
                total_possible += max(len(chroma_ids), len(pgvector_ids))

        if total_possible > 0:
            avg_rate = total_overlap / total_possible
            assert avg_rate >= 0.875, (
                f"평균 overlap rate = {avg_rate:.3f} (기준: ≥ 0.875)\n"
                f"전체 overlap: {total_overlap}/{total_possible}"
            )
