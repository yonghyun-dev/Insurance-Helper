"""tests.rag.test_hybrid

app/rag/hybrid.py 단위 테스트.

테스트 대상:
    - _dedupe_by_id: 중복 제거 (score 높은 것 유지)
    - HybridRetriever.retrieve:
        - graph 미주입 시 vector only
        - graph 주입 시 dedupe + score 정렬
        - graph retrieve 예외 시 vector fallback
    - HybridRetriever.health: vector.health() 위임
"""

from __future__ import annotations

from app.domains.rag.hybrid import HybridRetriever, _dedupe_by_id

from tests.rag.conftest import make_auto_slot, make_retrieval_result

# ===========================================================================
# _dedupe_by_id
# ===========================================================================


class TestDedupeById:
    """_dedupe_by_id — 동일 id 중복 제거."""

    def test_no_duplicates_returns_all(self):
        items = [
            make_retrieval_result("a", score=0.9),
            make_retrieval_result("b", score=0.8),
        ]
        result = _dedupe_by_id(items)
        assert len(result) == 2

    def test_duplicate_keeps_higher_score(self):
        """같은 id 두 개 중 score 높은 것을 유지."""
        low = make_retrieval_result("x", score=0.6)
        high = make_retrieval_result("x", score=0.9)
        result = _dedupe_by_id([low, high])
        assert len(result) == 1
        assert result[0]["score"] == 0.9

    def test_duplicate_order_first_then_update_score(self):
        """같은 id: 먼저 나온 것이 score 낮아도 높은 score 로 교체."""
        first_low = make_retrieval_result("x", score=0.5)
        second_high = make_retrieval_result("x", score=0.95)
        result = _dedupe_by_id([first_low, second_high])
        assert result[0]["score"] == 0.95

    def test_empty_input_returns_empty(self):
        assert _dedupe_by_id([]) == []

    def test_single_item_unchanged(self):
        item = make_retrieval_result("a", score=0.7)
        result = _dedupe_by_id([item])
        assert len(result) == 1
        assert result[0]["id"] == "a"

    def test_different_sources_same_id_deduped(self):
        """vector 와 graph 에서 같은 chunk_id 가 오면 중복 제거."""
        from tests.rag.conftest import make_retrieval_result

        vec = make_retrieval_result("shared", score=0.7, source="vector")
        gr = make_retrieval_result("shared", score=0.85, source="graph")
        result = _dedupe_by_id([vec, gr])
        assert len(result) == 1
        assert result[0]["score"] == 0.85

    def test_all_unique_preserved(self):
        items = [make_retrieval_result(f"c{i}") for i in range(5)]
        result = _dedupe_by_id(items)
        assert len(result) == 5


# ===========================================================================
# HybridRetriever.retrieve
# ===========================================================================


class FakeVectorRetriever:
    """VectorRetriever stub."""

    def __init__(self, results=None):
        self._results = results or []

    def retrieve(self, slots, top_k=8):
        return self._results[:top_k]

    def health(self):
        return True


class FakeGraphRetriever:
    """GraphRetriever stub."""

    def __init__(self, results=None, raise_exc=False):
        self._results = results or []
        self._raise = raise_exc

    def retrieve(self, slots, top_k=8):
        if self._raise:
            raise RuntimeError("Neo4j 연결 실패")
        return self._results[:top_k]


class TestHybridRetrieverRetrieve:
    """HybridRetriever.retrieve 분기 검증."""

    def test_graph_none_returns_vector_only(self):
        """graph 미주입 — vector only 반환."""
        v_results = [make_retrieval_result("v1"), make_retrieval_result("v2")]
        vector = FakeVectorRetriever(v_results)
        retriever = HybridRetriever(vector=vector, graph=None)

        results = retriever.retrieve(make_auto_slot(), top_k=8)

        assert len(results) == 2
        assert all(r["source"] == "vector" for r in results)

    def test_graph_injected_merges_and_dedupes(self):
        """graph 주입 — vector + graph 합산 후 dedupe."""
        v_results = [
            make_retrieval_result("shared", score=0.7, source="vector"),
            make_retrieval_result("only_v", score=0.6, source="vector"),
        ]
        g_results = [
            make_retrieval_result("shared", score=0.9, source="graph"),
            make_retrieval_result("only_g", score=0.8, source="graph"),
        ]
        vector = FakeVectorRetriever(v_results)
        graph = FakeGraphRetriever(g_results)
        retriever = HybridRetriever(vector=vector, graph=graph)

        results = retriever.retrieve(make_auto_slot(), top_k=8)

        ids = [r["id"] for r in results]
        assert "shared" in ids
        assert "only_v" in ids
        assert "only_g" in ids
        # shared 는 한 개만
        assert ids.count("shared") == 1

    def test_graph_injected_result_sorted_by_score_desc(self):
        """합산 후 score 내림차순 정렬."""
        v_results = [make_retrieval_result("v1", score=0.5, source="vector")]
        g_results = [make_retrieval_result("g1", score=0.95, source="graph")]
        vector = FakeVectorRetriever(v_results)
        graph = FakeGraphRetriever(g_results)
        retriever = HybridRetriever(vector=vector, graph=graph)

        results = retriever.retrieve(make_auto_slot(), top_k=8)

        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_graph_exception_falls_back_to_vector(self):
        """graph.retrieve 예외 → vector only 반환."""
        v_results = [make_retrieval_result("v1"), make_retrieval_result("v2")]
        vector = FakeVectorRetriever(v_results)
        graph = FakeGraphRetriever(raise_exc=True)
        retriever = HybridRetriever(vector=vector, graph=graph)

        results = retriever.retrieve(make_auto_slot(), top_k=8)

        assert len(results) == 2
        assert all(r["source"] == "vector" for r in results)

    def test_result_count_capped_at_top_k(self):
        """top_k 초과 결과 잘라냄."""
        v_results = [make_retrieval_result(f"v{i}", score=0.5) for i in range(5)]
        g_results = [make_retrieval_result(f"g{i}", score=0.6) for i in range(5)]
        vector = FakeVectorRetriever(v_results)
        graph = FakeGraphRetriever(g_results)
        retriever = HybridRetriever(vector=vector, graph=graph)

        results = retriever.retrieve(make_auto_slot(), top_k=6)

        assert len(results) <= 6


# ===========================================================================
# HybridRetriever.health
# ===========================================================================


class TestHybridRetrieverHealth:
    def test_health_delegates_to_vector(self, monkeypatch):
        """health() 는 vector.health() 를 위임."""

        class FakeVec:
            def retrieve(self, s, k=8):
                return []

            def health(self):
                return True

        retriever = HybridRetriever(vector=FakeVec(), graph=None)
        assert retriever.health() is True

    def test_health_false_when_vector_fails(self):
        class FakeVecBad:
            def retrieve(self, s, k=8):
                return []

            def health(self):
                return False

        retriever = HybridRetriever(vector=FakeVecBad(), graph=None)
        assert retriever.health() is False
