"""app.domains.rag.hybrid

파일 경로: app/rag/hybrid.py
목적: HybridRetriever — Vector + Graph 동시 호출 후 dedupe + score 정렬.

Sprint 4 I6 에서 채운다. 본 모듈은 vector-only 폴백 stub.
"""

from __future__ import annotations

from app.domains.rag.protocols import RetrievalResult
from app.domains.rag.vector import VectorRetriever
from app.domains.sessions.schemas import SlotState
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)


class HybridRetriever:
    """Vector + Graph 합성. Sprint 4 I6 구현 전엔 vector 만 사용."""

    def __init__(self, vector: VectorRetriever | None = None, graph: object | None = None) -> None:
        self._vector = vector or VectorRetriever()
        self._graph = graph  # I6 에서 GraphRetriever 주입

    def retrieve(self, slots: SlotState, top_k: int = 8) -> list[RetrievalResult]:
        v_results = self._vector.retrieve(slots, top_k)
        if self._graph is None:
            logger.debug("HybridRetriever stub: graph 미주입 → vector only")
            return v_results

        # I6 에서 graph 호출 + dedupe + score 정렬 구현
        try:
            g_results = self._graph.retrieve(slots, top_k)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("graph retrieve 실패 → vector only: %s", exc)
            g_results = []

        merged = _dedupe_by_id(v_results + g_results)
        merged.sort(key=lambda r: r["score"], reverse=True)
        return merged[:top_k]

    def health(self) -> bool:
        return self._vector.health()


def _dedupe_by_id(items: list[RetrievalResult]) -> list[RetrievalResult]:
    """동일 chunk id 중복 제거. 같은 id 면 score 높은 것 유지."""
    by_id: dict[str, RetrievalResult] = {}
    for item in items:
        key = item["id"]
        existing = by_id.get(key)
        if existing is None or item["score"] > existing["score"]:
            by_id[key] = item
    return list(by_id.values())
