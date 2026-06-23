"""tests.rag.test_graph

app/rag/graph.py 단위 테스트.

테스트 대상:
    - _extract_rows: intermediate_steps 에서 context rows 추출
    - _rows_to_results: Cypher rows → RetrievalResult 변환
    - _rank_to_score: rank 기반 score 계산 (0.5~0.9 범위)
    - GraphRetriever.retrieve: mock chain.invoke → RetrievalResult 변환 + 예외 시 빈 list
    - GraphRetriever.health: graph.query 성공/실패

mock 정책:
    - cached_property(_graph, _chain) 를 monkeypatch 로 우회
    - langchain_neo4j / langchain_openai 실 호출 없음
"""

from __future__ import annotations

import pytest
from app.domains.rag.graph import (
    GraphRetriever,
    _extract_rows,
    _rank_to_score,
    _rows_to_results,
)

from tests.rag.conftest import make_auto_slot

# ===========================================================================
# _extract_rows
# ===========================================================================


class TestExtractRows:
    """_extract_rows — intermediate_steps 파싱."""

    def test_extracts_context_from_steps(self):
        rows = [{"c.chunk_id": "abc", "c.text": "본문"}]
        steps = [
            {"query": "MATCH (c:Clause) RETURN c"},
            {"context": rows},
        ]
        result = _extract_rows(steps)
        assert result == rows

    def test_empty_steps_returns_empty_list(self):
        assert _extract_rows([]) == []

    def test_no_context_key_returns_empty(self):
        steps = [{"query": "MATCH (n) RETURN n"}]
        assert _extract_rows(steps) == []

    def test_context_not_list_returns_empty(self):
        """context 가 list 아닌 경우 빈 list."""
        steps = [{"context": "not a list"}]
        assert _extract_rows(steps) == []

    def test_last_context_wins(self):
        """여러 steps 중 마지막 context 반환 (reversed 탐색)."""
        rows_first = [{"c.chunk_id": "first"}]
        rows_last = [{"c.chunk_id": "last"}]
        steps = [
            {"context": rows_first},
            {"query": "MATCH ..."},
            {"context": rows_last},
        ]
        result = _extract_rows(steps)
        assert result[0]["c.chunk_id"] == "last"


# ===========================================================================
# _rows_to_results
# ===========================================================================


class TestRowsToResults:
    """_rows_to_results — Cypher rows → RetrievalResult."""

    def _make_row(
        self,
        chunk_id="abc",
        text="보험금 관련 조항입니다.",
        clause_no="제1조",
        page_start=1,
    ) -> dict:
        return {
            "c.chunk_id": chunk_id,
            "c.text": text,
            "c.clause_no": clause_no,
            "c.page_start": page_start,
        }

    def test_converts_row_to_retrieval_result(self):
        rows = [self._make_row()]
        results = _rows_to_results(rows, top_k=8)
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "abc"
        assert r["text"] == "보험금 관련 조항입니다."
        assert r["source"] == "graph"

    def test_row_without_chunk_id_skipped(self):
        """chunk_id 없는 row 는 결과에서 제외."""
        rows = [{"c.text": "본문만 있음"}]
        results = _rows_to_results(rows, top_k=8)
        assert results == []

    def test_metadata_contains_clause_no_and_page(self):
        rows = [self._make_row(clause_no="제5조", page_start=10)]
        results = _rows_to_results(rows, top_k=8)
        assert results[0]["metadata"]["clause_no"] == "제5조"
        assert results[0]["metadata"]["page_start"] == 10

    def test_top_k_limits_results(self):
        rows = [self._make_row(chunk_id=f"c{i}") for i in range(10)]
        results = _rows_to_results(rows, top_k=3)
        assert len(results) == 3

    def test_score_decreases_with_rank(self):
        """상위 rank 의 score 가 더 높다."""
        rows = [self._make_row(chunk_id=f"c{i}") for i in range(3)]
        results = _rows_to_results(rows, top_k=8)
        scores = [r["score"] for r in results]
        assert scores[0] > scores[1] > scores[2]

    def test_alternate_column_names_c_dot_prefix(self):
        """c. 접두사 없는 컬럼도 인식."""
        rows = [
            {
                "chunk_id": "xyz",
                "text": "대체 컬럼명",
                "clause_no": "제2조",
                "page_start": 3,
            }
        ]
        results = _rows_to_results(rows, top_k=8)
        assert len(results) == 1
        assert results[0]["id"] == "xyz"

    def test_empty_rows_returns_empty(self):
        assert _rows_to_results([], top_k=8) == []


# ===========================================================================
# _rank_to_score
# ===========================================================================


class TestRankToScore:
    """_rank_to_score — 0.5~0.9 범위 검증."""

    def test_single_result_returns_0_8(self):
        assert _rank_to_score(0, 1) == 0.8

    def test_first_rank_returns_0_9(self):
        score = _rank_to_score(0, 10)
        assert score == pytest.approx(0.9)

    def test_last_rank_returns_0_5(self):
        score = _rank_to_score(9, 10)
        assert score == pytest.approx(0.9 - 0.4 * (9 / 9))

    def test_score_in_valid_range(self):
        """모든 rank 에서 0.5 <= score <= 0.9."""
        total = 8
        for rank in range(total):
            s = _rank_to_score(rank, total)
            assert 0.5 <= s <= 0.9, f"rank={rank} score={s} out of range"


# ===========================================================================
# GraphRetriever.retrieve (cached_property mock)
# ===========================================================================


class TestGraphRetrieverRetrieve:
    """GraphRetriever.retrieve — mock chain.invoke 결과를 RetrievalResult 로 변환."""

    def _make_fake_chain_result(self, chunk_ids=("abc",)):
        context = [
            {
                "c.chunk_id": cid,
                "c.text": f"약관 조항 {cid}",
                "c.clause_no": "제1조",
                "c.page_start": 1,
            }
            for cid in chunk_ids
        ]
        return {
            "result": "보험금 지급 가능",
            "intermediate_steps": [
                {"query": "MATCH (c:Clause) RETURN c.chunk_id"},
                {"context": context},
            ],
        }

    def test_retrieve_returns_results_with_graph_source(self, monkeypatch):
        """chain.invoke 결과를 source="graph" RetrievalResult 로 변환."""
        retriever = GraphRetriever()
        fake_result = self._make_fake_chain_result(["abc"])

        class FakeChain:
            def invoke(self, _):
                return fake_result

        # cached_property 우회 — instance __dict__ 에 직접 설정
        retriever.__dict__["_chain"] = FakeChain()
        retriever.__dict__["_graph"] = object()  # health 용

        results = retriever.retrieve(make_auto_slot(), top_k=8)

        assert len(results) == 1
        assert results[0]["id"] == "abc"
        assert results[0]["source"] == "graph"

    def test_retrieve_multiple_rows(self, monkeypatch):
        retriever = GraphRetriever()
        fake_result = self._make_fake_chain_result(["c1", "c2", "c3"])

        class FakeChain:
            def invoke(self, _):
                return fake_result

        retriever.__dict__["_chain"] = FakeChain()
        retriever.__dict__["_graph"] = object()

        results = retriever.retrieve(make_auto_slot(), top_k=8)

        assert len(results) == 3

    def test_retrieve_returns_empty_on_chain_exception(self):
        """chain.invoke 예외 → 빈 list."""
        retriever = GraphRetriever()

        class FailChain:
            def invoke(self, _):
                raise RuntimeError("Cypher 실패")

        retriever.__dict__["_chain"] = FailChain()
        retriever.__dict__["_graph"] = object()

        results = retriever.retrieve(make_auto_slot(), top_k=8)

        assert results == []

    def test_retrieve_empty_intermediate_steps(self):
        """intermediate_steps 없으면 빈 list."""
        retriever = GraphRetriever()

        class FakeChain:
            def invoke(self, _):
                return {"result": "ok", "intermediate_steps": []}

        retriever.__dict__["_chain"] = FakeChain()
        retriever.__dict__["_graph"] = object()

        results = retriever.retrieve(make_auto_slot(), top_k=8)
        assert results == []

    def test_retrieve_respects_top_k(self):
        retriever = GraphRetriever()
        fake_result = self._make_fake_chain_result([f"c{i}" for i in range(10)])

        class FakeChain:
            def invoke(self, _):
                return fake_result

        retriever.__dict__["_chain"] = FakeChain()
        retriever.__dict__["_graph"] = object()

        results = retriever.retrieve(make_auto_slot(), top_k=3)
        assert len(results) <= 3


# ===========================================================================
# GraphRetriever.health
# ===========================================================================


class TestGraphRetrieverHealth:
    """health() — Neo4j graph.query 성공/실패."""

    def test_health_returns_true_when_query_succeeds(self):
        retriever = GraphRetriever()

        class FakeGraph:
            def query(self, cypher):
                return [{"ok": 1}]

        retriever.__dict__["_graph"] = FakeGraph()

        assert retriever.health() is True

    def test_health_returns_false_when_query_raises(self):
        retriever = GraphRetriever()

        class BadGraph:
            def query(self, cypher):
                raise ConnectionError("Neo4j 다운")

        retriever.__dict__["_graph"] = BadGraph()

        assert retriever.health() is False
