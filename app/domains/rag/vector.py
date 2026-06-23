"""app.domains.rag.vector

파일 경로: app/rag/vector.py
목적: VectorRetriever — VectorStoreAdapter 위임으로 backend 추상화.

설계 결정 (Sprint 4 rag-architecture.md § 5 옵션 B + Sprint 12 REQ-13):
    LangChain 의 Chroma 래퍼 대신 직접 호출. backend 는 VectorStoreAdapter
    (ChromaAdapter / PgVectorAdapter) 가 결정.
    이유: 회귀 0 + LangChain 의존 일부만 도입 (graph 만 LangChain 필수)
        + Sprint 12 backend 교체 일관성.
"""

from __future__ import annotations

from app.domains.rag._slots import slots_to_filters, slots_to_query
from app.domains.rag.protocols import RetrievalResult
from app.domains.rag.vectorstore import VectorStoreAdapter, get_vector_store
from app.domains.sessions.schemas import SlotState


class VectorRetriever:
    """VectorStoreAdapter 위임 기반 vector RAG.

    어댑터 주입 시 그것을 사용하고, 미주입 시 `get_vector_store()` 팩토리로 결정.
    각 결과에 `source="vector"` 필드를 추가해 Hybrid dedupe 에 활용.
    """

    def __init__(self, adapter: VectorStoreAdapter | None = None) -> None:
        self._adapter = adapter

    @property
    def adapter(self) -> VectorStoreAdapter:
        if self._adapter is None:
            self._adapter = get_vector_store()
        return self._adapter

    def retrieve(self, slots: SlotState, top_k: int = 8) -> list[RetrievalResult]:
        query = slots_to_query(slots)
        filters = slots_to_filters(slots)
        raw = self.adapter.query(query, top_k=top_k, filters=filters)
        return [
            {
                "id": r["id"],
                "text": r["text"],
                "score": r["score"],
                "metadata": r["metadata"],
                "source": "vector",
            }
            for r in raw
        ]

    def health(self) -> bool:
        """vector backend 접근 가능 여부 — 어댑터 위임."""
        return self.adapter.health()
