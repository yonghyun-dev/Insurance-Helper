"""tests.rag.test_vector

app/rag/vector.py 단위 테스트.

테스트 대상:
    - VectorRetriever.retrieve: 어댑터 query 결과에 source="vector" 부착
    - VectorRetriever.health: 어댑터 health 위임

Sprint 12 (REQ-13) 변경:
    - 기존 monkeypatch search_service 패턴 → fake adapter 주입 패턴.
    - VectorRetriever 가 VectorStoreAdapter 를 인자로 받도록 리팩토링됨.
"""

from __future__ import annotations

from typing import Any

from app.domains.rag.vector import VectorRetriever

from tests.rag.conftest import make_accident_disease_slot, make_empty_slot

# ---------------------------------------------------------------------------
# 공통 fake adapter
# ---------------------------------------------------------------------------


class _FakeAdapter:
    """VectorStoreAdapter 호환 fake. query 호출을 captured 에 기록."""

    def __init__(self, results: list[dict] | None = None, *, health_ok: bool = True) -> None:
        self._results = results or []
        self._health_ok = health_ok
        self.captured: dict[str, Any] = {}

    def query(self, query_text, top_k=8, filters=None):
        self.captured["query_text"] = query_text
        self.captured["top_k"] = top_k
        self.captured["filters"] = filters
        return self._results

    def health(self) -> bool:
        if isinstance(self._health_ok, BaseException):
            raise self._health_ok
        return self._health_ok

    # 미사용 메서드 (Protocol 만족용 stub)
    def upsert(self, *_a, **_kw) -> None:  # pragma: no cover
        pass

    def delete_by_document(self, *_a, **_kw) -> int:  # pragma: no cover
        return 0

    def count(self) -> int:  # pragma: no cover
        return 0


def _fake_result(chunk_id: str = "c1", score: float = 0.85) -> dict:
    return {
        "id": chunk_id,
        "text": f"약관 조항 텍스트 {chunk_id}",
        "score": score,
        "metadata": {
            "clause_no": "제1조",
            "insurer_name": "한화손해보험",
        },
    }


# ===========================================================================
# VectorRetriever.retrieve
# ===========================================================================


class TestVectorRetrieverRetrieve:
    """retrieve() — 어댑터 query 결과에 source 필드 부착."""

    def test_retrieve_attaches_source_vector(self):
        adapter = _FakeAdapter([_fake_result("c1"), _fake_result("c2")])
        retriever = VectorRetriever(adapter=adapter)

        results = retriever.retrieve(make_accident_disease_slot(), top_k=2)

        assert len(results) == 2
        for r in results:
            assert r["source"] == "vector"

    def test_retrieve_preserves_id_text_score_metadata(self):
        adapter = _FakeAdapter([_fake_result("chunk_x", score=0.9)])
        retriever = VectorRetriever(adapter=adapter)

        results = retriever.retrieve(make_accident_disease_slot(), top_k=1)

        assert results[0]["id"] == "chunk_x"
        assert results[0]["score"] == 0.9
        assert results[0]["text"] == "약관 조항 텍스트 chunk_x"
        assert "clause_no" in results[0]["metadata"]

    def test_retrieve_passes_correct_top_k(self):
        adapter = _FakeAdapter([])
        retriever = VectorRetriever(adapter=adapter)
        retriever.retrieve(make_accident_disease_slot(), top_k=5)

        assert adapter.captured["top_k"] == 5

    def test_retrieve_passes_filters_from_slots(self):
        adapter = _FakeAdapter([])
        retriever = VectorRetriever(adapter=adapter)
        retriever.retrieve(make_accident_disease_slot(), top_k=3)

        # make_accident_disease_slot() insurer="현대해상" → insurer_id "hyundai" 필터 포함
        assert adapter.captured["filters"] == {
            "area": "accident_disease",
            "insurer_id": "hyundai",
        }

    def test_retrieve_empty_slot_passes_none_filters(self):
        adapter = _FakeAdapter([])
        retriever = VectorRetriever(adapter=adapter)
        retriever.retrieve(make_empty_slot(), top_k=3)

        assert adapter.captured["filters"] is None

    def test_retrieve_returns_empty_when_search_empty(self):
        adapter = _FakeAdapter([])
        retriever = VectorRetriever(adapter=adapter)
        results = retriever.retrieve(make_accident_disease_slot(), top_k=8)
        assert results == []

    def test_retrieve_result_count_matches_raw(self):
        raw = [_fake_result(f"c{i}") for i in range(6)]
        adapter = _FakeAdapter(raw)
        retriever = VectorRetriever(adapter=adapter)
        results = retriever.retrieve(make_accident_disease_slot(), top_k=8)
        assert len(results) == 6


# ===========================================================================
# VectorRetriever.health
# ===========================================================================


class TestVectorRetrieverHealth:
    """health() — 어댑터 health 위임."""

    def test_health_returns_true_when_adapter_healthy(self):
        retriever = VectorRetriever(adapter=_FakeAdapter(health_ok=True))
        assert retriever.health() is True

    def test_health_returns_false_when_adapter_unhealthy(self):
        retriever = VectorRetriever(adapter=_FakeAdapter(health_ok=False))
        assert retriever.health() is False
