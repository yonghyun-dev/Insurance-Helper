"""tests.rag.test_indexer

app/rag/indexer.py 단위 테스트.

테스트 대상:
    - build_graph()/sync_document(): GraphDatabase.driver mock → UNWIND 배치 호출 검증 (v1)
    - 통계 dict 형식 검증 (insurers, products, versions, documents, clauses, subclauses, edges_*)
    - rebuild=True 시 DETACH DELETE 쿼리 실행 검증
    - article 청크 → Clause, 그 외 → SubClause 분류
    - HAS_SUBCLAUSE 엣지 — parent_chunk_id 기반

mock 정책:
    - neo4j.GraphDatabase.driver → FakeDriver (실 Memgraph 호출 없음)
    - app.domains.rag.indexer.session_scope → in-memory SQLite session
    - 기존 conftest.py 의 session 픽스처 활용
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from app.domains.chunks.models import ClauseChunk
from app.domains.documents.models import Document, Insurer, Product, ProductVersion

# ---------------------------------------------------------------------------
# Neo4j driver mock
# ---------------------------------------------------------------------------


class RecordingSession:
    """neo.run 호출 기록 — 실행 인자 캡처."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **kwargs) -> None:
        self.calls.append((cypher, kwargs))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def cypher_texts(self) -> list[str]:
        return [c for c, _ in self.calls]

    def has_cypher_containing(self, keyword: str) -> bool:
        return any(keyword in c for c in self.cypher_texts())


class FakeDriver:
    """neo4j.Driver stub."""

    def __init__(self):
        self.neo_session = RecordingSession()
        self.closed = False

    def session(self):
        return self.neo_session

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# SQLite 데이터 헬퍼
# ---------------------------------------------------------------------------


def _add_insurer(session, id_="ins1", name="한화손해보험") -> Insurer:
    ins = Insurer(id=id_, name=name, homepage_url="https://example.com")
    session.add(ins)
    session.flush()
    return ins


def _add_product(session, insurer_id="ins1", product_id="prod1", area="auto") -> Product:
    prod = Product(id=product_id, insurer_id=insurer_id, area=area, name="개인용자동차보험")
    session.add(prod)
    session.flush()
    return prod


def _add_version(session, product_id="prod1") -> ProductVersion:
    ver = ProductVersion(
        product_id=product_id,
        valid_from=date(2026, 1, 1),
        valid_to=None,
        version_label="2026-01-01_present",
        is_active=True,
    )
    session.add(ver)
    session.flush()
    return ver


def _add_document(session, version_id: int) -> Document:
    doc = Document(
        version_id=version_id,
        doc_type="terms",
        file_path="/fake/path.pdf",
        file_sha256="a" * 64,
        page_count=10,
        parser_version="0.1.0",
    )
    session.add(doc)
    session.flush()
    return doc


def _add_chunk(
    session,
    document_id: int,
    chunk_id: str,
    chunk_type: str = "article",
    clause_no: str | None = "제1조",
    parent_chunk_id: str | None = None,
) -> ClauseChunk:
    chunk = ClauseChunk(
        id=chunk_id,
        document_id=document_id,
        parent_chunk_id=parent_chunk_id,
        chunk_type=chunk_type,
        clause_no=clause_no,
        sub_no=None,
        page_start=1,
        page_end=1,
        token_count=100,
        text="약관 조항 본문입니다.",
        summary=None,
    )
    session.add(chunk)
    session.flush()
    return chunk


# ===========================================================================
# build_graph (v1 — UNWIND 배치 + REFERS_TO)
# ===========================================================================


def _wire(monkeypatch, session, fake_driver):
    """build_graph/sync_document 를 mock driver + in-memory SQLite 로 실행할 배선."""
    monkeypatch.setattr(
        "app.domains.rag.indexer.GraphDatabase.driver", lambda *a, **kw: fake_driver
    )

    @contextmanager
    def fake_session_scope():
        yield session

    monkeypatch.setattr("app.domains.rag.indexer.session_scope", fake_session_scope)
    from app.infrastructure.core.config import Settings

    monkeypatch.setattr(
        "app.domains.rag.indexer.get_settings",
        lambda: Settings(graph_uri="bolt://localhost:7687"),
    )


def _seed_basic(session):
    """보험사→상품→버전→문서 + article/annex/table 청크 3개."""
    _add_insurer(session)
    _add_product(session)
    ver = _add_version(session)
    doc = _add_document(session, ver.id)
    _add_chunk(session, doc.id, "c-art", chunk_type="article", clause_no="제3조")
    # 본문이 별표 1 을 참조하는 paragraph
    ch = _add_chunk(session, doc.id, "c-para", chunk_type="paragraph", clause_no="제3조")
    ch.text = "보상내용은 별표 1 을 따릅니다."
    annex = _add_chunk(session, doc.id, "c-annex", chunk_type="annex", clause_no="별표 1")
    annex.text = "별표 1 보장한도표"
    session.flush()
    return doc


class TestBuildGraph:
    def test_stats_and_unwind_batches(self, monkeypatch, session):
        import app.domains.rag.indexer as idx

        _seed_basic(session)
        drv = FakeDriver()
        _wire(monkeypatch, session, drv)
        stats = idx.build_graph()
        assert stats["insurers"] == 1
        assert stats["clauses"] == 1
        assert stats["subclauses"] == 2
        # UNWIND 배치 사용 (per-row MERGE 아님)
        assert drv.neo_session.has_cypher_containing("UNWIND $rows")

    def test_refers_to_edge_extracted(self, monkeypatch, session):
        import app.domains.rag.indexer as idx

        _seed_basic(session)
        drv = FakeDriver()
        _wire(monkeypatch, session, drv)
        stats = idx.build_graph()
        # c-para 본문 "별표 1" 참조 → annex 청크로 REFERS_TO 1건
        assert stats["edges_refers_to"] == 1
        assert drv.neo_session.has_cypher_containing("REFERS_TO")

    def test_annex_self_reference_excluded(self, monkeypatch, session):
        import app.domains.rag.indexer as idx

        _add_insurer(session); _add_product(session)
        ver = _add_version(session); doc = _add_document(session, ver.id)
        annex = _add_chunk(session, doc.id, "a1", chunk_type="annex", clause_no="별표 1")
        annex.text = "별표 1 자기 자신 언급"
        session.flush()
        drv = FakeDriver()
        _wire(monkeypatch, session, drv)
        stats = idx.build_graph()
        assert stats.get("edges_refers_to", 0) == 0

    def test_rebuild_true_emits_detach_delete(self, monkeypatch, session):
        import app.domains.rag.indexer as idx

        _seed_basic(session)
        drv = FakeDriver()
        _wire(monkeypatch, session, drv)
        idx.build_graph(rebuild=True)
        assert drv.neo_session.has_cypher_containing("DETACH DELETE")

    def test_rebuild_false_no_global_delete(self, monkeypatch, session):
        import app.domains.rag.indexer as idx

        _seed_basic(session)
        drv = FakeDriver()
        _wire(monkeypatch, session, drv)
        idx.build_graph(rebuild=False)
        assert not any(
            c.strip().startswith("MATCH (n) DETACH DELETE") for c in drv.neo_session.cypher_texts()
        )

    def test_clause_title_property_set(self, monkeypatch, session):
        import app.domains.rag.indexer as idx

        _seed_basic(session)
        drv = FakeDriver()
        _wire(monkeypatch, session, drv)
        idx.build_graph()
        clause_calls = [
            kw for c, kw in drv.neo_session.calls
            if "MERGE (n:Clause" in c and kw.get("rows")
        ]
        assert clause_calls and "title" in clause_calls[0]["rows"][0]

    def test_chunk_nodes_carry_scope_props(self, monkeypatch, session):
        import app.domains.rag.indexer as idx

        _seed_basic(session)
        drv = FakeDriver()
        _wire(monkeypatch, session, drv)
        idx.build_graph()
        sub_calls = [
            kw for c, kw in drv.neo_session.calls
            if "MERGE (n:SubClause" in c and kw.get("rows")
        ]
        row = sub_calls[0]["rows"][0]
        assert row["insurer_id"] == "ins1" and row["document_id"] is not None
        assert "clause_no" in row


class TestSyncDocument:
    def test_deletes_then_reloads_document_chunks(self, monkeypatch, session):
        import app.domains.rag.indexer as idx

        doc = _seed_basic(session)
        drv = FakeDriver()
        _wire(monkeypatch, session, drv)
        stats = idx.sync_document(doc.id)
        texts = drv.neo_session.cypher_texts()
        # 문서 스코프 삭제 → 재적재 순서
        del_idx = next(i for i, t in enumerate(texts) if "n.document_id = $did" in t and "DETACH DELETE" in t)
        load_idx = next(i for i, t in enumerate(texts) if "MERGE (n:Clause" in t)
        assert del_idx < load_idx
        assert stats["clauses"] == 1

    def test_driver_closed(self, monkeypatch, session):
        import app.domains.rag.indexer as idx

        doc = _seed_basic(session)
        drv = FakeDriver()
        _wire(monkeypatch, session, drv)
        idx.sync_document(doc.id)
        assert drv.closed is True
