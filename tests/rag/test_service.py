"""tests.rag.test_service

app/rag/service.py 단위 테스트.

테스트 대상:
    - retrieve() mode 라우팅 (vector / graph / hybrid)
    - Neo4j health 실패 시 mode="graph"/"hybrid" → vector 폴백
    - retriever 예외 시 vector 폴백
    - react opt-in 동작
    - clear_caches() 동작

mock 정책:
    - _vector_singleton / _graph_singleton / _hybrid_singleton 교체 (monkeypatch)
    - clear_caches() 로 테스트 격리
"""

from __future__ import annotations

import pytest

from tests.rag.conftest import make_auto_slot, make_retrieval_result

# ---------------------------------------------------------------------------
# 공통 stub
# ---------------------------------------------------------------------------


def _fake_results(n: int = 2, source: str = "vector") -> list[dict]:
    return [make_retrieval_result(f"c{i}", source=source) for i in range(n)]


class FakeRetriever:
    """임의 결과 반환 Retriever stub."""

    def __init__(self, results=None, health_val=True, raise_exc=False):
        self._results = results or _fake_results()
        self._health_val = health_val
        self._raise = raise_exc

    def retrieve(self, slots, top_k=8):
        if self._raise:
            raise RuntimeError("retriever 오류")
        return self._results

    def health(self):
        return self._health_val


# ---------------------------------------------------------------------------
# 픽스처 — rag service 캐시 격리
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolate_rag_caches():
    """각 테스트 전후로 rag.service lru_cache 초기화."""
    import app.domains.rag.service as svc

    svc.clear_caches()
    yield
    svc.clear_caches()


# ===========================================================================
# retrieve() — mode 라우팅
# ===========================================================================


class TestRetrieveModeRouting:
    """mode 파라미터에 따라 올바른 retriever 가 선택된다."""

    def test_vector_mode_uses_vector_retriever(self, monkeypatch):
        import app.domains.rag.service as svc

        vector = FakeRetriever(_fake_results(2, "vector"))
        monkeypatch.setattr(svc, "_vector_singleton", lambda: vector)
        monkeypatch.setattr(svc, "_graph_singleton", lambda: FakeRetriever(health_val=True))
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: FakeRetriever())

        results = svc.retrieve(make_auto_slot(), mode="vector", react=False)

        assert all(r["source"] == "vector" for r in results)

    def test_graph_mode_uses_graph_retriever_when_healthy(self, monkeypatch):
        import app.domains.rag.service as svc

        graph_results = _fake_results(2, "graph")
        graph = FakeRetriever(graph_results, health_val=True)
        monkeypatch.setattr(svc, "_graph_singleton", lambda: graph)
        monkeypatch.setattr(svc, "_vector_singleton", lambda: FakeRetriever(_fake_results(2, "vector")))
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: FakeRetriever())

        results = svc.retrieve(make_auto_slot(), mode="graph", react=False)

        assert all(r["source"] == "graph" for r in results)

    def test_hybrid_mode_uses_hybrid_retriever_when_healthy(self, monkeypatch):
        import app.domains.rag.service as svc

        hybrid_results = _fake_results(3, "vector")
        hybrid = FakeRetriever(hybrid_results, health_val=True)
        graph = FakeRetriever(health_val=True)
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: hybrid)
        monkeypatch.setattr(svc, "_graph_singleton", lambda: graph)
        monkeypatch.setattr(svc, "_vector_singleton", lambda: FakeRetriever())

        results = svc.retrieve(make_auto_slot(), mode="hybrid", react=False)

        assert len(results) == 3


# ===========================================================================
# graceful fallback — Neo4j health 실패
# ===========================================================================


class TestNeo4jFallback:
    """graph/hybrid 모드에서 Neo4j health 실패 시 vector 폴백."""

    def test_graph_mode_falls_back_to_vector_when_neo4j_unhealthy(self, monkeypatch):
        import app.domains.rag.service as svc

        vector_results = _fake_results(2, "vector")
        vector = FakeRetriever(vector_results, health_val=True)
        graph = FakeRetriever(health_val=False)  # Neo4j 다운

        monkeypatch.setattr(svc, "_graph_singleton", lambda: graph)
        monkeypatch.setattr(svc, "_vector_singleton", lambda: vector)
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: FakeRetriever())

        results = svc.retrieve(make_auto_slot(), mode="graph", react=False)

        # vector 폴백 — source 검증
        assert all(r["source"] == "vector" for r in results)

    def test_hybrid_mode_falls_back_to_vector_when_neo4j_unhealthy(self, monkeypatch):
        import app.domains.rag.service as svc

        vector_results = _fake_results(2, "vector")
        vector = FakeRetriever(vector_results, health_val=True)
        graph = FakeRetriever(health_val=False)

        monkeypatch.setattr(svc, "_graph_singleton", lambda: graph)
        monkeypatch.setattr(svc, "_vector_singleton", lambda: vector)
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: FakeRetriever())

        results = svc.retrieve(make_auto_slot(), mode="hybrid", react=False)

        assert all(r["source"] == "vector" for r in results)


# ===========================================================================
# graceful fallback — retriever 예외
# ===========================================================================


class TestRetrieverExceptionFallback:
    """retriever.retrieve 예외 → vector 폴백 또는 빈 list."""

    def test_graph_retriever_exception_falls_back_to_vector(self, monkeypatch):
        import app.domains.rag.service as svc

        vector_results = _fake_results(2, "vector")
        vector = FakeRetriever(vector_results, health_val=True)
        graph_healthy_but_raises = FakeRetriever(health_val=True, raise_exc=True)

        monkeypatch.setattr(svc, "_graph_singleton", lambda: graph_healthy_but_raises)
        monkeypatch.setattr(svc, "_vector_singleton", lambda: vector)
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: FakeRetriever())

        results = svc.retrieve(make_auto_slot(), mode="graph", react=False)

        # vector 폴백 성공
        assert len(results) > 0

    def test_vector_retriever_exception_returns_empty(self, monkeypatch):
        """vector 까지 실패하면 빈 list."""
        import app.domains.rag.service as svc

        vector_raises = FakeRetriever(raise_exc=True, health_val=True)
        graph = FakeRetriever(health_val=True)

        monkeypatch.setattr(svc, "_vector_singleton", lambda: vector_raises)
        monkeypatch.setattr(svc, "_graph_singleton", lambda: graph)
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: FakeRetriever())

        # vector 모드에서 예외 → 빈 list
        results = svc.retrieve(make_auto_slot(), mode="vector", react=False)

        assert results == []


# ===========================================================================
# react opt-in
# ===========================================================================


class TestReactOptIn:
    """react=True 시 ReActRunner 를 통해 실행된다."""

    def test_react_true_invokes_react_runner(self, monkeypatch):
        """react=True 면 ReActRunner.run 호출 (monkeypatch 로 확인)."""
        import app.domains.rag.service as svc

        called = {}

        class FakeRunner:
            def __init__(self, retriever, *, max_iter=5):
                called["created"] = True

            def run(self, slots, top_k=8):
                called["run"] = True
                return _fake_results(2, "vector")

        monkeypatch.setattr(svc, "ReActRunner", FakeRunner)
        vector = FakeRetriever(_fake_results(2, "vector"), health_val=True)
        graph = FakeRetriever(health_val=True)
        monkeypatch.setattr(svc, "_vector_singleton", lambda: vector)
        monkeypatch.setattr(svc, "_graph_singleton", lambda: graph)
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: FakeRetriever())

        svc.retrieve(make_auto_slot(), mode="vector", react=True)

        assert called.get("created") is True
        assert called.get("run") is True

    def test_react_false_does_not_invoke_react_runner(self, monkeypatch):
        """react=False 면 ReActRunner 생성 안 함."""
        import app.domains.rag.service as svc

        called = {}

        class FakeRunner:
            def __init__(self, retriever, *, max_iter=5):
                called["created"] = True

            def run(self, slots, top_k=8):
                return []

        monkeypatch.setattr(svc, "ReActRunner", FakeRunner)
        vector = FakeRetriever(_fake_results(2, "vector"), health_val=True)
        graph = FakeRetriever(health_val=True)
        monkeypatch.setattr(svc, "_vector_singleton", lambda: vector)
        monkeypatch.setattr(svc, "_graph_singleton", lambda: graph)
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: FakeRetriever())

        svc.retrieve(make_auto_slot(), mode="vector", react=False)

        assert "created" not in called


# ===========================================================================
# clear_caches
# ===========================================================================


class TestClearCaches:
    """clear_caches() — lru_cache 초기화."""

    def test_clear_caches_does_not_raise(self):
        import app.domains.rag.service as svc

        svc.clear_caches()  # 예외 없이 실행 가능

    def test_clear_caches_resets_singletons(self, monkeypatch):
        """캐시 초기화 후 다시 호출하면 새 인스턴스 생성."""
        import app.domains.rag.service as svc

        # 최초 singleton 생성
        v1 = svc._vector_singleton()
        svc.clear_caches()
        v2 = svc._vector_singleton()

        # 새 인스턴스 (lru_cache 재생성)
        assert v1 is not v2


# ===========================================================================
# Sprint 8 — circuit breaker 동작 검증
# ===========================================================================


class TestCircuitBreaker:
    """_rag_circuit_breaker singleton + circuit open → vector 폴백 동작."""

    def test_circuit_breaker_singleton_returns_circuit_breaker(self):
        """_rag_circuit_breaker() 는 CircuitBreaker 인스턴스를 반환한다."""
        import app.domains.rag.service as svc
        from pybreaker import CircuitBreaker as CB

        # lru_cache 초기화 후 신규 생성
        svc._rag_circuit_breaker.cache_clear()
        cb = svc._rag_circuit_breaker()
        assert isinstance(cb, CB)

    def test_circuit_breaker_singleton_is_cached(self):
        """동일 인스턴스를 반환한다 (lru_cache 동작)."""
        import app.domains.rag.service as svc

        svc._rag_circuit_breaker.cache_clear()
        cb1 = svc._rag_circuit_breaker()
        cb2 = svc._rag_circuit_breaker()
        assert cb1 is cb2

    def test_circuit_breaker_opens_after_consecutive_failures(self, monkeypatch):
        """연속 fail_max 회 실패 후 circuit 이 open 된다 (CircuitBreakerError 발생).

        실제 CircuitBreaker 인스턴스 사용 — state machine 자체 검증.
        """
        import contextlib

        from pybreaker import CircuitBreaker, CircuitBreakerError

        # 테스트 전용 breaker (fail_max=3) 직접 생성
        test_breaker = CircuitBreaker(fail_max=3, reset_timeout=60, name="test_cb")

        def always_fail():
            raise RuntimeError("retriever error")

        # 2회 실패 → circuit 아직 closed
        for _ in range(2):
            with contextlib.suppress(RuntimeError):
                test_breaker.call(always_fail)

        # 3번째 실패에서 circuit open
        with contextlib.suppress(RuntimeError, CircuitBreakerError):
            test_breaker.call(always_fail)

        # 이후 호출은 CircuitBreakerError 발생
        with pytest.raises(CircuitBreakerError):
            test_breaker.call(always_fail)

    def test_circuit_open_falls_back_to_vector(self, monkeypatch):
        """circuit open 상태에서 retrieve() 는 vector 폴백을 시도한다."""
        import app.domains.rag.service as svc
        from pybreaker import CircuitBreakerError

        # circuit 이 항상 open 상태인 breaker stub
        class AlwaysOpenBreaker:
            def call(self, func, *args, **kwargs):
                raise CircuitBreakerError("circuit open")

        monkeypatch.setattr(svc, "_rag_circuit_breaker", lambda: AlwaysOpenBreaker())

        vector_results = _fake_results(2, "vector")
        vector = FakeRetriever(vector_results, health_val=True)
        graph = FakeRetriever(health_val=True)

        monkeypatch.setattr(svc, "_vector_singleton", lambda: vector)
        monkeypatch.setattr(svc, "_graph_singleton", lambda: graph)
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: FakeRetriever())

        # graph 모드로 호출 — circuit open → vector 폴백
        results = svc.retrieve(make_auto_slot(), mode="graph", react=False)

        assert len(results) > 0
        assert all(r["source"] == "vector" for r in results)

    def test_circuit_open_vector_mode_returns_empty(self, monkeypatch):
        """vector 모드에서 circuit open 이면 vector 직접 호출도 없이 빈 list."""
        import app.domains.rag.service as svc
        from pybreaker import CircuitBreakerError

        class AlwaysOpenBreaker:
            def call(self, func, *args, **kwargs):
                raise CircuitBreakerError("circuit open")

        monkeypatch.setattr(svc, "_rag_circuit_breaker", lambda: AlwaysOpenBreaker())

        vector = FakeRetriever(_fake_results(2, "vector"), health_val=True)
        graph = FakeRetriever(health_val=True)

        monkeypatch.setattr(svc, "_vector_singleton", lambda: vector)
        monkeypatch.setattr(svc, "_graph_singleton", lambda: graph)
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: FakeRetriever())

        # vector 모드에서 circuit open → 폴백 없이 빈 list
        results = svc.retrieve(make_auto_slot(), mode="vector", react=False)

        assert results == []

    def test_circuit_open_vector_fallback_also_fails_returns_empty(self, monkeypatch):
        """circuit open + vector 폴백까지 실패하면 빈 list 반환."""
        import app.domains.rag.service as svc
        from pybreaker import CircuitBreakerError

        class AlwaysOpenBreaker:
            def call(self, func, *args, **kwargs):
                raise CircuitBreakerError("circuit open")

        monkeypatch.setattr(svc, "_rag_circuit_breaker", lambda: AlwaysOpenBreaker())

        # vector 도 실패하는 retriever
        vector_raises = FakeRetriever(raise_exc=True, health_val=True)
        graph = FakeRetriever(health_val=True)

        monkeypatch.setattr(svc, "_vector_singleton", lambda: vector_raises)
        monkeypatch.setattr(svc, "_graph_singleton", lambda: graph)
        monkeypatch.setattr(svc, "_hybrid_singleton", lambda: FakeRetriever())

        results = svc.retrieve(make_auto_slot(), mode="graph", react=False)

        assert results == []

    def test_circuit_breaker_cache_clear_on_isolate(self):
        """isolate_rag_caches fixture 에서 _rag_circuit_breaker cache 도 정리된다."""
        import app.domains.rag.service as svc

        # autouse 픽스처가 clear_caches() 를 호출하므로 breaker 도 재생성 가능
        svc._rag_circuit_breaker.cache_clear()
        cb = svc._rag_circuit_breaker()
        assert cb is not None


# ===========================================================================
# Sprint 11 — run_agent() 분기 테스트
# ===========================================================================


class TestRunAgent:
    """run_agent() — AgentRunner 를 지연 import 해 실행한다."""

    def test_run_agent_returns_agent_result(self, monkeypatch):
        """run_agent 가 AgentResult 반환."""
        import app.domains.rag.service as svc
        from app.domains.rag.agent import AgentResult

        fake_result = AgentResult(
            chunks=[{"id": "c1"}],
            tool_results=[{"tool": "finish"}],
            iterations=1,
            finish_reason="finish",
        )

        class FakeAgentRunner:
            def __init__(self, **kwargs):
                pass

            def run(self, slots, user_message):
                return fake_result

        # 지연 import 경로 monkeypatch
        monkeypatch.setattr("app.domains.rag.agent.AgentRunner", FakeAgentRunner)

        slots = make_auto_slot()
        result = svc.run_agent(slots, "청구하고 싶어요")

        assert result.finish_reason == "finish"
        assert result.chunks == [{"id": "c1"}]
        assert result.iterations == 1

    def test_run_agent_calls_runner_with_correct_args(self, monkeypatch):
        """run_agent 가 AgentRunner.run 에 slots + user_message 를 그대로 전달."""
        import app.domains.rag.service as svc
        from app.domains.rag.agent import AgentResult

        captured = {}

        class FakeAgentRunner:
            def __init__(self, **kwargs):
                pass

            def run(self, slots, user_message):
                captured["slots"] = slots
                captured["message"] = user_message
                return AgentResult(finish_reason="finish")

        monkeypatch.setattr("app.domains.rag.agent.AgentRunner", FakeAgentRunner)

        slots = make_auto_slot()
        svc.run_agent(slots, "자동차 추돌 사고")

        assert captured["slots"] is slots
        assert captured["message"] == "자동차 추돌 사고"

    def test_run_agent_propagates_exception(self, monkeypatch):
        """AgentRunner.run 예외는 그대로 전파 (sessions.service 가 폴백 처리)."""
        import app.domains.rag.service as svc

        class BrokenAgentRunner:
            def __init__(self, **kwargs):
                pass

            def run(self, slots, user_message):
                raise RuntimeError("agent 내부 오류")

        monkeypatch.setattr("app.domains.rag.agent.AgentRunner", BrokenAgentRunner)

        import pytest as _pytest

        with _pytest.raises(RuntimeError, match="agent 내부 오류"):
            svc.run_agent(make_auto_slot(), "질문")
