"""tests.rag.test_agent

app/domains/rag/agent.py 단위 테스트.

Sprint 24 그래프 일원화로 구 `AgentRunner` 는 제거되고 본 모듈은 공용 타입 `AgentResult`
와 추론 클라이언트 팩토리 `_get_openai_client` 만 보유한다. ReAct loop 동작/헬퍼
(_slot_summary/_dedupe_chunks/_safe_invoke/노드/run)는 `tests/rag/test_langgraph_agent.py`
가 단일 경로(LangGraph)로 커버한다.
"""

from __future__ import annotations

from app.domains.rag.agent import AgentResult, _get_openai_client


class TestAgentResult:
    """AgentResult dataclass 기본값 + 필드 접근 + mutable 격리."""

    def test_default_values(self):
        result = AgentResult()
        assert result.chunks == []
        assert result.tool_results == []
        assert result.iterations == 0
        assert result.finish_reason == ""

    def test_field_assignment(self):
        result = AgentResult(
            chunks=[{"id": "c1"}],
            tool_results=[{"tool": "finish"}],
            iterations=2,
            finish_reason="finish",
        )
        assert result.chunks[0]["id"] == "c1"
        assert result.tool_results[0]["tool"] == "finish"
        assert result.iterations == 2
        assert result.finish_reason == "finish"

    def test_chunks_are_independent_per_instance(self):
        """mutable 기본값 공유 없음 (dataclass field default_factory)."""
        r1 = AgentResult()
        r2 = AgentResult()
        r1.chunks.append({"id": "x"})
        assert r2.chunks == []


class TestGetOpenAiClient:
    """_get_openai_client — 중앙 LLM 팩토리(get_chat_client)에 위임."""

    def test_delegates_to_chat_client_factory(self, monkeypatch):
        import app.domains.rag.agent as agent_mod

        sentinel = object()
        monkeypatch.setattr(agent_mod, "get_chat_client", lambda: sentinel)
        assert _get_openai_client() is sentinel
