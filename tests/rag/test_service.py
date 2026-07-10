"""tests.rag.test_service — retrieval 단일 진입점 (뉴로심볼릭 고정 경로) 테스트.

Sprint 32 T2 — 구 rag_mode(vector/graph/hybrid) 라우팅 테스트를 대체.
"""

from __future__ import annotations

from typing import Any

import app.domains.rag.service as svc
import pytest
from app.domains.sessions.schemas import SlotState


@pytest.fixture(autouse=True)
def _fresh_singletons():
    svc.clear_caches()
    yield
    svc.clear_caches()


def _slots(**kw) -> SlotState:
    base = {"area": "accident_disease", "insurer_id": "samsung", "diagnosis": "골절"}
    base.update(kw)
    return SlotState(**base)


class FakeRetriever:
    def __init__(self, results=None, boom: Exception | None = None):
        self.results = results if results is not None else []
        self.boom = boom
        self.calls: list[dict[str, Any]] = []

    def retrieve(self, slots, top_k=8):
        self.calls.append({"slots": slots, "top_k": top_k})
        if self.boom:
            raise self.boom
        return self.results[:top_k]

    def retrieve_freeform(self, text, top_k=8, insurer_id=None):
        self.calls.append({"text": text, "top_k": top_k, "insurer_id": insurer_id})
        if self.boom:
            raise self.boom
        return self.results[:top_k]


def _wire(monkeypatch, fake: FakeRetriever) -> None:
    monkeypatch.setattr(svc, "_retriever_singleton", lambda: fake)


class TestRetrieve:
    def test_returns_retriever_results_as_dicts(self, monkeypatch):
        fake = FakeRetriever([{"id": "c1", "text": "t", "score": 0.9, "metadata": {}, "source": "neural"}])
        _wire(monkeypatch, fake)
        out = svc.retrieve(_slots(), top_k=8)
        assert out and out[0]["id"] == "c1"
        assert isinstance(out[0], dict)

    def test_retriever_exception_returns_empty(self, monkeypatch):
        _wire(monkeypatch, FakeRetriever(boom=RuntimeError("down")))
        assert svc.retrieve(_slots()) == []

    def test_rerank_fetches_double_candidates(self, monkeypatch):
        from app.infrastructure.core.config import get_settings

        monkeypatch.setattr(get_settings(), "rag_rerank", True)
        fake = FakeRetriever([{"id": f"c{i}", "text": "t", "score": 0.5, "metadata": {}} for i in range(16)])
        _wire(monkeypatch, fake)
        monkeypatch.setattr(svc, "_rerank_with_solar", lambda slots, out, k: out[:k])
        out = svc.retrieve(_slots(), top_k=8)
        assert fake.calls[0]["top_k"] == 16
        assert len(out) == 8

    def test_no_rerank_fetches_top_k(self, monkeypatch):
        from app.infrastructure.core.config import get_settings

        monkeypatch.setattr(get_settings(), "rag_rerank", False)
        fake = FakeRetriever([])
        _wire(monkeypatch, fake)
        svc.retrieve(_slots(), top_k=8)
        assert fake.calls[0]["top_k"] == 8


class TestRetrieveFreeform:
    def test_freeform_passes_text(self, monkeypatch):
        fake = FakeRetriever([{"id": "c1", "text": "t", "score": 0.5, "metadata": {}}])
        _wire(monkeypatch, fake)
        out = svc.retrieve_freeform("도수치료 보장", top_k=6)
        assert fake.calls[0] == {"text": "도수치료 보장", "top_k": 6, "insurer_id": None}
        assert out[0]["id"] == "c1"

    def test_freeform_exception_returns_empty(self, monkeypatch):
        _wire(monkeypatch, FakeRetriever(boom=RuntimeError("down")))
        assert svc.retrieve_freeform("질문") == []


class TestCircuitBreaker:
    def test_singleton_cached(self):
        assert svc._rag_circuit_breaker() is svc._rag_circuit_breaker()

    def test_opens_after_consecutive_failures_then_returns_empty(self, monkeypatch):
        fake = FakeRetriever(boom=RuntimeError("db down"))
        _wire(monkeypatch, fake)
        breaker = svc._rag_circuit_breaker()
        for _ in range(breaker.fail_max + 2):
            assert svc.retrieve(_slots()) == []
        # open 상태에서도 안전하게 빈 리스트 (예외 전파 없음)
        assert svc.retrieve(_slots()) == []


class TestClearCaches:
    def test_clear_caches_does_not_raise(self):
        svc.clear_caches()

    def test_clear_caches_resets_retriever_singleton(self):
        a = svc._retriever_singleton()
        svc.clear_caches()
        assert svc._retriever_singleton() is not a


class TestRunAgent:
    def test_run_agent_delegates_to_langgraph(self, monkeypatch):
        captured = {}

        def fake_run(slots, msg, **kw):
            captured["args"] = (slots, msg)
            return "AGENT_RESULT"

        monkeypatch.setattr(
            "app.domains.rag.langgraph_agent.run_agent_langgraph", fake_run
        )
        result = svc.run_agent(_slots(), "질문")
        assert result == "AGENT_RESULT"
        assert captured["args"][1] == "질문"

    def test_run_agent_propagates_exception(self, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("agent down")

        monkeypatch.setattr("app.domains.rag.langgraph_agent.run_agent_langgraph", boom)
        with pytest.raises(RuntimeError):
            svc.run_agent(_slots(), "질문")
