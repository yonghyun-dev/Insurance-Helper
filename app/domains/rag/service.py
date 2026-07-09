"""app.domains.rag.service

파일 경로: app/rag/service.py
목적: RAG retrieval 단일 진입점 — 뉴로심볼릭(뉴럴+심볼릭 융합) 고정 경로 (Sprint 32 T2).

구 rag_mode(vector/graph/hybrid) 토글은 폐지 — 두 채널은 선택지가 아니라 항상 함께
동작하는 구성요소다. 그래프 다운 시 retriever 내부에서 뉴럴 단독으로 graceful 강등.

sessions.service 는 본 모듈의 `retrieve()`/`retrieve_freeform()` 만 호출한다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from pybreaker import CircuitBreaker, CircuitBreakerError

from app.domains.rag.neurosymbolic import NeuroSymbolicRetriever
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
def _retriever_singleton() -> NeuroSymbolicRetriever:
    return NeuroSymbolicRetriever()


def retrieve(
    slots: SlotState,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """슬롯 컨텍스트로 top_k 청크 반환 — 뉴로심볼릭(뉴럴+심볼릭 RRF 융합) 단일 경로.

    graceful: 그래프 다운 → retriever 내부에서 뉴럴 단독. 벡터까지 실패 → 빈 list
    (sessions.service 가 _build_no_match_ask 로 분기).

    Returns:
        list[dict] — 기존 search.service.similarity_search 와 호환 + source 필드
        ("neural"/"symbolic"). sessions.service.generate_assessment 가 그대로 소비.

    주: 에이전트(search_terms tool) 경로도 dispatcher 가 본 모듈을 경유한다 — 우회 경로 없음.
    """
    settings = get_settings()
    retriever = _retriever_singleton()
    # 리랭크 활성 시 후보를 넉넉히(2x) 가져와 재정렬 후 top_k 로 줄인다.
    fetch_k = top_k * 2 if settings.rag_rerank else top_k

    breaker = _rag_circuit_breaker()
    try:
        results = breaker.call(retriever.retrieve, slots, fetch_k)
    except (CircuitBreakerError, Exception) as exc:  # noqa: BLE001
        logger.error("RAG retrieve 실패: %s", exc)
        results = []

    out = [dict(r) for r in results]
    if settings.rag_rerank and len(out) > 1:
        out = _rerank_with_solar(slots, out, top_k)
    return out[:top_k]


def retrieve_freeform(text: str, top_k: int = 8) -> list[dict[str, Any]]:
    """자유 질의(도움 챗봇·일반 QA) — 보험사 스코프 없이 동일 융합·점수컷 파이프라인.

    기존에는 vectorstore.query 직행이라 점수컷·심볼릭이 우회됐다 (Sprint 32 T2 일원화).
    """
    retriever = _retriever_singleton()
    breaker = _rag_circuit_breaker()
    try:
        results = breaker.call(retriever.retrieve_freeform, text, top_k)
    except (CircuitBreakerError, Exception) as exc:  # noqa: BLE001
        logger.error("RAG retrieve_freeform 실패: %s", exc)
        return []
    return [dict(r) for r in results]


def _rerank_with_solar(
    slots: SlotState, results: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    """Solar 로 후보 청크를 질의 관련도 순 재정렬 (listwise). 실패 시 원 순서 유지.

    국내 전용 제약상 cross-encoder 대신 추론 LLM(solar) 재활용. 입력은 청크당 300자
    요약본 — 토큰 절약. 반환 인덱스가 이상하면(범위 밖/부족) 원 순서로 폴백한다.
    """
    import json as _json

    from app.domains.rag._slots import slots_to_query
    from app.infrastructure.llm.client import get_chat_client, get_chat_model

    query = slots_to_query(slots)
    listing = "\n".join(
        f"[{i}] {r['text'][:300]}" for i, r in enumerate(results)
    )
    try:
        resp = get_chat_client().chat.completions.create(
            model=get_chat_model(),
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 보험 약관 검색 리랭커다. 질의와 각 청크의 관련도가 높은 순으로 "
                        "청크 인덱스를 정렬해 JSON 배열로만 답하라. 예: [2,0,5]"
                    ),
                },
                {"role": "user", "content": f"질의: {query}\n\n청크:\n{listing}"},
            ],
        )
        content = (resp.choices[0].message.content or "").strip()
        start, end = content.find("["), content.rfind("]")
        order = _json.loads(content[start : end + 1])
        idx = [i for i in order if isinstance(i, int) and 0 <= i < len(results)]
        # 중복 제거(순서 유지) + 누락 인덱스는 원 순서로 뒤에 붙임 — 청크 유실 방지
        seen: set[int] = set()
        idx = [i for i in idx if not (i in seen or seen.add(i))]
        idx += [i for i in range(len(results)) if i not in seen]
        reranked = [results[i] for i in idx][:top_k]
        logger.info("solar rerank 적용: %d 후보 → top%d", len(results), len(reranked))
        return reranked
    except Exception as exc:  # noqa: BLE001 — 리랭크는 부가 기능, 실패 시 원 순서
        logger.warning("solar rerank 실패 — 원 순서 유지: %s", exc)
        return results[:top_k]


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
    for fn in (_retriever_singleton, _rag_circuit_breaker):
        if hasattr(fn, "cache_clear"):
            fn.cache_clear()
    from app.domains.rag.vectorstore import clear_cache as _clear_vectorstore_cache

    _clear_vectorstore_cache()
