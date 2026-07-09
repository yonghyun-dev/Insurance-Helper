"""app.domains.rag.protocols

파일 경로: app/rag/protocols.py
목적: Retriever Protocol + RetrievalResult TypedDict. 모든 RAG 채널이 구현하는 공통 계약.

기존 `search.service.similarity_search` 의 반환 형식과 호환 (source 필드만 추가).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict

from app.domains.sessions.schemas import SlotState


class RetrievalResult(TypedDict):
    """단일 검색 결과.

    기존 `search.service.similarity_search` 반환 형식과 호환 + `source` 필드 추가.
    Hybrid dedupe / 디버그 / 감사 추적에 사용.
    """

    id: str
    text: str
    score: float
    metadata: dict[str, Any]
    source: Literal["vector", "graph"]


class Retriever(Protocol):
    """Vector / Graph / Hybrid 공통 인터페이스."""

    def retrieve(self, slots: SlotState, top_k: int = 8) -> list[RetrievalResult]:
        """슬롯 컨텍스트로 top_k 청크를 반환한다."""
        ...

    def health(self) -> bool:
        """저장소 연결 검사 (fallback 판단용)."""
        ...
