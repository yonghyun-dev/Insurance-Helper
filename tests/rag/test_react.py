"""tests.rag.test_react

app/rag/react.py 단위 테스트.

테스트 대상:
    - ReActRunner.run 종료 조건 4가지:
        1. score > 0.92 → 즉시 종료
        2. distinct clause >= 3 → 종료
        3. LLM Think → FINISH → 종료
        4. max_iter 도달 → 강제 종료
    - _dedupe_by_id: 순서 보존 + score 높은 것 유지
    - _distinct_clause_count: clause_no 기준 distinct 수
"""

from __future__ import annotations

from app.domains.rag.react import (
    ReActRunner,
    _dedupe_by_id,
    _distinct_clause_count,
)

from tests.rag.conftest import make_auto_slot, make_retrieval_result

# ===========================================================================
# helpers
# ===========================================================================


class TestDedupeByIdReact:
    """react._dedupe_by_id — 순서 보존 + score 높은 것 유지."""

    def test_empty_returns_empty(self):
        assert _dedupe_by_id([]) == []

    def test_no_duplicate_preserves_order(self):
        items = [
            make_retrieval_result("a", score=0.8),
            make_retrieval_result("b", score=0.7),
            make_retrieval_result("c", score=0.6),
        ]
        result = _dedupe_by_id(items)
        assert [r["id"] for r in result] == ["a", "b", "c"]

    def test_duplicate_keeps_higher_score_updates_value(self):
        """첫 등장 순서 유지, score 는 높은 값으로 교체."""
        low = make_retrieval_result("x", score=0.5)
        high = make_retrieval_result("x", score=0.9)
        result = _dedupe_by_id([low, high])
        assert len(result) == 1
        assert result[0]["score"] == 0.9

    def test_order_is_first_seen(self):
        """중복이 있어도 처음 등장 위치를 순서로 유지."""
        a = make_retrieval_result("a", score=0.5)
        b = make_retrieval_result("b", score=0.9)
        a2 = make_retrieval_result("a", score=0.95)  # a 의 두 번째 등장
        result = _dedupe_by_id([a, b, a2])
        # a 가 먼저 등장했으므로 a → b 순서
        assert result[0]["id"] == "a"
        assert result[1]["id"] == "b"
        # a 의 score 는 높은 값으로 교체
        assert result[0]["score"] == 0.95


class TestDistinctClauseCount:
    """_distinct_clause_count — clause_no 기준 distinct 수."""

    def test_empty_returns_zero(self):
        assert _distinct_clause_count([]) == 0

    def test_single_item_returns_one(self):
        items = [make_retrieval_result("c1", clause_no="제1조")]
        assert _distinct_clause_count(items) == 1

    def test_same_clause_no_counts_once(self):
        items = [
            make_retrieval_result("c1", clause_no="제1조"),
            make_retrieval_result("c2", clause_no="제1조"),
        ]
        assert _distinct_clause_count(items) == 1

    def test_different_clause_nos_count_separately(self):
        items = [
            make_retrieval_result("c1", clause_no="제1조"),
            make_retrieval_result("c2", clause_no="제2조"),
            make_retrieval_result("c3", clause_no="제3조"),
        ]
        assert _distinct_clause_count(items) == 3

    def test_no_clause_no_falls_back_to_id(self):
        """clause_no 없으면 id 로 distinct 계산."""
        items = [
            {
                "id": "uuid_1",
                "text": "본문",
                "score": 0.8,
                "metadata": {},  # clause_no 없음
                "source": "vector",
            },
            {
                "id": "uuid_2",
                "text": "본문",
                "score": 0.8,
                "metadata": {},
                "source": "vector",
            },
        ]
        assert _distinct_clause_count(items) == 2


# ===========================================================================
# ReActRunner.run — 종료 조건
# ===========================================================================


class ControlledRetriever:
    """각 호출마다 다른 결과를 반환하는 Retriever stub."""

    def __init__(self, results_per_call: list[list]):
        self._calls = list(results_per_call)
        self._idx = 0

    def retrieve(self, slots, top_k=8):
        result = self._calls[self._idx] if self._idx < len(self._calls) else []
        self._idx += 1
        return result


class TestReActRunnerTermination:
    """ReActRunner.run 종료 조건 4가지."""

    def test_terminates_on_high_score(self):
        """조건 1: score > 0.92 → 첫 iter 에서 종료."""
        high_score_chunk = make_retrieval_result("c1", score=0.95)
        retriever = ControlledRetriever([[high_score_chunk]])
        runner = ReActRunner(retriever, max_iter=5)

        results = runner.run(make_auto_slot(), top_k=8)

        # 고신뢰 청크 포함
        assert any(r["score"] > 0.92 for r in results)
        # retriever 는 1번만 호출됨 (즉시 종료)
        assert retriever._idx == 1

    def test_terminates_on_distinct_clauses(self):
        """조건 2: distinct clause >= 3 → 종료."""
        # 3개의 다른 clause_no 를 가진 청크 (score 는 모두 0.92 이하)
        chunks_with_3_clauses = [
            make_retrieval_result("c1", score=0.7, clause_no="제1조"),
            make_retrieval_result("c2", score=0.7, clause_no="제2조"),
            make_retrieval_result("c3", score=0.7, clause_no="제3조"),
        ]
        retriever = ControlledRetriever([chunks_with_3_clauses])
        runner = ReActRunner(retriever, max_iter=5)

        results = runner.run(make_auto_slot(), top_k=8)

        assert len(results) >= 3

    def test_terminates_on_llm_finish(self, monkeypatch):
        """조건 3: LLM Think → FINISH → 종료."""
        # score 낮고 clause 1개 → 조건 1, 2 미충족 → Think 호출
        low_chunks = [make_retrieval_result("c1", score=0.5, clause_no="제1조")]
        retriever = ControlledRetriever([low_chunks, low_chunks, low_chunks])

        # _think 를 FINISH 로 mock
        runner = ReActRunner(retriever, max_iter=5)
        monkeypatch.setattr(runner, "_think", lambda slots, acc, it: "FINISH")

        runner.run(make_auto_slot(), top_k=8)

        # FINISH 로 인해 max_iter 전에 종료됨
        assert retriever._idx <= 2  # 최대 2번 호출 (1번 retrieve + think 에서 finish)

    def test_terminates_on_max_iter(self, monkeypatch):
        """조건 4: max_iter 도달 → 강제 종료."""
        low_chunk = [make_retrieval_result("c1", score=0.5, clause_no="제1조")]
        # max_iter=3 번 계속 같은 청크 반환 (조건 1,2,3 미충족)
        retriever = ControlledRetriever([low_chunk] * 3)

        runner = ReActRunner(retriever, max_iter=3)
        # Think 는 항상 REFINE 반환
        monkeypatch.setattr(runner, "_think", lambda slots, acc, it: "REFINE")

        runner.run(make_auto_slot(), top_k=8)

        # max_iter=3 도달로 종료
        # 마지막 iter 에서는 think 호출 없이 break (코드 참조)
        assert retriever._idx == 3

    def test_run_returns_at_most_top_k(self, monkeypatch):
        """run() 반환 결과는 top_k 이하."""
        many_chunks = [
            make_retrieval_result(f"c{i}", score=0.5, clause_no=f"제{i}조")
            for i in range(20)
        ]
        retriever = ControlledRetriever([many_chunks])
        runner = ReActRunner(retriever, max_iter=2)
        monkeypatch.setattr(runner, "_think", lambda s, a, i: "FINISH")

        results = runner.run(make_auto_slot(), top_k=5)

        assert len(results) <= 5

    def test_run_dedupes_across_iterations(self, monkeypatch):
        """반복 검색에서 동일 청크 중복 제거."""
        same_chunk = make_retrieval_result("c1", score=0.5, clause_no="제1조")
        retriever = ControlledRetriever([[same_chunk], [same_chunk]])

        runner = ReActRunner(retriever, max_iter=3)
        monkeypatch.setattr(runner, "_think", lambda s, a, i: "FINISH")

        results = runner.run(make_auto_slot(), top_k=8)

        ids = [r["id"] for r in results]
        assert ids.count("c1") == 1

    def test_run_with_empty_retriever(self, monkeypatch):
        """검색 결과가 없어도 예외 없이 빈 list 반환."""
        retriever = ControlledRetriever([[], [], []])
        runner = ReActRunner(retriever, max_iter=3)
        monkeypatch.setattr(runner, "_think", lambda s, a, i: "REFINE")

        results = runner.run(make_auto_slot(), top_k=8)

        assert results == []
