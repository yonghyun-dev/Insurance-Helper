"""app.domains.search.service

파일 경로: app/search/service.py
목적: Chroma 벡터 DB 어댑터. 청크 임베딩 upsert + 유사도 검색 + 메타 필터링.

주요 기능:
    - `get_collection()` 캐시된 Chroma 컬렉션 핸들
    - `upsert_chunks(chunks, embeddings, document_meta)` 청크 + 임베딩 적재
    - `delete_by_document(document_id)` 문서 단위 삭제 (재처리용)
    - `similarity_search(query_text, top_k, filters)` 자연어 → 임베딩 → top-k 청크
    - `count()` 컬렉션 크기

주요 의존성: chromadb

설계 메모:
    - 컬렉션명 'insurance_clauses' 단일. 영역별 분리는 1만 청크 넘어가면 재검토.
    - SQLite 가 source of truth. Chroma 는 검색 메타·벡터만 보관.
    - 동기화 정책: upsert/delete 호출자(ingest service)가 SQLite 트랜잭션 후 Chroma 호출.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings

from app.domains.chunks.schemas import Chunk
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.exceptions import StorageError
from app.infrastructure.core.logging import get_logger
from app.infrastructure.embeddings.service import embed_texts

logger = get_logger(__name__)

COLLECTION_NAME = "insurance_clauses"


@lru_cache(maxsize=1)
def _get_client() -> chromadb.ClientAPI:
    """Chroma PersistentClient 캐싱. settings 의 chroma_db_path 사용."""
    settings = get_settings()
    settings.ensure_data_dirs()
    return chromadb.PersistentClient(
        path=str(settings.chroma_db_path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_collection() -> Collection:
    """청크 컬렉션을 얻거나 생성한다.

    Returns:
        Chroma Collection 핸들.
    """
    client = _get_client()
    # cosine 유사도 — text-embedding-3-small 의 권장 metric
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection() -> None:
    """컬렉션을 삭제 후 재생성한다.

    임베딩 차원 변경(예: 1536→4096) 시 Chroma 컬렉션은 첫 적재 차원에 고정되므로
    재인덱싱 전 반드시 리셋해야 한다 (Sprint 16 1b).
    """
    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception as exc:  # noqa: BLE001  # 없으면 무시
        logger.info("기존 컬렉션 삭제 skip (없거나 실패): %s", exc)
    client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )
    logger.info("Chroma 컬렉션 리셋 완료: %s", COLLECTION_NAME)


def upsert_chunks(
    chunks: list[Chunk],
    embeddings: list[list[float]],
    document_meta: dict[str, Any],
) -> None:
    """청크 리스트 + 임베딩을 Chroma 에 upsert.

    Args:
        chunks: 청크 리스트 (id, text, 위치/타입 메타 포함).
        embeddings: chunks 와 동일 길이의 임베딩 벡터 리스트.
        document_meta: 모든 청크에 공통으로 부착할 문서 단위 메타데이터
            (insurer_id/insurer_name/product_id/product_name/area/version_id/...).

    Raises:
        StorageError: 입력 길이 불일치 또는 Chroma 호출 실패.
    """
    if len(chunks) != len(embeddings):
        raise StorageError(
            f"청크 {len(chunks)}개 / 임베딩 {len(embeddings)}개 — 길이 불일치"
        )
    if not chunks:
        return

    collection = get_collection()
    ids = [c.id for c in chunks]
    docs = [c.text for c in chunks]
    metas = [_build_metadata(c, document_meta) for c in chunks]

    try:
        collection.upsert(ids=ids, documents=docs, embeddings=embeddings, metadatas=metas)
    except Exception as exc:
        raise StorageError(f"Chroma upsert 실패: {exc}") from exc

    logger.info("Chroma upsert 완료: %d 청크", len(chunks))


def delete_by_document(document_id: int) -> int:
    """특정 document_id 의 모든 청크를 Chroma 에서 삭제 (재처리용).

    Returns:
        삭제된 청크 수 (추정).
    """
    collection = get_collection()
    try:
        existing = collection.get(where={"document_id": document_id})
        ids = existing.get("ids", []) or []
        if not ids:
            return 0
        collection.delete(ids=ids)
        logger.info("Chroma 삭제: document_id=%d (%d 청크)", document_id, len(ids))
        return len(ids)
    except Exception as exc:
        raise StorageError(f"Chroma 삭제 실패 (document_id={document_id}): {exc}") from exc


def _to_chroma_where(filters: dict[str, Any] | None) -> dict[str, Any] | None:
    """필터 dict → Chroma where. 키 2개 이상이면 `$and` 로 감싼다.

    Chroma 0.5+ 는 where 에 연산자 1개만 허용하므로 {"area":..,"insurer_id":..}
    같은 다중 키는 ValueError 가 난다. 단일 키는 그대로, 2개 이상은 $and 리스트로.
    """
    if not filters:
        return None
    if len(filters) == 1:
        return filters
    return {"$and": [{k: v} for k, v in filters.items()]}


def similarity_search(
    query_text: str,
    top_k: int = 8,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """자연어 쿼리 → 임베딩 → top-k 청크 반환.

    Args:
        query_text: 검색 자연어.
        top_k: 반환 개수.
        filters: where 필터 (예: {"area": "auto"} 또는 {"area":.., "insurer_id":..}).
            다중 키는 내부에서 Chroma `$and` 로 변환된다.

    Returns:
        결과 리스트. 각 항목은 {id, text, score, metadata}.
    """
    if not query_text.strip():
        return []

    query_emb = embed_texts([query_text], role="query")[0]
    collection = get_collection()

    try:
        result = collection.query(
            query_embeddings=[query_emb],
            n_results=top_k,
            where=_to_chroma_where(filters),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        raise StorageError(f"Chroma 검색 실패: {exc}") from exc

    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    items: list[dict[str, Any]] = []
    for i, _id in enumerate(ids):
        items.append(
            {
                "id": _id,
                "text": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                # cosine distance → similarity (1 - distance), 0~1
                "score": max(0.0, 1.0 - float(distances[i])) if i < len(distances) else 0.0,
            }
        )
    return items


def count() -> int:
    """현재 컬렉션의 청크 수."""
    return get_collection().count()


def sample_dim() -> int | None:
    """적재된 임베딩 1개의 실제 차원. 비어 있으면 None (검증용)."""
    res = get_collection().get(include=["embeddings"], limit=1)
    embeddings = res.get("embeddings") if isinstance(res, dict) else None
    if embeddings is not None and len(embeddings) > 0 and embeddings[0] is not None:
        return len(embeddings[0])
    return None


def _build_metadata(chunk: Chunk, document_meta: dict[str, Any]) -> dict[str, Any]:
    """청크 1개의 Chroma 메타데이터를 구성한다.

    문서 단위 공통 메타 + 청크 고유 메타. Chroma 는 None 값 metadata 를 허용하지
    않으므로 None 키는 제거하거나 문자열로 정규화.
    """
    meta: dict[str, Any] = {
        **document_meta,
        "chunk_type": chunk.chunk_type.value,
        "clause_no": chunk.clause_no or "",
        "sub_no": chunk.sub_no or "",
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "token_count": chunk.token_count,
    }
    return {k: v for k, v in meta.items() if v is not None}
