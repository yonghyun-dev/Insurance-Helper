"""tests.rag.test_neurosymbolic — 뉴로심볼릭 융합 retriever 단위 테스트 (Sprint 32 T2).

FakeVector/FakeSymbolic 으로 RRF 융합·graceful 강등·스코프 검증·점수컷을 검증한다.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.domains.rag.neurosymbolic import NeuroSymbolicRetriever, _rrf


def _chunk(cid: str, score: float | None = 0.5, insurer: str = "samsung") -> dict[str, Any]:
    return {
        "id": cid,
        "text": f"본문 {cid}",
        "score": score,
        "metadata": {"insurer_id": insurer, "clause_no": "제3조", "chunk_type": "article"},
    }


class FakeAdapter:
    def __init__(self, results: list[dict[str, Any]]):
        self.results = results
        self.calls: list[dict[str, Any]] = []

    def query(self, query_text: str, top_k: int = 8, filters: dict | None = None):
        self.calls.append({"q": query_text, "top_k": top_k, "filters": filters})
        return self.results[:top_k]

    def health(self) -> bool:
        return True


class FakeVector:
    def __init__(self, results: list[dict[str, Any]]):
        self.adapter = FakeAdapter(results)

    def health(self) -> bool:
        return True


class FakeSymbolic:
    def __init__(self, cands: list[dict] | None = None, expanded: list[dict] | None = None,
                 fail: bool = False):
        self.cands = cands or []
        self.expanded = expanded or []
        self.fail = fail

    def clause_candidates(self, query, insurer_id, limit=12):
        if self.fail:
            raise ConnectionError("graph down")
        return self.cands[:limit]

    def expand(self, chunk_ids, limit=16):
        if self.fail:
            raise ConnectionError("graph down")
        return self.expanded[:limit]


@pytest.fixture(autouse=True)
def _no_score_cut(monkeypatch):
    """점수컷 비활성 기본 (컷 전용 테스트에서 개별 활성)."""
    from app.infrastructure.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rag_score_ratio", 0.0)
    monkeypatch.setattr(settings, "rag_graph_enabled", True)
    yield


class TestRrf:
    def test_chunk_in_multiple_rankings_boosted(self):
        scores = _rrf([["a", "b"], ["b", "c"]])
        assert scores["b"] > scores["a"] > scores["c"]

    def test_rank_order_preserved_single_ranking(self):
        scores = _rrf([["a", "b", "c"]])
        assert scores["a"] > scores["b"] > scores["c"]


class TestFusion:
    def test_neural_only_when_graph_disabled(self, monkeypatch):
        from app.infrastructure.core.config import get_settings

        monkeypatch.setattr(get_settings(), "rag_graph_enabled", False)
        r = NeuroSymbolicRetriever(
            vector=FakeVector([_chunk("n1"), _chunk("n2")]),
            symbolic=FakeSymbolic(fail=True),  # 호출되면 안 됨 — 비활성이므로 안전
        )
        out = r.retrieve_fused("q", "samsung", None, top_k=8)
        assert [c["id"] for c in out] == ["n1", "n2"]
        assert all(c["source"] == "neural" for c in out)

    def test_graceful_degrade_on_graph_failure(self):
        r = NeuroSymbolicRetriever(
            vector=FakeVector([_chunk("n1")]),
            symbolic=FakeSymbolic(fail=True),
        )
        out = r.retrieve_fused("q", "samsung", None, top_k=8)
        assert [c["id"] for c in out] == ["n1"]

    def test_symbolic_candidates_fused_and_hydrated(self, monkeypatch):
        # 심볼릭 전용 청크 s1 은 SQLite 하이드레이션 경유
        monkeypatch.setattr(
            "app.domains.rag.neurosymbolic._hydrate_chunks",
            lambda ids: {cid: _chunk(cid, score=None) for cid in ids},
        )
        r = NeuroSymbolicRetriever(
            vector=FakeVector([_chunk("n1"), _chunk("n2")]),
            symbolic=FakeSymbolic(
                cands=[{"chunk_id": "s1", "match_score": 2}],
                expanded=[{"chunk_id": "n2", "via": "sibling", "src_rank": 0}],
            ),
        )
        out = r.retrieve_fused("q", "samsung", None, top_k=8)
        ids = [c["id"] for c in out]
        assert "s1" in ids
        # n2 는 뉴럴+확장 양쪽 → RRF 부스트로 n1 보다 앞서야 함
        assert ids.index("n2") < ids.index("n1")
        s1 = next(c for c in out if c["id"] == "s1")
        assert s1["source"] == "symbolic"

    def test_scope_violation_excluded(self, monkeypatch):
        # 하이드레이트 결과가 타 보험사면 편입 금지 (정합 불변식)
        monkeypatch.setattr(
            "app.domains.rag.neurosymbolic._hydrate_chunks",
            lambda ids: {cid: _chunk(cid, score=None, insurer="meritz") for cid in ids},
        )
        r = NeuroSymbolicRetriever(
            vector=FakeVector([_chunk("n1")]),
            symbolic=FakeSymbolic(cands=[{"chunk_id": "other1", "match_score": 3}]),
        )
        out = r.retrieve_fused("q", "samsung", None, top_k=8)
        assert all(c["metadata"]["insurer_id"] == "samsung" for c in out)

    def test_score_ratio_cut_applied_to_neural(self, monkeypatch):
        from app.infrastructure.core.config import get_settings

        monkeypatch.setattr(get_settings(), "rag_score_ratio", 0.5)
        r = NeuroSymbolicRetriever(
            vector=FakeVector([_chunk("hi", 0.8), _chunk("mid", 0.5), _chunk("low", 0.1)]),
            symbolic=FakeSymbolic(),
        )
        out = r.retrieve_fused("q", "samsung", None, top_k=8)
        ids = [c["id"] for c in out]
        assert "low" not in ids and "hi" in ids and "mid" in ids

    def test_top_k_respected(self):
        r = NeuroSymbolicRetriever(
            vector=FakeVector([_chunk(f"n{i}") for i in range(10)]),
            symbolic=FakeSymbolic(),
        )
        assert len(r.retrieve_fused("q", None, None, top_k=3)) == 3

    def test_empty_neural_and_symbolic_returns_empty(self):
        r = NeuroSymbolicRetriever(vector=FakeVector([]), symbolic=FakeSymbolic())
        assert r.retrieve_fused("q", None, None, top_k=8) == []
