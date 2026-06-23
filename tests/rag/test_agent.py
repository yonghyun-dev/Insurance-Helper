"""tests.rag.test_agent

app/rag/agent.py (AgentRunner + AgentResult) 단위 테스트.

테스트 대상:
    - AgentResult dataclass 기본값 + 필드 접근
    - AgentRunner.run — 정상 ReAct loop (finish tool 호출)
    - AgentRunner.run — no_tool_call 종료 (LLM 이 tool 없이 답변)
    - AgentRunner.run — max_iter 강제 종료
    - AgentRunner.run — search_terms 결과 chunks 누적 + dedupe
    - AgentRunner.run — 중복 (tool_name, args) 호출 차단 → {"skipped": "duplicate"}
    - AgentRunner._safe_invoke — ToolNotImplementedError graceful 변환
    - AgentRunner._safe_invoke — ToolNotFoundError graceful 변환
    - AgentRunner._safe_invoke — 일반 Exception graceful 변환
    - AgentRunner._dedupe_chunks — score 높은 것 유지
    - AgentRunner._slot_summary — 슬롯 요약 문자열
    - slots.area None → "auto" 기본값 적용

mock 정책:
    - _get_openai_client monkeypatch → FakeOpenAI (tool_calls 응답 시뮬)
    - dispatcher.invoke monkeypatch (또는 _safe_invoke 직접 테스트)
    - get_settings monkeypatch (llm_model, openai_api_key)
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.domains.rag.agent import AgentResult, AgentRunner
from app.domains.sessions.schemas import SlotState
from app.shared.tools.dispatcher import ToolNotFoundError, ToolNotImplementedError  # noqa: F401

# ---------------------------------------------------------------------------
# 헬퍼 — OpenAI 응답 시뮬
# ---------------------------------------------------------------------------


def _make_tool_call(name: str, args: dict, call_id: str = "call_001") -> MagicMock:
    """OpenAI ToolCall 오브젝트 흉내."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args, ensure_ascii=False)
    return tc


def _make_chat_message(tool_calls: list | None = None, content: str = "") -> MagicMock:
    """OpenAI ChatCompletionMessage 흉내."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    return msg


def _make_response(tool_calls: list | None = None, content: str = "") -> MagicMock:
    """OpenAI ChatCompletion 흉내."""
    resp = MagicMock()
    resp.choices[0].message = _make_chat_message(tool_calls, content)
    return resp


def _make_fake_client(responses: list[MagicMock]) -> MagicMock:
    """순서대로 응답을 반환하는 가짜 OpenAI client."""
    client = MagicMock()
    client.chat.completions.create.side_effect = responses
    return client


# ---------------------------------------------------------------------------
# 픽스처 — AgentRunner 격리
# ---------------------------------------------------------------------------


@pytest.fixture()
def auto_slots() -> SlotState:
    from datetime import date

    return SlotState(
        area="auto",
        insurer="한화손해보험",
        product="개인용자동차보험",
        incident_date=date(2026, 3, 15),
        incident_type="추돌",
    )


@pytest.fixture()
def empty_slots() -> SlotState:
    return SlotState()


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """get_settings monkeypatch — llm_model + openai_api_key."""
    from app.infrastructure.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_model", "gpt-4o-mini")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")


@pytest.fixture(autouse=True)
def clear_openai_client_cache():
    """_get_openai_client lru_cache 초기화 (테스트 격리).

    monkeypatch 로 교체 후 teardown 시 cache_clear 가 없을 수 있으므로 방어적으로 처리.
    """
    import app.domains.rag.agent as agent_mod

    if hasattr(agent_mod._get_openai_client, "cache_clear"):
        agent_mod._get_openai_client.cache_clear()
    yield
    if hasattr(agent_mod._get_openai_client, "cache_clear"):
        agent_mod._get_openai_client.cache_clear()


# ---------------------------------------------------------------------------
# AgentResult dataclass
# ---------------------------------------------------------------------------


class TestAgentResult:
    """AgentResult dataclass 기본값 + 필드 접근."""

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
        """mutable 기본값 공유 없음 확인 (dataclass field default_factory)."""
        r1 = AgentResult()
        r2 = AgentResult()
        r1.chunks.append({"id": "x"})
        assert r2.chunks == []


# ---------------------------------------------------------------------------
# AgentRunner._dedupe_chunks
# ---------------------------------------------------------------------------


class TestDedupeChunks:
    """_dedupe_chunks — score 높은 것 유지, id 기반 중복 제거."""

    def test_no_duplicates_returns_all(self):
        chunks = [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.8}]
        result = AgentRunner._dedupe_chunks(chunks)
        assert len(result) == 2

    def test_duplicate_id_keeps_higher_score(self):
        chunks = [
            {"id": "a", "score": 0.7},
            {"id": "a", "score": 0.95},
        ]
        result = AgentRunner._dedupe_chunks(chunks)
        assert len(result) == 1
        assert result[0]["score"] == 0.95

    def test_duplicate_id_keeps_first_if_score_equal(self):
        # score 같으면 첫 번째 우선 (>=False 조건)
        chunks = [
            {"id": "a", "score": 0.8},
            {"id": "a", "score": 0.8},
        ]
        result = AgentRunner._dedupe_chunks(chunks)
        assert len(result) == 1

    def test_empty_chunks_returns_empty(self):
        assert AgentRunner._dedupe_chunks([]) == []

    def test_chunks_without_score_field(self):
        # score 필드 없으면 0 으로 처리
        chunks = [
            {"id": "a"},
            {"id": "a", "score": 0.5},
        ]
        result = AgentRunner._dedupe_chunks(chunks)
        assert len(result) == 1
        assert result[0].get("score") == 0.5

    def test_multiple_ids_all_preserved(self):
        chunks = [{"id": f"c{i}", "score": 0.9} for i in range(5)]
        result = AgentRunner._dedupe_chunks(chunks)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# AgentRunner._slot_summary
# ---------------------------------------------------------------------------


class TestSlotSummary:
    """_slot_summary — 슬롯 요약 문자열 생성."""

    def test_full_slots_all_fields_appear(self, auto_slots):
        summary = AgentRunner._slot_summary(auto_slots)
        assert "area=auto" in summary
        assert "insurer=한화손해보험" in summary
        assert "product=개인용자동차보험" in summary
        assert "incident_type=추돌" in summary

    def test_empty_slots_returns_empty_string(self, empty_slots):
        summary = AgentRunner._slot_summary(empty_slots)
        assert summary == "(empty)"

    def test_partial_slots_only_filled_appear(self):
        slots = SlotState(area="fire", insurer="삼성화재")
        summary = AgentRunner._slot_summary(slots)
        assert "area=fire" in summary
        assert "insurer=삼성화재" in summary
        # 비어있는 필드는 미포함
        assert "product=" not in summary


# ---------------------------------------------------------------------------
# AgentRunner._safe_invoke — 예외 graceful 변환
# ---------------------------------------------------------------------------


class TestSafeInvoke:
    """_safe_invoke — dispatcher.invoke 예외를 error dict 로 변환."""

    def test_tool_not_implemented_error_returns_error_dict(self, monkeypatch):
        import app.domains.rag.agent as agent_mod

        monkeypatch.setattr(
            agent_mod,
            "invoke",
            lambda name, args: (_ for _ in ()).throw(
                ToolNotImplementedError("search_terms 미구현")
            ),
        )
        result = AgentRunner._safe_invoke("search_terms", {})
        assert result["error"] == "not_implemented"
        assert result["tool"] == "search_terms"
        assert "미구현" in result["message"]

    def test_tool_not_found_error_returns_error_dict(self, monkeypatch):
        import app.domains.rag.agent as agent_mod

        monkeypatch.setattr(
            agent_mod,
            "invoke",
            lambda name, args: (_ for _ in ()).throw(
                ToolNotFoundError("phantom_tool")
            ),
        )
        result = AgentRunner._safe_invoke("phantom_tool", {})
        assert result["error"] == "not_found"
        assert result["tool"] == "phantom_tool"

    def test_generic_exception_returns_runtime_error_dict(self, monkeypatch):
        import app.domains.rag.agent as agent_mod

        monkeypatch.setattr(
            agent_mod,
            "invoke",
            lambda name, args: (_ for _ in ()).throw(RuntimeError("DB 연결 오류")),
        )
        result = AgentRunner._safe_invoke("calc_claim_amount", {"loss_amount": 100000})
        assert result["error"] == "runtime"
        assert "DB 연결 오류" in result["message"]

    def test_successful_invoke_returns_result(self, monkeypatch):
        import app.domains.rag.agent as agent_mod

        expected = {"paid_amount": 90000}
        monkeypatch.setattr(
            agent_mod,
            "invoke",
            lambda name, args: expected,
        )
        result = AgentRunner._safe_invoke("calc_claim_amount", {"loss_amount": 100000})
        assert result == expected


# ---------------------------------------------------------------------------
# AgentRunner.run — 정상 finish tool 종료
# ---------------------------------------------------------------------------


class TestAgentRunFinish:
    """run() — LLM 이 finish tool 호출해 정상 종료."""

    def test_finish_tool_sets_finish_reason(self, auto_slots, monkeypatch):
        import app.domains.rag.agent as agent_mod

        # 1st call: finish tool 호출
        finish_call = _make_tool_call("finish", {"reason": "정보 충분"})
        responses = [_make_response(tool_calls=[finish_call])]

        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)
        # finish invoke → {"finished": True}
        monkeypatch.setattr(agent_mod, "invoke", lambda name, args: {"finished": True})

        runner = AgentRunner()
        result = runner.run(auto_slots, "청구하고 싶어요")

        assert result.finish_reason == "finish"
        assert result.iterations == 1

    def test_finish_tool_has_tool_result_recorded(self, auto_slots, monkeypatch):
        import app.domains.rag.agent as agent_mod

        finish_call = _make_tool_call("finish", {"reason": "완료"})
        fake_client = _make_fake_client([_make_response(tool_calls=[finish_call])])
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)
        monkeypatch.setattr(agent_mod, "invoke", lambda name, args: {"finished": True})

        runner = AgentRunner()
        result = runner.run(auto_slots, "청구하고 싶어요")

        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool"] == "finish"

    def test_finish_after_search_terms_accumulates_chunks(self, auto_slots, monkeypatch):
        """search_terms → finish 2-turn 시뮬."""
        import app.domains.rag.agent as agent_mod

        search_call = _make_tool_call("search_terms", {"query": "추돌 사고"}, "call_001")
        finish_call = _make_tool_call("finish", {"reason": "완료"}, "call_002")

        responses = [
            _make_response(tool_calls=[search_call]),
            _make_response(tool_calls=[finish_call]),
        ]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        def fake_invoke(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name == "search_terms":
                return {"chunks": [{"id": "c1", "score": 0.9, "text": "약관 조항"}], "count": 1}
            return {"finished": True}

        monkeypatch.setattr(agent_mod, "invoke", fake_invoke)

        runner = AgentRunner()
        result = runner.run(auto_slots, "청구하고 싶어요")

        assert result.finish_reason == "finish"
        assert result.iterations == 2
        assert len(result.chunks) == 1
        assert result.chunks[0]["id"] == "c1"


# ---------------------------------------------------------------------------
# AgentRunner.run — no_tool_call 종료
# ---------------------------------------------------------------------------


class TestAgentRunNoToolCall:
    """run() — LLM 이 tool 안 부르고 텍스트로만 응답 시 no_tool_call 종료."""

    def test_no_tool_call_sets_finish_reason(self, auto_slots, monkeypatch):
        import app.domains.rag.agent as agent_mod

        # tool_calls 없는 응답
        responses = [_make_response(tool_calls=None, content="청구 가능합니다.")]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        runner = AgentRunner()
        result = runner.run(auto_slots, "청구하고 싶어요")

        assert result.finish_reason == "no_tool_call"
        assert result.iterations == 1

    def test_no_tool_call_empty_list_also_terminates(self, auto_slots, monkeypatch):
        """tool_calls = [] (빈 리스트) 도 no_tool_call 처리."""
        import app.domains.rag.agent as agent_mod

        responses = [_make_response(tool_calls=[], content="답변")]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        runner = AgentRunner()
        result = runner.run(auto_slots, "안녕하세요")

        assert result.finish_reason == "no_tool_call"

    def test_no_tool_call_chunks_empty(self, auto_slots, monkeypatch):
        """no_tool_call 종료 시 chunks 는 비어있다."""
        import app.domains.rag.agent as agent_mod

        responses = [_make_response(tool_calls=None)]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        runner = AgentRunner()
        result = runner.run(auto_slots, "아무말")

        assert result.chunks == []
        assert result.tool_results == []


# ---------------------------------------------------------------------------
# AgentRunner.run — max_iter 강제 종료
# ---------------------------------------------------------------------------


class TestAgentRunMaxIter:
    """run() — max_iter 도달 시 강제 종료."""

    def test_max_iter_sets_finish_reason(self, auto_slots, monkeypatch):
        import app.domains.rag.agent as agent_mod

        # 항상 search_terms tool_call 반환 (finish 없음)
        search_call = _make_tool_call("search_terms", {"query": "약관"}, "c1")
        responses = [_make_response(tool_calls=[search_call])] * 3  # max_iter=3

        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)
        monkeypatch.setattr(
            agent_mod,
            "invoke",
            lambda name, args: {"chunks": [], "count": 0},
        )

        runner = AgentRunner(max_iter=3)
        result = runner.run(auto_slots, "청구 가능한가요")

        assert result.finish_reason == "max_iter"
        assert result.iterations == 3

    def test_max_iter_one_terminates_after_first(self, auto_slots, monkeypatch):
        """max_iter=1 이면 첫 turn 에서 도달해도 max_iter 로 종료."""
        import app.domains.rag.agent as agent_mod

        search_call = _make_tool_call("search_terms", {"query": "약관"}, "c1")
        fake_client = _make_fake_client([_make_response(tool_calls=[search_call])])
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)
        monkeypatch.setattr(
            agent_mod, "invoke", lambda name, args: {"chunks": [], "count": 0}
        )

        runner = AgentRunner(max_iter=1)
        result = runner.run(auto_slots, "테스트")

        assert result.finish_reason == "max_iter"
        assert result.iterations == 1


# ---------------------------------------------------------------------------
# AgentRunner.run — 중복 호출 차단
# ---------------------------------------------------------------------------


class TestAgentRunDuplicateBlock:
    """동일 (tool_name, args) 2회 호출 시 {"skipped": "duplicate"} 반환."""

    def test_duplicate_tool_call_same_turn_skipped(self, auto_slots, monkeypatch):
        """같은 turn 에 동일 tool 2번 호출 → 두 번째는 skip."""
        import app.domains.rag.agent as agent_mod

        # 같은 args 로 2번 search_terms
        call1 = _make_tool_call("search_terms", {"query": "추돌"}, "c1")
        call2 = _make_tool_call("search_terms", {"query": "추돌"}, "c2")
        finish_call = _make_tool_call("finish", {}, "c3")

        responses = [
            _make_response(tool_calls=[call1, call2]),
            _make_response(tool_calls=[finish_call]),
        ]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        invoke_count = {"n": 0}

        def fake_invoke(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name == "search_terms":
                invoke_count["n"] += 1
                return {"chunks": [{"id": "c1", "score": 0.9}], "count": 1}
            return {"finished": True}

        monkeypatch.setattr(agent_mod, "invoke", fake_invoke)

        runner = AgentRunner()
        result = runner.run(auto_slots, "질문")

        # search_terms 실제 invoke 는 1회 (두 번째는 skip)
        assert invoke_count["n"] == 1

        # tool_results 에 duplicate skip 기록
        search_results = [
            tr for tr in result.tool_results if tr["tool"] == "search_terms"
        ]
        assert len(search_results) == 2
        skipped = [tr for tr in search_results if tr["result"] == {"skipped": "duplicate"}]
        assert len(skipped) == 1

    def test_duplicate_across_turns_skipped(self, auto_slots, monkeypatch):
        """다른 turn 에 동일 tool + 동일 args → 두 번째 turn 에서 skip."""
        import app.domains.rag.agent as agent_mod

        search_call_1 = _make_tool_call("search_terms", {"query": "동일"}, "t1")
        search_call_2 = _make_tool_call("search_terms", {"query": "동일"}, "t2")
        finish_call = _make_tool_call("finish", {}, "f1")

        responses = [
            _make_response(tool_calls=[search_call_1]),
            _make_response(tool_calls=[search_call_2]),
            _make_response(tool_calls=[finish_call]),
        ]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        invoke_count = {"n": 0}

        def fake_invoke(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name == "search_terms":
                invoke_count["n"] += 1
                return {"chunks": [], "count": 0}
            return {"finished": True}

        monkeypatch.setattr(agent_mod, "invoke", fake_invoke)

        runner = AgentRunner()
        runner.run(auto_slots, "질문")

        # search_terms 실제 invoke 는 1회
        assert invoke_count["n"] == 1

    def test_different_args_not_blocked(self, auto_slots, monkeypatch):
        """다른 args 면 중복 차단 안 함."""
        import app.domains.rag.agent as agent_mod

        call1 = _make_tool_call("search_terms", {"query": "추돌"}, "c1")
        call2 = _make_tool_call("search_terms", {"query": "화재"}, "c2")
        finish_call = _make_tool_call("finish", {}, "c3")

        responses = [
            _make_response(tool_calls=[call1, call2]),
            _make_response(tool_calls=[finish_call]),
        ]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        invoke_count = {"n": 0}

        def fake_invoke(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name == "search_terms":
                invoke_count["n"] += 1
                return {"chunks": [], "count": 0}
            return {"finished": True}

        monkeypatch.setattr(agent_mod, "invoke", fake_invoke)

        runner = AgentRunner()
        runner.run(auto_slots, "질문")

        # 두 번 모두 invoke 됨
        assert invoke_count["n"] == 2


# ---------------------------------------------------------------------------
# AgentRunner.run — search_terms chunks 누적 + dedupe
# ---------------------------------------------------------------------------


class TestAgentRunChunksAccumulation:
    """search_terms 여러 번 호출 시 chunks 누적 + dedupe."""

    def test_search_terms_chunks_accumulated_across_turns(self, auto_slots, monkeypatch):
        """두 번의 search_terms 호출(다른 query) → chunks 합산."""
        import app.domains.rag.agent as agent_mod

        call1 = _make_tool_call("search_terms", {"query": "추돌"}, "s1")
        call2 = _make_tool_call("search_terms", {"query": "보상"}, "s2")
        finish_call = _make_tool_call("finish", {}, "f1")

        responses = [
            _make_response(tool_calls=[call1]),
            _make_response(tool_calls=[call2]),
            _make_response(tool_calls=[finish_call]),
        ]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        chunk_counter = {"n": 0}

        def fake_invoke(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name == "search_terms":
                chunk_counter["n"] += 1
                return {
                    "chunks": [{"id": f"chunk_{chunk_counter['n']}", "score": 0.9}],
                    "count": 1,
                }
            return {"finished": True}

        monkeypatch.setattr(agent_mod, "invoke", fake_invoke)

        runner = AgentRunner()
        result = runner.run(auto_slots, "질문")

        # 2번 호출 → 2개 chunks
        assert len(result.chunks) == 2

    def test_search_terms_duplicate_chunks_deduped(self, auto_slots, monkeypatch):
        """두 번의 search_terms 가 같은 chunk id 반환 → dedupe."""
        import app.domains.rag.agent as agent_mod

        call1 = _make_tool_call("search_terms", {"query": "A"}, "s1")
        call2 = _make_tool_call("search_terms", {"query": "B"}, "s2")
        finish_call = _make_tool_call("finish", {}, "f1")

        responses = [
            _make_response(tool_calls=[call1]),
            _make_response(tool_calls=[call2]),
            _make_response(tool_calls=[finish_call]),
        ]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        call_count = {"n": 0}

        def fake_invoke(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name == "search_terms":
                call_count["n"] += 1
                # 두 번 모두 같은 chunk id 반환 (score 는 다름)
                score = 0.7 if call_count["n"] == 1 else 0.95
                return {
                    "chunks": [{"id": "common_chunk", "score": score}],
                    "count": 1,
                }
            return {"finished": True}

        monkeypatch.setattr(agent_mod, "invoke", fake_invoke)

        runner = AgentRunner()
        result = runner.run(auto_slots, "질문")

        # dedupe → 1개, score 높은 것 유지
        assert len(result.chunks) == 1
        assert result.chunks[0]["score"] == 0.95

    def test_non_search_terms_tool_does_not_accumulate_chunks(self, auto_slots, monkeypatch):
        """search_terms 외 tool 결과는 chunks 에 미포함."""
        import app.domains.rag.agent as agent_mod

        calc_call = _make_tool_call(
            "calc_claim_amount",
            {"loss_amount": 1000000, "fault_ratio": 20},
            "c1",
        )
        finish_call = _make_tool_call("finish", {}, "f1")

        responses = [
            _make_response(tool_calls=[calc_call]),
            _make_response(tool_calls=[finish_call]),
        ]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        def fake_invoke(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name == "calc_claim_amount":
                return {"paid_amount": 800000, "formula": "..."}
            return {"finished": True}

        monkeypatch.setattr(agent_mod, "invoke", fake_invoke)

        runner = AgentRunner()
        result = runner.run(auto_slots, "보험금 계산해줘")

        assert result.chunks == []
        # tool_results 에는 calc + finish 기록
        assert any(tr["tool"] == "calc_claim_amount" for tr in result.tool_results)


# ---------------------------------------------------------------------------
# AgentRunner.run — dispatcher 예외 graceful 처리
# ---------------------------------------------------------------------------


class TestAgentRunDispatcherExceptions:
    """dispatcher.invoke 예외 시 error dict 변환 후 loop 계속 진행."""

    def test_not_implemented_error_continues_loop(self, auto_slots, monkeypatch):
        """ToolNotImplementedError → error dict + 다음 turn 진행."""
        import app.domains.rag.agent as agent_mod

        # 1st: not_implemented tool, 2nd: finish
        stub_call = _make_tool_call("lookup_law_clause", {"law_name": "보험업법", "keyword_or_article": "제4조"}, "c1")
        finish_call = _make_tool_call("finish", {}, "c2")

        responses = [
            _make_response(tool_calls=[stub_call]),
            _make_response(tool_calls=[finish_call]),
        ]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        def fake_invoke(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name == "lookup_law_clause":
                raise ToolNotImplementedError("lookup_law_clause 미구현")
            return {"finished": True}

        monkeypatch.setattr(agent_mod, "invoke", fake_invoke)

        runner = AgentRunner()
        result = runner.run(auto_slots, "법률 조항 알려줘")

        # finish 까지 도달 (loop 계속)
        assert result.finish_reason == "finish"

        # error dict 가 tool_results 에 기록됨
        law_result = next(
            tr for tr in result.tool_results if tr["tool"] == "lookup_law_clause"
        )
        assert law_result["result"]["error"] == "not_implemented"

    def test_not_found_error_continues_loop(self, auto_slots, monkeypatch):
        """ToolNotFoundError → error dict + 다음 turn 진행."""
        import app.domains.rag.agent as agent_mod

        phantom_call = _make_tool_call("phantom_tool", {}, "c1")
        finish_call = _make_tool_call("finish", {}, "c2")

        responses = [
            _make_response(tool_calls=[phantom_call]),
            _make_response(tool_calls=[finish_call]),
        ]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        def fake_invoke(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name == "phantom_tool":
                raise ToolNotFoundError("phantom_tool 없음")
            return {"finished": True}

        monkeypatch.setattr(agent_mod, "invoke", fake_invoke)

        runner = AgentRunner()
        result = runner.run(auto_slots, "질문")

        assert result.finish_reason == "finish"
        phantom_result = next(
            tr for tr in result.tool_results if tr["tool"] == "phantom_tool"
        )
        assert phantom_result["result"]["error"] == "not_found"

    def test_runtime_error_continues_loop(self, auto_slots, monkeypatch):
        """일반 Exception → runtime error dict + 다음 turn 진행."""
        import app.domains.rag.agent as agent_mod

        bad_call = _make_tool_call("calc_claim_amount", {"loss_amount": -1}, "c1")
        finish_call = _make_tool_call("finish", {}, "c2")

        responses = [
            _make_response(tool_calls=[bad_call]),
            _make_response(tool_calls=[finish_call]),
        ]
        fake_client = _make_fake_client(responses)
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        def fake_invoke(name: str, args: dict[str, Any]) -> dict[str, Any]:
            if name == "calc_claim_amount":
                raise ValueError("음수 손해액 불가")
            return {"finished": True}

        monkeypatch.setattr(agent_mod, "invoke", fake_invoke)

        runner = AgentRunner()
        result = runner.run(auto_slots, "질문")

        assert result.finish_reason == "finish"
        calc_result = next(
            tr for tr in result.tool_results if tr["tool"] == "calc_claim_amount"
        )
        assert calc_result["result"]["error"] == "runtime"


# ---------------------------------------------------------------------------
# AgentRunner.run — slots.area None → "auto" 기본
# ---------------------------------------------------------------------------


class TestAgentRunAreaDefault:
    """slots.area None 시 system prompt 에 auto 기본값 적용."""

    def test_area_none_uses_auto_policy(self, empty_slots, monkeypatch):
        """area=None 이면 auto 정책 적용 (시스템 프롬프트 생성 실패 없이 실행)."""
        import app.domains.rag.agent as agent_mod

        finish_call = _make_tool_call("finish", {}, "c1")
        fake_client = _make_fake_client([_make_response(tool_calls=[finish_call])])
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)
        monkeypatch.setattr(agent_mod, "invoke", lambda name, args: {"finished": True})

        runner = AgentRunner()
        # area None → 예외 없이 실행 + auto 기본값 적용
        result = runner.run(empty_slots, "질문")

        assert result.finish_reason == "finish"

    def test_system_prompt_contains_area_policy_keywords(self, auto_slots, monkeypatch):
        """system prompt 생성 시 area 정책(mandatory/recommended) 포함 확인."""
        import app.domains.rag.agent as agent_mod

        captured = {}

        def fake_create(**kwargs):
            captured["messages"] = kwargs.get("messages", [])
            msg = _make_chat_message(tool_calls=None, content="완료")
            resp = MagicMock()
            resp.choices[0].message = msg
            return resp

        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = fake_create
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)

        runner = AgentRunner()
        runner.run(auto_slots, "자동차 사고 청구")

        # system 메시지에 area 정책 포함
        system_msg = captured["messages"][0]
        assert system_msg["role"] == "system"
        # auto 영역의 의무 tool 이름 포함 여부
        assert "search_terms" in system_msg["content"]

    def test_invalid_json_args_handled_gracefully(self, auto_slots, monkeypatch):
        """LLM 이 잘못된 JSON arguments 보낼 때 args={} 로 처리."""
        import app.domains.rag.agent as agent_mod

        # 잘못된 JSON arguments
        bad_call = MagicMock()
        bad_call.id = "c1"
        bad_call.function.name = "finish"
        bad_call.function.arguments = "{invalid json}"

        finish_response = _make_response(tool_calls=[bad_call])
        fake_client = _make_fake_client([finish_response])
        monkeypatch.setattr(agent_mod, "_get_openai_client", lambda: fake_client)
        monkeypatch.setattr(agent_mod, "invoke", lambda name, args: {"finished": True})

        runner = AgentRunner()
        # JSON 파싱 실패 → {} 로 폴백, 예외 없이 실행
        result = runner.run(auto_slots, "테스트")
        assert result.finish_reason == "finish"
