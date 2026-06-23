"""tests.rag.test_agent_backends_equivalence

AgentRunner (app.domains.rag.agent) ↔ run_agent_langgraph (app.domains.rag.langgraph_agent) 결과 동등성 검증.

Sprint 13 (REQ-12) — 두 backend 가 동일 fake OpenAI 응답 시퀀스를 받았을 때
동등한 AgentResult 를 반환하는지 확인한다.

검증 시나리오:
    1. finish 즉시 — 1 turn, finish tool 호출, finish_reason="finish"
    2. max_iter 도달 — finish 없이 계속 tool 호출, finish_reason="max_iter"
    3. 중복 tool 차단 — 동일 (tool, args) 두 번 → 두 번째는 skipped, 양 backend 동일

비교 기준:
    - finish_reason 동일
    - iterations 동일
    - tool_results 길이 동일
    - chunks (id 기준 정렬) 동일

mock 정책:
    - AgentRunner: _get_openai_client monkeypatch (agent 모듈)
    - run_agent_langgraph: _get_openai_client monkeypatch (langgraph_agent 모듈) +
                            dispatcher.invoke monkeypatch (search_terms 실 호출 방지)
    - 각 backend 를 별도 test 함수에서 실행 (lru_cache 충돌 방지)
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.domains.rag import langgraph_agent as lg
from app.domains.rag.agent import AgentResult, AgentRunner
from app.domains.sessions.schemas import SlotState

# ---------------------------------------------------------------------------
# 헬퍼 — fake OpenAI 응답 빌더 (양 backend 공용 형식 분리)
# ---------------------------------------------------------------------------


def _ns_tool_call(call_id: str, name: str, args: dict[str, Any]):
    """langgraph_agent 가 사용하는 SimpleNamespace 기반 tool_call."""
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _mock_tool_call(call_id: str, name: str, args: dict[str, Any]) -> MagicMock:
    """AgentRunner 가 사용하는 MagicMock 기반 tool_call."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args, ensure_ascii=False)
    return tc


def _ns_response(content: str = "", tool_calls=None):
    """langgraph_agent 용 SimpleNamespace 응답."""
    msg = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _mock_response(tool_calls=None, content: str = "") -> MagicMock:
    """AgentRunner 용 MagicMock 응답."""
    resp = MagicMock()
    resp.choices[0].message.content = content
    resp.choices[0].message.tool_calls = tool_calls
    return resp


def _make_lg_client(responses: list):
    """langgraph_agent 용 fake client (SimpleNamespace 방식)."""
    iter_resp = iter(responses)

    class _Client:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(*_a, **_kw):
                    return next(iter_resp)

    return _Client()


def _make_agent_client(responses: list) -> MagicMock:
    """AgentRunner 용 fake client (MagicMock 방식)."""
    client = MagicMock()
    client.chat.completions.create.side_effect = responses
    return client


@pytest.fixture()
def auto_slots() -> SlotState:
    """auto 영역 최소 슬롯 — 양 backend 공용 픽스처."""
    return SlotState(area="auto", insurer="한화손해보험")


# ---------------------------------------------------------------------------
# 시나리오 1 — finish 즉시 (1 turn)
# ---------------------------------------------------------------------------


class TestEquivalenceFinishImmediate:
    """finish tool 1회 호출 시나리오 — 양 backend 동등성.

    각 테스트는 AgentRunner / LangGraph 를 순서대로 실행해 결과를 비교한다.
    monkeypatch 는 각 _run_* 헬퍼 내에서 설정하며, 함수 종료 시 monkeypatch 가 자동 복원됨.
    """

    def _run_agentrunner(self, slots: SlotState, monkeypatch) -> AgentResult:
        """AgentRunner backend 실행 (lru_cache 우회: 직접 함수 교체)."""
        import app.domains.rag.agent as agent_mod

        tc = _mock_tool_call("tc1", "finish", {"reason": "done"})
        client = _make_agent_client([_mock_response(tool_calls=[tc])])

        # lru_cache 된 함수를 lambda 로 직접 교체 (monkeypatch 가 원본 복원함)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: client)
        runner = AgentRunner(max_iter=5)
        return runner.run(slots, "사고 났어요")

    def _run_langgraph(self, slots: SlotState, monkeypatch) -> AgentResult:
        """LangGraph backend 실행."""
        import app.domains.rag.agent as agent_mod

        tc = _ns_tool_call("tc1", "finish", {"reason": "done"})
        client = _make_lg_client([_ns_response(tool_calls=[tc])])
        # langgraph_agent._get_openai_client 는 agent.py 에서 import 된 것 재사용
        # → lg 모듈과 agent_mod 양쪽 교체
        monkeypatch.setattr(lg, "_get_openai_client", lambda: client)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: client)
        return lg.run_agent_langgraph(slots, "사고 났어요", max_iter=5)

    def test_agentrunner_finish_reason(self, auto_slots, monkeypatch):
        """AgentRunner: finish_reason="finish"."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        assert result.finish_reason == "finish", f"finish_reason={result.finish_reason!r}"

    def test_langgraph_finish_reason(self, auto_slots, monkeypatch):
        """LangGraph: finish_reason="finish"."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        assert result.finish_reason == "finish", f"finish_reason={result.finish_reason!r}"

    def test_agentrunner_iterations(self, auto_slots, monkeypatch):
        """AgentRunner: iterations=1."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        assert result.iterations == 1, f"iterations={result.iterations}"

    def test_langgraph_iterations(self, auto_slots, monkeypatch):
        """LangGraph: iterations=1."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        assert result.iterations == 1, f"iterations={result.iterations}"

    def test_agentrunner_tool_results_length(self, auto_slots, monkeypatch):
        """AgentRunner: tool_results 1건 (finish)."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        assert len(result.tool_results) == 1, f"tool_results={len(result.tool_results)}"

    def test_langgraph_tool_results_length(self, auto_slots, monkeypatch):
        """LangGraph: tool_results 1건 (finish)."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        assert len(result.tool_results) == 1, f"tool_results={len(result.tool_results)}"

    def test_agentrunner_chunks_empty(self, auto_slots, monkeypatch):
        """AgentRunner: chunks 빈 리스트 (finish only)."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        assert result.chunks == [], f"chunks={result.chunks}"

    def test_langgraph_chunks_empty(self, auto_slots, monkeypatch):
        """LangGraph: chunks 빈 리스트 (finish only)."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        assert result.chunks == [], f"chunks={result.chunks}"


# ---------------------------------------------------------------------------
# 시나리오 2 — max_iter 도달
# ---------------------------------------------------------------------------

_MAX_ITER = 3


class TestEquivalenceMaxIter:
    """finish 없이 max_iter 도달 시나리오 — 양 backend 동등성."""

    def _fake_invoke(self, name: str, args: dict) -> dict:
        """search_terms 실 호출 방지용 fake dispatcher.invoke."""
        if name == "search_terms":
            return {"chunks": [{"id": f"c-{args.get('query')}", "score": 0.5, "text": "x"}]}
        return {"finished": True}

    def _build_agent_responses(self) -> list:
        """AgentRunner 용 — max_iter+2 개 응답 (각 turn 다른 args)."""
        return [
            _mock_response(
                tool_calls=[_mock_tool_call(f"tc{i}", "search_terms", {"query": f"질의{i}"})]
            )
            for i in range(_MAX_ITER + 2)
        ]

    def _build_lg_responses(self) -> list:
        """LangGraph 용 — max_iter+2 개 응답."""
        return [
            _ns_response(
                tool_calls=[_ns_tool_call(f"tc{i}", "search_terms", {"query": f"질의{i}"})]
            )
            for i in range(_MAX_ITER + 2)
        ]

    def _run_agentrunner(self, slots: SlotState, monkeypatch) -> AgentResult:
        import app.domains.rag.agent as agent_mod

        client = _make_agent_client(self._build_agent_responses())
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: client)
        monkeypatch.setattr(agent_mod, "invoke", self._fake_invoke)
        runner = AgentRunner(max_iter=_MAX_ITER)
        return runner.run(slots, "사고 났어요")

    def _run_langgraph(self, slots: SlotState, monkeypatch) -> AgentResult:
        import app.domains.rag.agent as agent_mod

        client = _make_lg_client(self._build_lg_responses())
        monkeypatch.setattr(lg, "_get_openai_client", lambda: client)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: client)
        monkeypatch.setattr(lg, "invoke", self._fake_invoke)
        return lg.run_agent_langgraph(slots, "사고 났어요", max_iter=_MAX_ITER)

    def test_agentrunner_finish_reason_max_iter(self, auto_slots, monkeypatch):
        """AgentRunner: finish_reason="max_iter"."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        assert result.finish_reason == "max_iter", f"finish_reason={result.finish_reason!r}"

    def test_langgraph_finish_reason_max_iter(self, auto_slots, monkeypatch):
        """LangGraph: finish_reason="max_iter"."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        assert result.finish_reason == "max_iter", f"finish_reason={result.finish_reason!r}"

    def test_agentrunner_iterations_equal_max_iter(self, auto_slots, monkeypatch):
        """AgentRunner: iterations == max_iter."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        assert result.iterations == _MAX_ITER, (
            f"iterations={result.iterations}, 기대={_MAX_ITER}"
        )

    def test_langgraph_iterations_equal_max_iter(self, auto_slots, monkeypatch):
        """LangGraph: iterations == max_iter."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        assert result.iterations == _MAX_ITER, (
            f"iterations={result.iterations}, 기대={_MAX_ITER}"
        )

    def test_agentrunner_tool_results_length(self, auto_slots, monkeypatch):
        """AgentRunner: tool_results 개수 == max_iter (각 turn 1 tool_call)."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        assert len(result.tool_results) == _MAX_ITER, (
            f"tool_results={len(result.tool_results)}, 기대={_MAX_ITER}"
        )

    def test_langgraph_tool_results_length(self, auto_slots, monkeypatch):
        """LangGraph: tool_results 개수 == max_iter."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        assert len(result.tool_results) == _MAX_ITER, (
            f"tool_results={len(result.tool_results)}, 기대={_MAX_ITER}"
        )

    def test_agentrunner_chunks_count(self, auto_slots, monkeypatch):
        """AgentRunner: chunks 개수 == max_iter (각 turn 다른 id, dedupe 후 유지)."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        assert len(result.chunks) == _MAX_ITER, (
            f"chunks={len(result.chunks)}, 기대={_MAX_ITER}"
        )

    def test_langgraph_chunks_count(self, auto_slots, monkeypatch):
        """LangGraph: chunks 개수 == max_iter."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        assert len(result.chunks) == _MAX_ITER, (
            f"chunks={len(result.chunks)}, 기대={_MAX_ITER}"
        )


# ---------------------------------------------------------------------------
# 시나리오 3 — 중복 tool 차단
# ---------------------------------------------------------------------------


class TestEquivalenceDuplicateBlocking:
    """동일 (tool, args) 두 번 호출 시 두 번째는 skipped — 양 backend 동등성."""

    def _fake_invoke(self, name: str, args: dict) -> dict:
        if name == "search_terms":
            return {"chunks": [{"id": "chunk-추돌", "score": 0.8, "text": "추돌 관련"}]}
        return {"finished": True}

    def _build_agent_responses(self) -> list:
        """1 turn: search_terms + search_terms(중복) + finish."""
        tc1 = _mock_tool_call("tc1", "search_terms", {"query": "추돌"})
        tc2 = _mock_tool_call("tc2", "search_terms", {"query": "추돌"})  # 중복
        tc3 = _mock_tool_call("tc3", "finish", {})
        return [_mock_response(tool_calls=[tc1, tc2, tc3])]

    def _build_lg_responses(self) -> list:
        """1 turn: search_terms + search_terms(중복) + finish."""
        tc1 = _ns_tool_call("tc1", "search_terms", {"query": "추돌"})
        tc2 = _ns_tool_call("tc2", "search_terms", {"query": "추돌"})  # 중복
        tc3 = _ns_tool_call("tc3", "finish", {})
        return [_ns_response(tool_calls=[tc1, tc2, tc3])]

    def _run_agentrunner(self, slots: SlotState, monkeypatch) -> AgentResult:
        import app.domains.rag.agent as agent_mod

        client = _make_agent_client(self._build_agent_responses())
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: client)
        monkeypatch.setattr(agent_mod, "invoke", self._fake_invoke)
        runner = AgentRunner(max_iter=5)
        return runner.run(slots, "추돌 사고")

    def _run_langgraph(self, slots: SlotState, monkeypatch) -> AgentResult:
        import app.domains.rag.agent as agent_mod

        client = _make_lg_client(self._build_lg_responses())
        monkeypatch.setattr(lg, "_get_openai_client", lambda: client)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: client)
        monkeypatch.setattr(lg, "invoke", self._fake_invoke)
        return lg.run_agent_langgraph(slots, "추돌 사고", max_iter=5)

    def test_agentrunner_finish_reason(self, auto_slots, monkeypatch):
        """AgentRunner: finish_reason="finish"."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        assert result.finish_reason == "finish", f"finish_reason={result.finish_reason!r}"

    def test_langgraph_finish_reason(self, auto_slots, monkeypatch):
        """LangGraph: finish_reason="finish"."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        assert result.finish_reason == "finish", f"finish_reason={result.finish_reason!r}"

    def test_agentrunner_tool_results_count(self, auto_slots, monkeypatch):
        """AgentRunner: tool_results 3건 (search×2 + finish×1)."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        assert len(result.tool_results) == 3, f"tool_results={len(result.tool_results)}"

    def test_langgraph_tool_results_count(self, auto_slots, monkeypatch):
        """LangGraph: tool_results 3건 (search×2 + finish×1)."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        assert len(result.tool_results) == 3, f"tool_results={len(result.tool_results)}"

    def test_agentrunner_second_search_terms_skipped(self, auto_slots, monkeypatch):
        """AgentRunner: 두 번째 search_terms 결과 skipped=duplicate."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        search_results = [tr for tr in result.tool_results if tr["tool"] == "search_terms"]
        assert len(search_results) == 2, f"search_terms 건수={len(search_results)}"
        assert search_results[1]["result"].get("skipped") == "duplicate", (
            f"두 번째 결과={search_results[1]['result']}"
        )

    def test_langgraph_second_search_terms_skipped(self, auto_slots, monkeypatch):
        """LangGraph: 두 번째 search_terms 결과 skipped=duplicate."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        search_results = [tr for tr in result.tool_results if tr["tool"] == "search_terms"]
        assert len(search_results) == 2, f"search_terms 건수={len(search_results)}"
        assert search_results[1]["result"].get("skipped") == "duplicate", (
            f"두 번째 결과={search_results[1]['result']}"
        )

    def test_agentrunner_chunks_dedupe_one_item(self, auto_slots, monkeypatch):
        """AgentRunner: 중복 제거 후 chunks 1건 (동일 id)."""
        result = self._run_agentrunner(auto_slots, monkeypatch)
        ids = [c["id"] for c in result.chunks]
        assert ids == ["chunk-추돌"], f"chunks ids={ids}"

    def test_langgraph_chunks_dedupe_one_item(self, auto_slots, monkeypatch):
        """LangGraph: 중복 제거 후 chunks 1건 (동일 id)."""
        result = self._run_langgraph(auto_slots, monkeypatch)
        ids = [c["id"] for c in result.chunks]
        assert ids == ["chunk-추돌"], f"chunks ids={ids}"
