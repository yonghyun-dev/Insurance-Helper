"""admin 그래프 API — node-link 변환·BFS 스코프·경로·게이팅 (Sprint 38 준비)."""

from __future__ import annotations

import pytest
from app.domains.admin import service


def _fake_graph():
    """service.fetch_graph 반환 형태의 소형 픽스처 (2보험사)."""
    nodes = [
        {"id": "insurer:samsung", "node_type": "Insurer", "label": "삼성화재"},
        {"id": "product:samsung_silson", "node_type": "Product", "label": "실손"},
        {"id": "document:1", "node_type": "Document", "label": "terms #1"},
        {"id": "clause:c1", "node_type": "Clause", "label": "제3조 (보상)"},
        {"id": "clause:c2", "node_type": "SubClause", "label": "별표 1"},
        {"id": "insurer:lotte", "node_type": "Insurer", "label": "롯데손해보험"},
        {"id": "clause:c9", "node_type": "Clause", "label": "제1조"},
    ]
    edges = [
        {"edge_id": "e0", "source": "insurer:samsung", "target": "product:samsung_silson", "relation_type": "SELLS"},
        {"edge_id": "e1", "source": "product:samsung_silson", "target": "document:1", "relation_type": "HAS_DOCUMENT"},
        {"edge_id": "e2", "source": "document:1", "target": "clause:c1", "relation_type": "CONTAINS"},
        {"edge_id": "e3", "source": "clause:c1", "target": "clause:c2", "relation_type": "REFERS_TO"},
        {"edge_id": "e4", "source": "insurer:lotte", "target": "clause:c9", "relation_type": "CONTAINS"},
    ]
    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


class TestShortestPath:
    def test_direct_path(self):
        p = service.shortest_path(_fake_graph(), "insurer:samsung", "clause:c2")
        assert p is not None
        assert p["hop_count"] == 4
        assert p["nodes"][0] == "insurer:samsung"
        assert p["nodes"][-1] == "clause:c2"
        assert p["edges"] == ["e0", "e1", "e2", "e3"]

    def test_undirected_traversal(self):
        # REFERS_TO 방향 반대로도 도달 (무방향 BFS)
        p = service.shortest_path(_fake_graph(), "clause:c2", "insurer:samsung")
        assert p is not None and p["hop_count"] == 4

    def test_disconnected_returns_none(self):
        assert service.shortest_path(_fake_graph(), "insurer:samsung", "clause:c9") is None

    def test_unknown_node_returns_none(self):
        assert service.shortest_path(_fake_graph(), "insurer:samsung", "clause:nope") is None


class TestBfsScope:
    def test_reachable_cuts_other_insurer(self):
        g = _fake_graph()
        reach = service._bfs_reachable("insurer:samsung", g["edges"])
        assert "clause:c2" in reach
        assert "insurer:lotte" not in reach
        assert "clause:c9" not in reach


class TestNodeIdAndLabel:
    def test_node_id_prefixes(self):
        assert service._node_id("Insurer", {"id": "samsung"}) == "insurer:samsung"
        assert service._node_id("Clause", {"chunk_id": "abc"}) == "clause:abc"

    def test_display_label_clause_title(self):
        assert service._display_label("Clause", {"title": "제3조 (보상)", "clause_no": "제3조"}) == "제3조 (보상)"
        assert service._display_label("Insurer", {"id": "samsung", "name": "삼성화재"}) == "삼성화재"


class TestRouterGating:
    """production 에선 미인증 404, dev 에선 개방 (PM-43 P6)."""

    @pytest.fixture()
    def client(self, monkeypatch):
        from app.main import app
        from fastapi.testclient import TestClient

        # 그래프 스토어 무관 테스트 — fetch_graph 를 픽스처로 대체
        monkeypatch.setattr(
            "app.domains.admin.router.service.fetch_graph",
            lambda insurer_id=None, scope=None: _fake_graph(),
        )
        return TestClient(app)

    def test_dev_open(self, client):
        r = client.get("/api/v1/admin/graph")
        assert r.status_code == 200
        assert r.json()["node_count"] == 7

    def test_production_blocked_without_auth(self, client, monkeypatch):
        from app.infrastructure.core.config import get_settings

        monkeypatch.setenv("APP_ENV", "production")
        get_settings.cache_clear()
        try:
            assert client.get("/api/v1/admin/graph").status_code == 404
        finally:
            get_settings.cache_clear()

    def test_flag_disabled_blocked_even_in_dev(self, client, monkeypatch):
        # 운영 compose 는 ADMIN_GRAPH_ENABLED=false — 인증·환경 무관 404 은닉
        from app.infrastructure.core.config import get_settings

        monkeypatch.setenv("ADMIN_GRAPH_ENABLED", "false")
        get_settings.cache_clear()
        try:
            assert client.get("/api/v1/admin/graph").status_code == 404
            assert client.get("/api/v1/admin/graph/tree").status_code == 404
        finally:
            get_settings.cache_clear()

    def test_path_endpoint(self, client):
        r = client.get(
            "/api/v1/admin/graph/path",
            params={"source": "insurer:samsung", "target": "clause:c2"},
        )
        assert r.status_code == 200
        assert r.json()["hop_count"] == 4

    def test_path_not_found_404(self, client):
        r = client.get(
            "/api/v1/admin/graph/path",
            params={"source": "insurer:samsung", "target": "clause:c9"},
        )
        assert r.status_code == 404

    def test_graph_store_down_503(self, client, monkeypatch):
        def boom(insurer_id=None, scope=None):
            raise RuntimeError("down")

        monkeypatch.setattr("app.domains.admin.router.service.fetch_graph", boom)
        assert client.get("/api/v1/admin/graph").status_code == 503


class TestNodeIdNotOverwritten:
    """실측 버그 회귀 방지 — 원시 props 의 'id' 가 프리픽스 id 를 덮으면 안 됨."""

    def test_prefixed_id_survives_props_spread(self, monkeypatch):
        fake_nodes = [{"label": "Insurer", "props": {"id": "samsung", "name": "삼성화재"}}]

        class _Sess:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def run(self, q, **kw):
                class _R:
                    def data(_):
                        return fake_nodes if "MATCH (n)" in q and "-[r]->" not in q else []
                return _R()

        class _Drv:
            def session(self): return _Sess()
            def close(self): pass

        monkeypatch.setattr(
            "app.domains.admin.service.GraphDatabase",
            type("GD", (), {"driver": staticmethod(lambda *a, **k: _Drv())}),
        )
        monkeypatch.setitem(service._cache, "graph", None)  # TTL 캐시 격리
        g = service.fetch_graph()
        assert g["nodes"][0]["id"] == "insurer:samsung"
        assert g["nodes"][0]["name"] == "삼성화재"


class TestDocumentScope:
    """PM — 문서 단위 스코프: 하향 BFS 라 형제 문서·상위 계층으로 번지지 않아야 함."""

    def _two_doc_graph(self):
        nodes = [
            {"id": "insurer:samsung", "node_type": "Insurer", "label": "삼성화재"},
            {"id": "product:p", "node_type": "Product", "label": "실손"},
            {"id": "version:1", "node_type": "Version", "label": "v1"},
            {"id": "document:1", "node_type": "Document", "label": "terms #1"},
            {"id": "document:2", "node_type": "Document", "label": "summary #2"},
            {"id": "clause:a", "node_type": "Clause", "label": "제3조"},
            {"id": "clause:b", "node_type": "Clause", "label": "제1조"},
        ]
        edges = [
            {"edge_id": "e0", "source": "insurer:samsung", "target": "product:p", "relation_type": "SELLS"},
            {"edge_id": "e1", "source": "product:p", "target": "version:1", "relation_type": "HAS_VERSION"},
            {"edge_id": "e2", "source": "version:1", "target": "document:1", "relation_type": "HAS_DOCUMENT"},
            {"edge_id": "e3", "source": "version:1", "target": "document:2", "relation_type": "HAS_DOCUMENT"},
            {"edge_id": "e4", "source": "document:1", "target": "clause:a", "relation_type": "CONTAINS"},
            {"edge_id": "e5", "source": "document:2", "target": "clause:b", "relation_type": "CONTAINS"},
        ]
        return nodes, edges

    def test_document_scope_excludes_sibling_and_ancestors(self):
        _, edges = self._two_doc_graph()
        reach = service._bfs_reachable("document:1", edges)
        assert reach == {"document:1", "clause:a"}  # 형제 문서·상위 미포함

    def test_insurer_scope_still_full_subtree(self):
        _, edges = self._two_doc_graph()
        reach = service._bfs_reachable("insurer:samsung", edges)
        assert "clause:a" in reach and "clause:b" in reach and "document:2" in reach

    def test_fetch_graph_scope_param(self, monkeypatch):
        nodes, edges = self._two_doc_graph()
        full = {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}
        monkeypatch.setattr(service, "_fetch_full_graph", lambda: full)
        g = service.fetch_graph(scope="document:1")
        assert {n["id"] for n in g["nodes"]} == {"document:1", "clause:a"}
        # scope 가 insurer_id 보다 우선
        g2 = service.fetch_graph(insurer_id="samsung", scope="document:2")
        assert {n["id"] for n in g2["nodes"]} == {"document:2", "clause:b"}

    def test_list_scopes_tree(self, monkeypatch):
        nodes, edges = self._two_doc_graph()
        full = {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}
        monkeypatch.setattr(service, "_fetch_full_graph", lambda: full)
        scopes = service.list_scopes()
        assert len(scopes) == 1
        assert scopes[0]["insurer_id"] == "samsung"
        docs = scopes[0]["documents"]
        assert [d["node_id"] for d in docs] == ["document:1", "document:2"]
        assert docs[0]["clause_count"] == 1


class TestGraphSourcePortContract:
    """포트 계약(헥사고날 seam) — 미래 어댑터(연구팀 TDD 트리 JSON)도 이 스펙을 통과해야 함."""

    def _adapter(self, monkeypatch):
        nodes = [
            {"id": "insurer:samsung", "node_type": "Insurer", "label": "삼성화재"},
            {"id": "document:1", "node_type": "Document", "label": "terms #1", "doc_type": "terms"},
            {"id": "clause:a", "node_type": "Clause", "label": "제3조 (보상)"},
        ]
        edges = [
            {"edge_id": "e0", "source": "insurer:samsung", "target": "document:1", "relation_type": "HAS_DOCUMENT"},
            {"edge_id": "e1", "source": "document:1", "target": "clause:a", "relation_type": "CONTAINS"},
        ]
        full = {"nodes": nodes, "edges": edges, "node_count": 3, "edge_count": 2}
        monkeypatch.setattr(service, "_fetch_full_graph", lambda: full)
        return service.get_graph_source()

    def test_satisfies_protocol(self, monkeypatch):
        from app.domains.admin.ports import GraphSourcePort

        assert isinstance(self._adapter(monkeypatch), GraphSourcePort)

    def test_fetch_graph_contract_keys(self, monkeypatch):
        g = self._adapter(monkeypatch).fetch_graph()
        assert set(g) >= {"nodes", "edges", "node_count", "edge_count"}
        assert all({"id", "node_type", "label"} <= set(n) for n in g["nodes"])
        assert all({"edge_id", "source", "target", "relation_type"} <= set(e) for e in g["edges"])

    def test_scope_cuts_downward(self, monkeypatch):
        a = self._adapter(monkeypatch)
        g = a.fetch_graph(scope="document:1")
        assert {n["id"] for n in g["nodes"]} == {"document:1", "clause:a"}

    def test_scopes_tree_shape(self, monkeypatch):
        scopes = self._adapter(monkeypatch).list_scopes()
        assert scopes and {"insurer_id", "node_id", "label", "documents"} <= set(scopes[0])
        doc = scopes[0]["documents"][0]
        assert {"node_id", "label", "doc_type", "clause_count", "clauses"} <= set(doc)

    def test_shortest_path_contract(self, monkeypatch):
        a = self._adapter(monkeypatch)
        g = a.fetch_graph()
        p = a.shortest_path(g, "insurer:samsung", "clause:a")
        assert p is not None and p["hop_count"] == 2
        assert a.shortest_path(g, "clause:a", "clause:none") is None

    def test_node_content_contract(self, monkeypatch):
        a = self._adapter(monkeypatch)
        c = a.node_content("document:1")
        assert c is not None
        assert {"id", "node_type", "label", "meta", "text", "children"} <= set(c)
        assert [ch["id"] for ch in c["children"]] == ["clause:a"]
        assert {"id", "label", "node_type", "preview"} <= set(c["children"][0])
        assert a.node_content("nope:1") is None

class TestDocumentStructure:
    """SQLite 읽기순서 → 도입부/섹션/조/항 복원 (순수 함수 — DB 불필요)."""

    def _rows(self):
        def mk(id, ct, no=None, sub=None, p=1, head=""):
            return {"id": id, "chunk_type": ct, "clause_no": no, "sub_no": sub,
                    "page_start": p, "head": head}
        return [
            mk("t0", "table", p=6, head="| 가이드북 |"),
            mk("a1", "article", no="제1조", head="제1조 (목적) 본문"),
            mk("p1", "paragraph", no="제1조", sub="①", head="제1조 (목적) ① 내용A"),
            mk("p2", "paragraph", no="제1조", sub="②", head="제1조 (목적) ② 내용B"),
            mk("a2", "article", no="제2조", head="제2조 (정의) 본문"),
            mk("a2b", "article", no="제2조", head="제2조 (정의) 이어서"),
            mk("a3", "article", no="제1조", head="제1조 (특약) 본문"),
        ]

    def test_intro_and_section_split_on_number_reset(self):
        intro, sections = service._build_doc_sections(self._rows())
        assert [i["id"] for i in intro] == ["subclause:t0"]
        assert len(sections) == 2
        assert [a["label"] for a in sections[0]] == ["제1조 (목적)", "제2조 (정의)"]
        assert [a["label"] for a in sections[1]] == ["제1조 (특약)"]

    def test_paragraphs_attach_to_current_article(self):
        _, sections = service._build_doc_sections(self._rows())
        assert [s["label"] for s in sections[0][0]["subs"]] == ["제1조 ①", "제1조 ②"]

    def test_split_article_becomes_continuation(self):
        _, sections = service._build_doc_sections(self._rows())
        assert [s["label"] for s in sections[0][1]["subs"]] == ["제2조 (정의) (계속)"]

    def test_sub_label_variants(self):
        assert service._sub_label("제3조", "②", "paragraph", 26) == "제3조 ②"
        assert service._sub_label("제9조", "1.#part-2", "paragraph", 90) == "제9조 1. (계속 2)"
        assert service._sub_label(None, None, "table", 6) == "[표] p.6"
        assert service._sub_label("제3조", "part-1", "paragraph", 30) == "제3조 (계속 1)"
        # 별표: clause_no 에 이미 '별표'가 있으면 태그 중복 금지
        assert service._sub_label("별표 2", None, "annex", 166) == "별표 2 p.166"
        assert service._sub_label(None, None, "annex", 166) == "[별표] p.166"

    def test_preview_strips_duplicate_marker(self):
        # 라벨 '제1조 ①' 과 겹치는 미리보기 선두 마커 '①' 제거
        _, sections = service._build_doc_sections(self._rows())
        assert sections[0][0]["subs"][0]["preview"] == "내용A"
