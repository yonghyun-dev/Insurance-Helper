"""app.domains.rag.vectorstore

파일 경로: app/rag/vectorstore.py
목적: 벡터 저장 backend 어댑터 추상화 (Sprint 12 REQ-13).

설계 (tech-decisions § Sprint 12):
    - `VectorStoreAdapter` Protocol — 5 메서드 (upsert/query/delete_by_document/count/health)
    - `ChromaAdapter` — 기존 `app.domains.search.service` 함수 thin wrap (회귀 0)
    - `PgVectorAdapter` — psycopg + pgvector. clause_chunks.embedding 컬럼 + HNSW 인덱스
    - `get_vector_store()` 팩토리 — `Settings.effective_vector_store` 기반 분기

호환성:
    - 두 어댑터의 `query()` 반환 형식 동일: list[{id, text, score, metadata}]
    - score 정의 동일: cosine similarity = 1 - cosine_distance (0~1, 높을수록 유사)
    - 동등성 회귀 (top-8 overlap ≥ 7/8) 로 보장

폐기 계획: Sprint 13 (LangGraph) 완료 후 ChromaAdapter 와 chromadb 의존 제거.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Protocol

from app.domains.chunks.schemas import Chunk
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.exceptions import StorageError
from app.infrastructure.core.logging import get_logger
from app.infrastructure.embeddings.service import embed_texts

logger = get_logger(__name__)


# Chroma 메타 키 → SQL 컬럼 매핑 (PgVectorAdapter 의 filter 변환용)
_FILTER_KEY_TO_SQL: dict[str, str] = {
    "area": "p.area",
    "insurer_id": "p.insurer_id",
    "product_id": "p.id",
    "version_id": "v.id",
    "doc_type": "d.doc_type",
    "document_id": "c.document_id",
}


class VectorStoreAdapter(Protocol):
    """벡터 저장 backend 의 통일 인터페이스.

    ChromaAdapter 와 PgVectorAdapter 가 본 Protocol 을 만족한다.
    """

    def upsert(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        document_meta: dict[str, Any],
    ) -> None:
        """청크 + 임베딩 적재 (chunk_id 동일 시 덮어쓰기)."""
        ...

    def query(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """자연어 → 임베딩 → top-k 청크. 반환 dict 구조: {id, text, score, metadata}."""
        ...

    def delete_by_document(self, document_id: int) -> int:
        """특정 document_id 의 모든 청크 임베딩을 삭제. 삭제된 청크 수 반환."""
        ...

    def count(self) -> int:
        """저장된 임베딩 수."""
        ...

    def health(self) -> bool:
        """backend 접근 가능 여부."""
        ...

    def reset(self) -> None:
        """저장소를 비워 재인덱싱을 준비한다 (임베딩 차원 변경 시 필수)."""
        ...


class ChromaAdapter:
    """기존 `app.domains.search.service` thin wrap. 회귀 0 보장."""

    def upsert(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        document_meta: dict[str, Any],
    ) -> None:
        from app.domains.search import service as search_service

        search_service.upsert_chunks(chunks, embeddings, document_meta)

    def query(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        from app.domains.search import service as search_service

        return search_service.similarity_search(query_text, top_k=top_k, filters=filters)

    def delete_by_document(self, document_id: int) -> int:
        from app.domains.search import service as search_service

        return search_service.delete_by_document(document_id)

    def count(self) -> int:
        from app.domains.search import service as search_service

        return search_service.count()

    def health(self) -> bool:
        from app.domains.search import service as search_service

        try:
            search_service.get_collection()
            return True
        except Exception as exc:
            logger.warning("Chroma health 실패: %s", exc, exc_info=True)
            return False

    def reset(self) -> None:
        from app.domains.search import service as search_service

        search_service.reset_collection()


class PgVectorAdapter:
    """PostgreSQL + pgvector backend.

    clause_chunks.embedding vector(4096) 컬럼 (Sprint 16 1b — Upstage).
    4096-d 는 pgvector ANN 인덱스 한계(vector 2000 / halfvec 4000) 초과 → HNSW 없이 exact(순차) 검색.
    메타데이터는 documents/product_versions/products/insurers JOIN 으로 동적 구성
    (ChromaAdapter 처럼 별도 메타 컬럼 없음 — SQLite 가 source of truth).
    """

    def __init__(self, database_url: str) -> None:
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise StorageError(
                "PgVectorAdapter requires PostgreSQL DATABASE_URL "
                f"(got: {database_url[:32]}...)"
            )
        self._database_url = database_url
        self._engine = None  # lazy init

    def _get_engine(self):  # type: ignore[no-untyped-def]
        if self._engine is None:
            from pgvector.sqlalchemy import Vector  # noqa: F401  # 타입 등록 부수효과
            from sqlalchemy import create_engine

            self._engine = create_engine(self._database_url, pool_pre_ping=True)
        return self._engine

    def upsert(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        document_meta: dict[str, Any],  # noqa: ARG002  # pgvector 는 메타 SQLite 에서 JOIN
    ) -> None:
        """clause_chunks 의 embedding 컬럼만 UPDATE. text/메타는 SQLite source of truth."""
        if len(chunks) != len(embeddings):
            raise StorageError(
                f"청크 {len(chunks)}개 / 임베딩 {len(embeddings)}개 — 길이 불일치"
            )
        if not chunks:
            return

        from sqlalchemy import text

        engine = self._get_engine()
        with engine.begin() as conn:
            for chunk, emb in zip(chunks, embeddings, strict=True):
                conn.execute(
                    text(
                        "UPDATE clause_chunks SET embedding = CAST(:emb AS vector) "
                        "WHERE id = :id"
                    ),
                    {"emb": str(emb), "id": chunk.id},
                )

        logger.info("pgvector upsert 완료: %d 청크", len(chunks))

    def query(
        self,
        query_text: str,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not query_text.strip():
            return []

        query_emb = embed_texts([query_text], role="query")[0]

        # Chroma filter → SQL WHERE 변환
        where_clauses: list[str] = ["c.embedding IS NOT NULL"]
        params: dict[str, Any] = {"qvec": str(query_emb), "top_k": top_k}

        if filters:
            for key, value in filters.items():
                sql_col = _FILTER_KEY_TO_SQL.get(key)
                if sql_col is None:
                    # 알 수 없는 키는 무시 (Chroma 동작과 동일하지 않을 수 있음 — 로그)
                    logger.warning("pgvector filter 미매핑 키: %s — 무시", key)
                    continue
                placeholder = f"f_{key}"
                where_clauses.append(f"{sql_col} = :{placeholder}")
                params[placeholder] = value

        where_sql = " AND ".join(where_clauses)
        sql = f"""
            SELECT
                c.id,
                c.text,
                c.chunk_type,
                c.clause_no,
                c.sub_no,
                c.page_start,
                c.page_end,
                c.token_count,
                c.document_id,
                d.doc_type,
                v.id AS version_id,
                v.version_label,
                p.id AS product_id,
                p.area,
                p.name AS product_name,
                i.id AS insurer_id,
                i.name AS insurer_name,
                1.0 - (c.embedding <=> CAST(:qvec AS vector)) AS score
            FROM clause_chunks c
            JOIN documents d ON c.document_id = d.id
            JOIN product_versions v ON d.version_id = v.id
            JOIN products p ON v.product_id = p.id
            JOIN insurers i ON p.insurer_id = i.id
            WHERE {where_sql}
            ORDER BY c.embedding <=> CAST(:qvec AS vector)
            LIMIT :top_k
        """

        from sqlalchemy import text

        engine = self._get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()

        results: list[dict[str, Any]] = []
        for row in rows:
            metadata = {
                "document_id": row["document_id"],
                "insurer_id": row["insurer_id"],
                "insurer_name": row["insurer_name"],
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "area": row["area"],
                "version_id": row["version_id"],
                "version_label": row["version_label"],
                "doc_type": row["doc_type"],
                "chunk_type": row["chunk_type"],
                "clause_no": row["clause_no"] or "",
                "sub_no": row["sub_no"] or "",
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "token_count": row["token_count"],
            }
            results.append(
                {
                    "id": row["id"],
                    "text": row["text"],
                    "score": max(0.0, float(row["score"])),
                    "metadata": metadata,
                }
            )
        return results

    def delete_by_document(self, document_id: int) -> int:
        """document_id 의 모든 청크 embedding 을 NULL 로 (행 삭제 아님 — chunks 자체는 SQLite 가 관리)."""
        from sqlalchemy import text

        engine = self._get_engine()
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "UPDATE clause_chunks SET embedding = NULL "
                    "WHERE document_id = :doc_id AND embedding IS NOT NULL"
                ),
                {"doc_id": document_id},
            )
            count = result.rowcount or 0
        logger.info("pgvector 삭제: document_id=%d (%d 청크)", document_id, count)
        return count

    def count(self) -> int:
        from sqlalchemy import text

        engine = self._get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT COUNT(*) FROM clause_chunks WHERE embedding IS NOT NULL")
            ).scalar()
        return int(row or 0)

    def health(self) -> bool:
        from sqlalchemy import text

        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("pgvector health 실패: %s", exc, exc_info=True)
            return False

    def reset(self) -> None:
        """모든 청크 embedding 을 NULL 로 비운다.

        차원 변경은 alembic 마이그레이션(vector(4096))이 담당하므로 여기서는 데이터만 비운다.
        재인덱싱이 4096 임베딩으로 다시 채운다.
        """
        from sqlalchemy import text

        engine = self._get_engine()
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE clause_chunks SET embedding = NULL WHERE embedding IS NOT NULL")
            )
        logger.info("pgvector reset: 전체 embedding NULL 처리")


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStoreAdapter:
    """현재 Settings 에 따라 적절한 어댑터 반환.

    `Settings.effective_vector_store` 가 "pgvector" 면 PgVectorAdapter, 아니면 ChromaAdapter.
    """
    settings = get_settings()
    if settings.effective_vector_store == "pgvector":
        return PgVectorAdapter(settings.database_url)
    return ChromaAdapter()


def clear_cache() -> None:
    """테스트용 — 어댑터 싱글톤 캐시 초기화."""
    get_vector_store.cache_clear()
