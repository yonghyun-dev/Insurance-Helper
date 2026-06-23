"""tests.rag.test_langgraph_agent

app/rag/langgraph_agent.py 단위 테스트.

테스트 대상:
    - AgentState TypedDict 형식 + 헬퍼 함수
    - 노드 4종 (prepare_messages / call_llm / execute_tools / should_continue)
    - build_agent_graph() 컴파일 + draw_mermaid
    - run_agent_langgraph 통합 (AgentRunner 와 동등 시그니처)

Sprint 13 (REQ-12) — AgentRunner → LangGraph 점진 마이그레이션. AgentRunner 의 회귀 0
유지 + LangGraph backend 의 동등 결과 보장.

OpenAI mock 패턴: `app.domains.rag.langgraph_agent._get_openai_client` monkeypatch
(AgentRunner 의 _get_openai_client 재사용 — agent.py:_get_openai_client lru_cache).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from app.domains.rag import langgraph_agent as lg
from app.domains.rag.agent import AgentResult
from app.domains.sessions.schemas import SlotState

# ---------------------------------------------------------------------------
# 헬퍼 — fake OpenAI client
# ---------------------------------------------------------------------------


def _make_tool_call(call_id: str, name: str, args: dict[str, Any]):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _make_response(content: str = "", tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _make_fake_client(responses: list):
    """`responses` 는 LLM 응답 시퀀스 (각 turn 마다 하나씩 반환)."""
    iter_resp = iter(responses)

    class _Client:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(*_a, **_kw):
                    return next(iter_resp)

    return _Client()


@pytest.fixture
def auto_slots() -> SlotState:
    return SlotState(area="auto", insurer="hanwha")


# ===========================================================================
# 헬퍼 함수
# ===========================================================================


class TestHelpers:
    def test_slot_summary_empty(self):
        s = SlotState()
        assert lg._slot_summary(s) == "(empty)"

    def test_slot_summary_partial(self):
        s = SlotState(area="auto", insurer="hanwha")
        result = lg._slot_summary(s)
        assert "area=auto" in result
        assert "insurer=hanwha" in result

    def test_dedupe_chunks_keeps_highest_score(self):
        chunks = [
            {"id": "c1", "score": 0.5, "text": "low"},
            {"id": "c1", "score": 0.9, "text": "high"},
            {"id": "c2", "score": 0.7, "text": "other"},
        ]
        result = lg._dedupe_chunks(chunks)
        ids = {c["id"]: c["score"] for c in result}
        assert ids == {"c1": 0.9, "c2": 0.7}

    def test_safe_invoke_unknown_tool(self):
        result = lg._safe_invoke("nonexistent_tool", {})
        assert result["error"] == "not_found"

    def test_safe_invoke_finish_tool(self):
        # finish 는 dispatcher 가 인라인 반환
        result = lg._safe_invoke("finish", {"reason": "done"})
        assert result.get("finished") is True


# ===========================================================================
# 노드 단위
# ===========================================================================


class TestPrepareMessages:
    def test_initial_state(self, auto_slots):
        state = lg.prepare_messages(
            {"slots": auto_slots, "user_message": "사고 났어요", "max_iter": 5}
        )
        assert len(state["messages"]) == 2
        assert state["messages"][0]["role"] == "system"
        assert "area=auto" in state["messages"][0]["content"]
        assert state["messages"][1]["role"] == "user"
        assert state["messages"][1]["content"] == "사고 났어요"
        assert state["iter_count"] == 0
        assert state["chunks"] == []
        assert state["tool_results"] == []
        # W-2 보정: set → list (JSON 직렬화 가능)
        assert state["visited_tools"] == []


class TestShouldContinue:
    def test_finish_returns_end(self):
        from langgraph.graph import END

        state = {"finish_reason": "finish", "iter_count": 1, "max_iter": 5}
        assert lg.should_continue(state) == END

    def test_no_tool_call_handled_by_after_llm_not_should_continue(self):
        """W-3 보정: should_continue 는 execute_tools 이후만 호출되므로 no_tool_call 분기 없음.

        no_tool_call 종료는 build_agent_graph 의 after_llm conditional edge 가 처리.
        """
        # no_tool_call 상태에서 should_continue 가 호출되면 (도달 불가능 경로) 그냥 call_llm 반환
        state = {"finish_reason": "no_tool_call", "iter_count": 1, "max_iter": 5}
        assert lg.should_continue(state) == "call_llm"

    def test_max_iter_returns_end(self):
        from langgraph.graph import END

        state = {"finish_reason": "", "iter_count": 5, "max_iter": 5}
        assert lg.should_continue(state) == END

    def test_continue_returns_call_llm(self):
        state = {"finish_reason": "", "iter_count": 2, "max_iter": 5}
        assert lg.should_continue(state) == "call_llm"


class TestCallLlmNode:
    def test_no_tool_call_sets_finish_reason(self, auto_slots, monkeypatch):
        client = _make_fake_client([_make_response(content="텍스트만")])
        monkeypatch.setattr(lg, "_get_openai_client", lambda: client)

        state = lg.prepare_messages(
            {"slots": auto_slots, "user_message": "테스트", "max_iter": 5}
        )
        new_state = lg.call_llm(state)
        assert new_state["finish_reason"] == "no_tool_call"
        assert new_state["iter_count"] == 1

    def test_tool_calls_appended_to_messages(self, auto_slots, monkeypatch):
        tcs = [_make_tool_call("tc1", "search_terms", {"query": "보장범위"})]
        client = _make_fake_client([_make_response(tool_calls=tcs)])
        monkeypatch.setattr(lg, "_get_openai_client", lambda: client)

        state = lg.prepare_messages(
            {"slots": auto_slots, "user_message": "테스트", "max_iter": 5}
        )
        new_state = lg.call_llm(state)
        assert new_state["finish_reason"] == ""
        assert new_state["iter_count"] == 1
        # assistant message 가 추가됨
        last = new_state["messages"][-1]
        assert last["role"] == "assistant"
        assert len(last["tool_calls"]) == 1


class TestExecuteToolsNode:
    def test_finish_tool_sets_finish_reason(self, monkeypatch):
        # dispatcher.invoke 가 finish 호출 시 {"finished": True} 반환
        state: lg.AgentState = {
            "slots": SlotState(),
            "user_message": "",
            "messages": [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc1",
                            "type": "function",
                            "function": {"name": "finish", "arguments": "{}"},
                        }
                    ],
                }
            ],
            "tool_results": [],
            "chunks": [],
            "visited_tools": [],
            "iter_count": 1,
            "max_iter": 5,
            "finish_reason": "",
        }
        new_state = lg.execute_tools(state)
        assert new_state["finish_reason"] == "finish"
        assert len(new_state["tool_results"]) == 1
        assert new_state["tool_results"][0]["tool"] == "finish"

    def test_duplicate_tool_skipped(self, monkeypatch):
        # 동일 (tool, args) 두 번 호출 — 두 번째는 skipped
        state: lg.AgentState = {
            "slots": SlotState(),
            "user_message": "",
            "messages": [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc1",
                            "type": "function",
                            "function": {"name": "finish", "arguments": "{}"},
                        },
                        {
                            "id": "tc2",
                            "type": "function",
                            "function": {"name": "finish", "arguments": "{}"},
                        },
                    ],
                }
            ],
            "tool_results": [],
            "chunks": [],
            "visited_tools": [],
            "iter_count": 1,
            "max_iter": 5,
            "finish_reason": "",
        }
        new_state = lg.execute_tools(state)
        assert len(new_state["tool_results"]) == 2
        # 두 번째는 skipped
        assert new_state["tool_results"][1]["result"].get("skipped") == "duplicate"


# ===========================================================================
# StateGraph 빌드 + 시각화
# ===========================================================================


class TestBuildAgentGraph:
    def test_graph_compiles(self):
        graph = lg.build_agent_graph()
        assert graph is not None

    def test_draw_mermaid_includes_nodes(self):
        graph = lg.build_agent_graph()
        mermaid = graph.get_graph().draw_mermaid()
        assert "prepare" in mermaid
        assert "call_llm" in mermaid
        assert "execute_tools" in mermaid


# ===========================================================================
# run_agent_langgraph 통합 (AgentRunner 동등 시그니처)
# ===========================================================================


class TestRunAgentLanggraph:
    def test_returns_agent_result_type(self, auto_slots, monkeypatch):
        # finish 즉시 호출 시나리오 (1 turn)
        tcs = [_make_tool_call("tc1", "finish", {"reason": "done"})]
        client = _make_fake_client([_make_response(tool_calls=tcs)])
        monkeypatch.setattr(lg, "_get_openai_client", lambda: client)

        result = lg.run_agent_langgraph(auto_slots, "사고 났어요")
        assert isinstance(result, AgentResult)
        assert result.finish_reason == "finish"
        assert result.iterations == 1
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool"] == "finish"

    def test_no_tool_call_returns_immediately(self, auto_slots, monkeypatch):
        client = _make_fake_client([_make_response(content="텍스트만")])
        monkeypatch.setattr(lg, "_get_openai_client", lambda: client)

        result = lg.run_agent_langgraph(auto_slots, "테스트")
        assert result.finish_reason == "no_tool_call"
        assert result.chunks == []
        assert result.tool_results == []

    def test_max_iter_termination(self, auto_slots, monkeypatch):
        # finish 안 부르고 매 turn search_terms (다른 args) — max_iter 도달
        # 각 turn 마다 unique args 로 중복 차단 피함
        responses = [
            _make_response(
                tool_calls=[
                    _make_tool_call(f"tc{i}", "search_terms", {"query": f"q{i}"})
                ]
            )
            for i in range(10)
        ]
        client = _make_fake_client(responses)
        monkeypatch.setattr(lg, "_get_openai_client", lambda: client)
        # search_terms 가 실제 search.service 호출 안 하도록 dispatcher.invoke mock
        from app.domains.rag import langgraph_agent as lg_mod

        monkeypatch.setattr(
            lg_mod, "invoke", lambda name, args: {"chunks": [{"id": f"c-{args.get('query')}", "score": 0.5, "text": "x"}]}
        )

        result = lg.run_agent_langgraph(auto_slots, "테스트", max_iter=3)
        assert result.finish_reason == "max_iter"
        assert result.iterations == 3
