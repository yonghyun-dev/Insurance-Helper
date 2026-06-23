"""app.domains.rag.service

파일 경로: app/rag/service.py
목적: RAG retrieval 단일 진입점. mode 라우팅 + graceful fallback + ReAct opt-in.

sessions.service 는 본 모듈의 `retrieve()` 만 호출한다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from pybreaker import CircuitBreaker, CircuitBreakerError

from app.domains.rag.graph import GraphRetriever
from app.domains.rag.hybrid import HybridRetriever
from app.domains.rag.protocols import RagMode, Retriever
from app.domains.rag.vector import VectorRetriever
from app.domains.sessions.schemas import SlotState
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.logging import get_logger

if TYPE_CHECKING:
    from app.domains.rag.agent import AgentResult

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _rag_circuit_breaker() -> CircuitBreaker:
    """Sprint 8 — RAG retriever 호출 보호 circuit breaker.

    설정: Settings.circuit_breaker_fail_max 회 연속 실패 → reset_seconds 초 open.
    open 상태에서 호출 시 CircuitBreakerError 발생 → vector 폴백 분기로 빠짐.
    """
    s = get_settings()
    return CircuitBreaker(
        fail_max=s.circuit_breaker_fail_max,
        reset_timeout=s.circuit_breaker_reset_seconds,
        name="rag_retriever",
    )


@lru_cache(maxsize=1)
def _vector_singleton() -> VectorRetriever:
    return VectorRetriever()


@lru_cache(maxsize=1)
def _graph_singleton() -> GraphRetriever:
    return GraphRetriever()


@lru_cache(maxsize=1)
def _hybrid_singleton() -> HybridRetriever:
    # I6 에서 graph 주입. 현재는 vector only 폴백.
    return HybridRetriever(_vector_singleton(), _graph_singleton())


def _get_retriever(mode: RagMode) -> Retriever:
    if mode == "vector":
        return _vector_singleton()
    if mode == "graph":
        return _graph_singleton()
    return _hybrid_singleton()


def retrieve(
    slots: SlotState,
    top_k: int = 8,
    *,
    mode: RagMode | None = None,
) -> list[dict[str, Any]]:
    """슬롯 컨텍스트로 top_k 청크 반환. mode 미지정 시 settings 사용.

    graceful fallback:
        - mode 가 graph 또는 hybrid 인데 Neo4j health 실패 → vector mode 로 자동 폴백
        - 모든 retriever 실패 → 빈 list (sessions.service 가 _build_no_match_ask 로 분기)

    Returns:
        list[dict] — 기존 search.service.similarity_search 와 호환 + source 필드.
        sessions.service.generate_assessment 가 그대로 소비.

    주: 에이전트(tool 자가 라우팅) 경로는 본 함수가 아니라 run_agent(LangGraph) 가 담당.
    settings.rag_react 가 에이전트 vs 단순 retrieve 를 sessions.service 에서 분기한다.
    """
    settings = get_settings()
    resolved_mode: RagMode = mode if mode is not None else settings.rag_mode  # type: ignore[assignment]

    # graceful fallback — graph 의존 모드인데 health 실패 시 vector 로
    if resolved_mode in ("graph", "hybrid") and not _graph_singleton().health():
        logger.warning(
            "Neo4j health 실패 — mode=%s → vector 폴백", resolved_mode
        )
        resolved_mode = "vector"

    retriever = _get_retriever(resolved_mode)

    breaker = _rag_circuit_breaker()
    try:
        results = breaker.call(retriever.retrieve, slots, top_k)
    except CircuitBreakerError as exc:
        logger.warning("RAG circuit open (mode=%s) — vector 폴백 시도: %s", resolved_mode, exc)
        # circuit open 상태 — vector 직접 호출 (breaker 우회) 1회 시도
        if resolved_mode != "vector":
            try:
                results = _vector_singleton().retrieve(slots, top_k)
            except Exception as exc2:
                logger.error("circuit-open vector 폴백 실패: %s", exc2)
                results = []
        else:
            results = []
    except Exception as exc:
        logger.error("RAG retrieve 실패 (mode=%s): %s", resolved_mode, exc)
        # vector 가 아니면 vector 로 1회 더 시도
        if resolved_mode != "vector":
            try:
                results = _vector_singleton().retrieve(slots, top_k)
                logger.info("vector 폴백 성공")
            except Exception as exc2:
                logger.error("vector 폴백도 실패: %s", exc2)
                results = []
        else:
            results = []

    # RetrievalResult TypedDict → 일반 dict (기존 sessions.service 계약 유지)
    return [dict(r) for r in results]


def run_agent(slots: SlotState, user_message: str) -> AgentResult:
    """ReAct agent 실행 — 단일 LangGraph 경로 (Sprint 24 그래프 일원화).

    `retrieve()` 와 별개 — LLM 이 tool 다발 자가 라우팅 (search_terms / law / hira / kidi /
    calc / validate / fss / finish). 결과는 chunks + tool_results 둘 다 포함.

    sessions.service 가 settings.rag_react=true 일 때 본 함수 호출 → agent_result.chunks 를
    generate_assessment 의 chunks 인자로 전달.

    심볼명 `run_agent` 유지 — sessions 테스트가 본 함수를 패치한다(패치 seam).
    구 AgentRunner / rag_backend 토글은 제거되고 항상 LangGraph 구현으로 위임.

    Args:
        slots: 현재 SlotState
        user_message: 사용자 자연어 입력 (LLM context)

    Returns:
        AgentResult (chunks + tool_results + iterations + finish_reason)
    """
    from app.domains.rag.langgraph_agent import run_agent_langgraph  # 지연 import

    return run_agent_langgraph(slots, user_message)


def clear_caches() -> None:
    """테스트에서 singleton 초기화용 (예: settings 변경 후).

    Sprint 8 reviewer W-4 보정: circuit breaker singleton 도 초기화 (open 상태 격리).
    Sprint 12 reviewer W-2 보정: vectorstore.get_vector_store lru_cache 도 초기화
    (effective_vector_store 변경 시 어댑터 재선택 보장).
    test 환경에서 monkeypatch 로 plain function 으로 교체된 경우는 cache_clear 가 없으므로
    방어적으로 hasattr 체크.
    """
    for fn in (_vector_singleton, _graph_singleton, _hybrid_singleton, _rag_circuit_breaker):
        if hasattr(fn, "cache_clear"):
            fn.cache_clear()
    from app.domains.rag.vectorstore import clear_cache as _clear_vectorstore_cache

    _clear_vectorstore_cache()
