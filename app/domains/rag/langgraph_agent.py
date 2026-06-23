"""app.domains.rag.langgraph_agent

파일 경로: app/domains/rag/langgraph_agent.py
목적: ReAct 에이전트의 **단일 정본 구현** — LangGraph StateGraph.

Sprint 24 그래프 일원화로 구 `AgentRunner`(수기 ReAct loop)는 제거되고 본 모듈이
유일한 에이전트 경로가 되었다. `rag.service.run_agent` 가 본 모듈의
`run_agent_langgraph` 로 위임한다.

구조:
    - LangGraph StateGraph 3 노드 + 조건 엣지
    - 노드: prepare → call_llm → execute_tools → (should_continue 분기)
    - 종료 우선순위: finish / no_tool_call / max_iter / llm_error

호환:
    - `AgentResult` (`app.domains.rag.agent`) 재사용 — 호출자 변경 0
    - chunks dedupe + tool_results 형식 유지

시각화:
    - `build_agent_graph().get_graph().draw_mermaid()` 로 mermaid 출력
    - `ica agent-graph` CLI 명령
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.domains.rag.agent import AgentResult, _get_openai_client
from app.domains.sessions.schemas import SlotState
from app.infrastructure.llm.client import get_chat_model
from app.shared.tools.definitions import ALL_TOOLS, tools_for_area
from app.shared.tools.dispatcher import (
    ToolNotFoundError,
    ToolNotImplementedError,
    invoke,
    serialize_for_llm,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITER = 5

# 강제 원칙 system prompt — 의무/권장 tool·영역별 가이드. (구 AgentRunner 에서 이전)
# 약한 프롬프트는 실 LLM tool 선택 행동을 약화시키므로 강한 버전을 단일 경로의 정본으로 사용.
_SYSTEM_PROMPT = """\
당신은 한국 보험청구심사 어시스턴트의 ReAct agent다.
사용자 슬롯과 대화 컨텍스트가 주어지면, 정확한 청구 가능성 답변을 위해
아래 tool 다발 중 필요한 것을 자가 판단해 호출한다.

**원칙 (강제)**:
1. 모든 영역에서 `search_terms` 를 최소 1회 호출 (약관 인용 의무)
2. 모든 영역에서 `validate_coverage_period` 호출 (사고일 ∈ 보장기간 검증, 의무)
3. 청구 금액 추정 시 `calc_claim_amount` 호출 (deterministic — LLM 산수 환각 회피)
4. 영역별 권장:
   - auto: `get_fault_ratio_standard` (표준 과실비율) + `lookup_law_clause` (자배법)
   - fire: `lookup_law_clause` (상법)
   - accident_disease: `get_disease_code` (KCD 코드) + `lookup_law_clause` (보험업법)
5. 같은 tool 을 동일 인자로 2회 호출 금지 (이미 결과를 받았다)
6. 정보 충분하면 `finish` tool 호출하여 종료 (즉시 generate_assessment 단계로 진입)
7. 최대 5회 iter — 도달 시 강제 종료

**현재 슬롯**:
{slots_summary}

**영역별 의무·권장**:
- 의무: {mandatory}
- 권장: {recommended}
"""


# ---------------------------------------------------------------------------
# AgentState — LangGraph state 정의
# ---------------------------------------------------------------------------


class AgentState(TypedDict, total=False):
    """LangGraph StateGraph 의 통일 state.

    AgentRunner 의 인스턴스/로컬 변수를 모두 state 로 표현해 노드 간 격리 보장.
    """

    slots: SlotState
    user_message: str
    messages: list[dict[str, Any]]            # OpenAI 대화 이력
    tool_results: list[dict[str, Any]]        # 호출 기록 (audit + assessment 용)
    chunks: list[dict[str, Any]]              # search_terms 결과 누적
    llm_calls: list[dict[str, Any]]           # LLM 호출별 관측치 (토큰/latency)
    # Sprint 13 W-2 보정: set → list — JSON 직렬화 가능, 체크포인터 도입 시 호환 보장
    visited_tools: list[str]                  # (tool_name + args_json) 중복 차단 키 목록
    iter_count: int                           # max_iter 가드
    max_iter: int                             # 설정값
    finish_reason: str                        # "" | "finish" | "no_tool_call" | "max_iter" | "llm_error"


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _slot_summary(slots: SlotState) -> str:
    parts: list[str] = []
    for field_name in ("area", "insurer", "product", "incident_date", "incident_type"):
        val = getattr(slots, field_name, None)
        if val:
            parts.append(f"{field_name}={val}")
    return ", ".join(parts) or "(empty)"


def _safe_invoke(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """dispatcher.invoke + graceful 예외 → LLM 친화 에러 dict."""
    try:
        return invoke(tool_name, args)
    except ToolNotImplementedError as exc:
        return {"error": "not_implemented", "tool": tool_name, "message": str(exc)}
    except ToolNotFoundError as exc:
        return {"error": "not_found", "tool": tool_name, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.error("dispatcher.invoke 예외 (%s): %s", tool_name, exc)
        return {"error": "runtime", "tool": tool_name, "message": str(exc)}


def _dedupe_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """동일 chunk id 중복 제거 — score 높은 것 유지."""
    by_id: dict[str, dict[str, Any]] = {}
    for c in chunks:
        cid = str(c.get("id"))
        existing = by_id.get(cid)
        if existing is None or (c.get("score") or 0) > (existing.get("score") or 0):
            by_id[cid] = c
    return list(by_id.values())


# ---------------------------------------------------------------------------
# 노드 4종
# ---------------------------------------------------------------------------


def prepare_messages(state: AgentState) -> AgentState:
    """state 초기화 — system + user 메시지 구성, visited_tools/chunks/tool_results 초기화."""
    slots = state["slots"]
    user_message = state["user_message"]

    area = slots.area or "auto"
    area_policy = tools_for_area(area)  # type: ignore[arg-type]
    system = _SYSTEM_PROMPT.format(
        slots_summary=_slot_summary(slots),
        mandatory=", ".join(area_policy["mandatory"]),
        recommended=", ".join(area_policy["recommended"]),
    )

    return {
        **state,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        "tool_results": [],
        "chunks": [],
        "llm_calls": [],
        "visited_tools": [],
        "iter_count": 0,
        "finish_reason": "",
    }


def call_llm(state: AgentState) -> AgentState:
    """LLM 호출 → assistant message + tool_calls 를 state.messages 에 누적.

    no_tool_call 시 finish_reason="no_tool_call" 설정 (should_continue 가 종료 분기).
    """
    client = _get_openai_client()
    model = get_chat_model()
    iter_count = state.get("iter_count", 0) + 1
    llm_calls = list(state.get("llm_calls", []))

    # B5 견고성 — LLM 호출 실패 시 부분 진행분(chunks/tool_results) 보존하고 graph 정상 종료.
    t0 = perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=state["messages"],
            tools=ALL_TOOLS,
            tool_choice="auto",
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = round((perf_counter() - t0) * 1000, 1)
        logger.error(
            "langgraph_agent: LLM 호출 실패 iter=%d %.1fms — llm_error 종료(부분 진행분 보존): %s",
            iter_count, latency_ms, exc,
        )
        llm_calls.append({"model": model, "latency_ms": latency_ms, "error": str(exc)})
        return {**state, "iter_count": iter_count, "llm_calls": llm_calls, "finish_reason": "llm_error"}

    latency_ms = round((perf_counter() - t0) * 1000, 1)
    msg = response.choices[0].message
    tool_calls = getattr(msg, "tool_calls", None) or []

    # B1 관측성 — 토큰 사용량 + latency 수집(usage 미제공 시 None).
    usage = getattr(response, "usage", None)
    llm_calls.append({
        "model": model,
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
        "latency_ms": latency_ms,
        "tool_calls": len(tool_calls),
    })

    new_messages = list(state["messages"])

    if not tool_calls:
        # LLM 텍스트 답변만 — 종료 신호
        logger.info("langgraph_agent: no_tool_call iter=%d %.1fms", iter_count, latency_ms)
        return {
            **state,
            "iter_count": iter_count,
            "llm_calls": llm_calls,
            "finish_reason": "no_tool_call",
        }

    # assistant message + tool_calls 누적 (OpenAI 프로토콜)
    new_messages.append(
        {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        }
    )

    # state 임시 저장: execute_tools 에서 message 의 tool_calls 읽음
    return {
        **state,
        "messages": new_messages,
        "iter_count": iter_count,
        "llm_calls": llm_calls,
    }


def execute_tools(state: AgentState) -> AgentState:
    """state.messages 의 마지막 assistant tool_calls 실행 + tool message 누적.

    중복 호출 차단 (visited_tools). search_terms 결과는 chunks 에 누적.
    finish tool 감지 시 finish_reason="finish".
    """
    messages = list(state["messages"])
    tool_results = list(state.get("tool_results", []))
    chunks = list(state.get("chunks", []))
    visited_tools = list(state.get("visited_tools", []))  # set → list (W-2 보정)
    finish_reason = state.get("finish_reason", "")

    # 마지막 assistant message 의 tool_calls 가져옴
    last_assistant = messages[-1]
    tool_calls = last_assistant.get("tool_calls", [])

    for tc in tool_calls:
        tool_name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}

        # 중복 차단 (W-2 보정: visited_tools 가 list 이므로 in 연산 — 규모 작아 무시 가능)
        key = f"{tool_name}::{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        if key in visited_tools:
            logger.info("langgraph_agent: 중복 tool skip (%s)", tool_name)
            tool_result: dict[str, Any] = {"skipped": "duplicate"}
            latency_ms = 0.0
        else:
            visited_tools.append(key)
            t0 = perf_counter()
            tool_result = _safe_invoke(tool_name, args)
            latency_ms = round((perf_counter() - t0) * 1000, 1)

        # B1 관측성 — tool 별 latency + 성공여부(error 키 부재) 기록.
        tool_results.append({
            "tool": tool_name,
            "args": args,
            "result": tool_result,
            "latency_ms": latency_ms,
            "ok": "error" not in tool_result,
        })

        # search_terms 결과 → chunks 누적
        if tool_name == "search_terms" and "chunks" in tool_result:
            chunks.extend(tool_result["chunks"])

        # finish tool 감지
        if tool_name == "finish":
            finish_reason = "finish"

        # tool message 누적
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": serialize_for_llm(tool_result),
            }
        )

    return {
        **state,
        "messages": messages,
        "tool_results": tool_results,
        "chunks": chunks,
        "visited_tools": visited_tools,
        "finish_reason": finish_reason,
    }


def should_continue(state: AgentState) -> str:
    """조건 엣지 — execute_tools 이후 종료 3 우선순위 검사.

    W-3 보정: no_tool_call 분기는 `after_llm` (call_llm 직후) 이 처리하므로
    여기서 도달 불가. execute_tools 는 tool_calls 가 있을 때만 라우팅되므로 finish + max_iter 만 검사.
    """
    # 1. finish tool 호출됨
    if state.get("finish_reason") == "finish":
        return END
    # 2. max_iter 도달
    if state.get("iter_count", 0) >= state.get("max_iter", DEFAULT_MAX_ITER):
        logger.warning(
            "langgraph_agent: max_iter (%d) 도달 — 강제 종료",
            state.get("max_iter", DEFAULT_MAX_ITER),
        )
        return END
    # 계속
    return "call_llm"


# ---------------------------------------------------------------------------
# StateGraph 빌드 + 실행
# ---------------------------------------------------------------------------


def _build_agent_graph_uncached() -> CompiledStateGraph:
    """LangGraph StateGraph 컴파일 결과 반환 (캐시 없음).

    노드: prepare → call_llm → (after_llm 분기) → execute_tools → (should_continue 분기)
    """
    graph = StateGraph(AgentState)
    graph.add_node("prepare", prepare_messages)
    graph.add_node("call_llm", call_llm)
    graph.add_node("execute_tools", execute_tools)

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "call_llm")

    # call_llm 후 no_tool_call/llm_error 이면 즉시 종료, 아니면 execute_tools
    def after_llm(state: AgentState) -> str:
        if state.get("finish_reason") in ("no_tool_call", "llm_error"):
            return END
        return "execute_tools"

    graph.add_conditional_edges("call_llm", after_llm, {END: END, "execute_tools": "execute_tools"})
    graph.add_conditional_edges(
        "execute_tools",
        should_continue,
        {END: END, "call_llm": "call_llm"},
    )

    return graph.compile()


@lru_cache(maxsize=1)
def build_agent_graph() -> CompiledStateGraph:
    """compile 결과 캐시 (W-5 보정).

    visited_tools 격리는 prepare_messages 노드에서 매 invoke 초기화하므로 graph 재사용 안전.
    테스트는 `clear_agent_graph_cache()` 호출로 격리.
    """
    return _build_agent_graph_uncached()


def clear_agent_graph_cache() -> None:
    """테스트용 — compile 결과 캐시 초기화."""
    build_agent_graph.cache_clear()


def run_agent_langgraph(
    slots: SlotState,
    user_message: str,
    *,
    max_iter: int = DEFAULT_MAX_ITER,
) -> AgentResult:
    """AgentRunner.run() 동등 시그니처 — LangGraph 구현체.

    Args:
        slots: SlotState
        user_message: 사용자 자연어 입력
        max_iter: ReAct loop 최대 반복 (기본 5)

    Returns:
        AgentResult (chunks dedupe + tool_results + iterations + finish_reason)
    """
    app_graph = build_agent_graph()
    initial: AgentState = {
        "slots": slots,
        "user_message": user_message,
        "max_iter": max_iter,
        "iter_count": 0,
        "messages": [],
        "tool_results": [],
        "chunks": [],
        "llm_calls": [],
        "visited_tools": [],  # set → list (W-2 보정)
        "finish_reason": "",
    }

    # LangGraph 의 invoke 는 max recursion 제한 — max_iter * 2 (call_llm + execute_tools 왕복) + 여유
    final_state = app_graph.invoke(initial, config={"recursion_limit": max_iter * 2 + 4})

    finish_reason = final_state.get("finish_reason") or "max_iter"

    result = AgentResult(
        chunks=_dedupe_chunks(final_state.get("chunks", [])),
        tool_results=final_state.get("tool_results", []),
        llm_calls=final_state.get("llm_calls", []),
        iterations=final_state.get("iter_count", 0),
        finish_reason=finish_reason,
    )
    return result
