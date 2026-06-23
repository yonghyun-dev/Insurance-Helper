"""app.domains.rag.langgraph_agent

파일 경로: app/rag/langgraph_agent.py
목적: Sprint 13 (REQ-12) — LangGraph StateGraph 로 ReAct loop 재구성.

설계 (tech-decisions § Sprint 13):
    - 기존 `app.domains.rag.agent.AgentRunner` 와 **동등한 외부 시그니처** 유지
      → `run_agent_langgraph(slots, user_message) -> AgentResult`
    - 내부는 LangGraph StateGraph 4 노드 + 조건 엣지로 표준화
    - 노드: prepare → call_llm → execute_tools → (should_continue 분기)
    - 종료 4 우선순위: finish / no_tool_call / max_iter / 외부 예외

Sprint 13 점진 마이그레이션:
    - env 토글 `RAG_BACKEND=agentrunner|langgraph` 로 분기
    - 기본 agentrunner — Sprint 14~15 안정화 후 chore commit 으로 폐기

호환성:
    - `AgentResult` (`app.domains.rag.agent`) 그대로 재사용 — 호출자 변경 0
    - chunks dedupe + tool_results 형식 동일

시각화:
    - `build_agent_graph().get_graph().draw_mermaid()` 로 mermaid 출력
    - `ica agent-graph` CLI 명령 (Sprint 13 T7)
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
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

# AgentRunner._SYSTEM_PROMPT 재사용을 위한 import
_SYSTEM_PROMPT = (
    "당신은 보험 청구 가능성 분석 어시스턴트의 ReAct agent 다.\n"
    "현재 슬롯 요약: {slots_summary}\n\n"
    "필수 호출 tool: {mandatory}\n"
    "권장 호출 tool: {recommended}\n\n"
    "위 tool 들을 자유롭게 호출하여 정보를 수집한 뒤 충분하다고 판단되면 "
    "`finish` tool 을 호출하여 종료한다. 최대 5 turn 이내에 종료해야 한다.\n"
    "동일한 tool 을 동일한 인자로 두 번 이상 호출하지 말 것."
)


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
    # Sprint 13 W-2 보정: set → list — JSON 직렬화 가능, 체크포인터 도입 시 호환 보장
    visited_tools: list[str]                  # (tool_name + args_json) 중복 차단 키 목록
    iter_count: int                           # max_iter 가드
    max_iter: int                             # 설정값
    finish_reason: str                        # "" | "finish" | "no_tool_call" | "max_iter"


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
        "visited_tools": [],
        "iter_count": 0,
        "finish_reason": "",
    }


def call_llm(state: AgentState) -> AgentState:
    """LLM 호출 → assistant message + tool_calls 를 state.messages 에 누적.

    no_tool_call 시 finish_reason="no_tool_call" 설정 (should_continue 가 종료 분기).
    """
    client = _get_openai_client()

    response = client.chat.completions.create(
        model=get_chat_model(),
        messages=state["messages"],
        tools=ALL_TOOLS,
        tool_choice="auto",
        temperature=0.0,
    )
    msg = response.choices[0].message
    tool_calls = getattr(msg, "tool_calls", None) or []

    iter_count = state.get("iter_count", 0) + 1
    new_messages = list(state["messages"])

    if not tool_calls:
        # LLM 텍스트 답변만 — 종료 신호
        logger.info("langgraph_agent: no_tool_call iter=%d", iter_count)
        return {
            **state,
            "iter_count": iter_count,
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
        else:
            visited_tools.append(key)
            tool_result = _safe_invoke(tool_name, args)

        tool_results.append({"tool": tool_name, "args": args, "result": tool_result})

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

    # call_llm 후 no_tool_call 이면 즉시 종료, 아니면 execute_tools
    def after_llm(state: AgentState) -> str:
        if state.get("finish_reason") == "no_tool_call":
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
        "visited_tools": [],  # set → list (W-2 보정)
        "finish_reason": "",
    }

    # LangGraph 의 invoke 는 max recursion 제한 — max_iter * 2 (call_llm + execute_tools 왕복) + 여유
    final_state = app_graph.invoke(initial, config={"recursion_limit": max_iter * 2 + 4})

    finish_reason = final_state.get("finish_reason") or "max_iter"

    result = AgentResult(
        chunks=_dedupe_chunks(final_state.get("chunks", [])),
        tool_results=final_state.get("tool_results", []),
        iterations=final_state.get("iter_count", 0),
        finish_reason=finish_reason,
    )
    return result
