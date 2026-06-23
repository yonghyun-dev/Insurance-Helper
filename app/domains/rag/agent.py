"""app.domains.rag.agent

파일 경로: app/domains/rag/agent.py
목적: ReAct 에이전트 공용 타입/클라이언트.

구 `AgentRunner`(수기 ReAct loop)는 Sprint 24 그래프 일원화로 제거되고, 단일 경로인
`app.domains.rag.langgraph_agent`(LangGraph StateGraph)로 대체되었다. 본 모듈은
LangGraph 구현이 공유하는 **반환 타입 `AgentResult`** 와 **추론 LLM 클라이언트 팩토리
`_get_openai_client`** 만 보유한다(심볼명 유지 — langgraph_agent 와 테스트가 의존).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from app.infrastructure.llm.client import get_chat_client


def _get_openai_client() -> OpenAI:
    """추론 LLM 클라이언트 — 중앙 팩토리(app.infrastructure.llm.client)에 위임.

    제품 추론은 Upstage Solar 전용(provider=upstage 기본), OpenAI 폴백 없음.
    심볼명 유지 — langgraph_agent 와 테스트가 본 함수를 import/패치한다. 캐시는 팩토리가 담당.
    """
    return get_chat_client()


@dataclass
class AgentResult:
    """LangGraph 에이전트(run_agent_langgraph)의 반환 형식.

    sessions.service 가 chunks 를 generate_assessment 에 전달 + tool_results 를
    추가 컨텍스트 + audit trace 로 넘긴다.
    """

    chunks: list[dict[str, Any]] = field(default_factory=list)  # search_terms 결과 누적
    tool_results: list[dict[str, Any]] = field(default_factory=list)  # 모든 tool 호출 결과
    # LLM 호출별 관측치 — {model, prompt_tokens, completion_tokens, total_tokens, latency_ms}
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    finish_reason: str = ""  # "finish" / "max_iter" / "no_tool_call" / "llm_error"
