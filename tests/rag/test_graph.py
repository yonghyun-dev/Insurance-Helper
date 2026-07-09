"""tests.rag.test_graph — SymbolicGraphChannel (결정론 심볼릭 채널) 단위 테스트.

Sprint 32 T2 — 구 GraphCypherQAChain(LLM-Cypher) 테스트를 대체.
FakeDriver 로 실 Memgraph 없이 Cypher 발행·결과 처리 로직을 검증한다.
"""

from __future__ import annotations

from typing import Any

from app.domains.rag.graph import SymbolicGraphChannel, _tokens


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def single(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self, responses: dict[str, list[dict[str, Any]]]):
        # 응답 라우팅: cypher 부분 문자열 → rows
        self._responses = responses
        self.queries: list[str] = []

    def run(self, cypher: str, **params: Any) -> FakeResult:
        self.queries.append(cypher)
        for key, rows in self._responses.items():
            if key in cypher:
                return FakeResult(rows)
        return FakeResult([])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeDriver:
    def __init__(self, responses: dict[str, list[dict[str, Any]]]):
        self._responses = responses
        self.sessions: list[FakeSession] = []

    def session(self):
        s = FakeSession(self._responses)
        self.sessions.append(s)
        return s


class TestTokens:
    def test_extracts_meaningful_tokens(self):
        assert "보상내용" in _tokens("제3조 (보장종목별 보상내용)")

    def test_filters_stopwords_and_short(self):
        toks = _tokens("제3조 관한 사항 A")
        assert "관한" not in toks and "사항" not in toks and "A" not in toks


class TestClauseCandidates:
    def test_scores_by_title_token_in_query(self):
        drv = FakeDriver({
            "MATCH (c:Clause)": [
                {"chunk_id": "c1", "title": "제3조 (보장종목별 보상내용)", "clause_no": "제3조"},
                {"chunk_id": "c2", "title": "제10조 (계약의 갱신)", "clause_no": "제10조"},
            ]
        })
        ch = SymbolicGraphChannel(driver=drv)
        out = ch.clause_candidates("보상내용이 궁금해요", insurer_id="samsung")
        assert [o["chunk_id"] for o in out] == ["c1"]
        assert out[0]["match_score"] >= 1

    def test_insurer_scope_in_cypher(self):
        drv = FakeDriver({"MATCH (c:Clause)": []})
        ch = SymbolicGraphChannel(driver=drv)
        ch.clause_candidates("질의", insurer_id="samsung")
        assert any("c.insurer_id = $iid" in q for q in drv.sessions[0].queries)

    def test_no_scope_when_insurer_none(self):
        drv = FakeDriver({"MATCH (c:Clause)": []})
        ch = SymbolicGraphChannel(driver=drv)
        ch.clause_candidates("질의", insurer_id=None)
        assert all("insurer_id = $iid" not in q for q in drv.sessions[0].queries)


class TestExpand:
    def test_refers_to_before_siblings(self):
        drv = FakeDriver({
            "REFERS_TO": [{"src": "n1", "dst": "annex1"}],
            "sib.document_id": [{"src": "n1", "dst": "sib1"}],
        })
        ch = SymbolicGraphChannel(driver=drv)
        out = ch.expand(["n1"])
        assert [o["chunk_id"] for o in out] == ["annex1", "sib1"]
        assert out[0]["via"] == "refers_to"

    def test_excludes_input_ids_and_dedupes(self):
        drv = FakeDriver({
            "REFERS_TO": [{"src": "n1", "dst": "n1"}, {"src": "n1", "dst": "x"},
                          {"src": "n1", "dst": "x"}],
        })
        ch = SymbolicGraphChannel(driver=drv)
        out = ch.expand(["n1"])
        assert [o["chunk_id"] for o in out] == ["x"]

    def test_empty_input_short_circuits(self):
        drv = FakeDriver({})
        ch = SymbolicGraphChannel(driver=drv)
        assert ch.expand([]) == []
        assert not drv.sessions  # 세션 자체를 안 연다

    def test_limit_respected(self):
        drv = FakeDriver({
            "REFERS_TO": [{"src": "n1", "dst": f"t{i}"} for i in range(30)],
        })
        ch = SymbolicGraphChannel(driver=drv)
        assert len(ch.expand(["n1"], limit=5)) == 5


class TestHealth:
    def test_health_true_on_success(self):
        drv = FakeDriver({"RETURN 1": [{"1": 1}]})
        assert SymbolicGraphChannel(driver=drv).health() is True

    def test_health_false_on_error(self):
        class BoomDriver:
            def session(self):
                raise ConnectionError("down")

        assert SymbolicGraphChannel(driver=BoomDriver()).health() is False
