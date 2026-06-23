"""tests.rag.test_indexer

app/rag/indexer.py 단위 테스트.

테스트 대상:
    - build_graph(): neo4j.GraphDatabase.driver mock → neo.run 호출 검증
    - 통계 dict 형식 검증 (insurers, products, versions, documents, clauses, subclauses, edges_*)
    - rebuild=True 시 DETACH DELETE 쿼리 실행 검증
    - article 청크 → Clause, 그 외 → SubClause 분류
    - HAS_SUBCLAUSE 엣지 — parent_chunk_id 기반

mock 정책:
    - neo4j.GraphDatabase.driver → FakeDriver (실 Neo4j 호출 없음)
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
# build_graph
# ===========================================================================


class TestBuildGraph:
    """build_graph() — neo4j.GraphDatabase.driver mock 검증."""

    def _run_build_graph(self, monkeypatch, session, fake_driver, rebuild=False):
        """build_graph 를 mock driver + session 으로 실행."""
        import app.domains.rag.indexer as idx

        # neo4j.GraphDatabase.driver mock
        monkeypatch.setattr("app.domains.rag.indexer.GraphDatabase.driver", lambda *a, **kw: fake_driver)

        # session_scope → in-memory SQLite session 주입
        @contextmanager
        def fake_session_scope():
            yield session

        monkeypatch.setattr("app.domains.rag.indexer.session_scope", fake_session_scope)
        # get_settings — 실 .env 필요 없도록 패치
        from app.infrastructure.core.config import Settings

        monkeypatch.setattr(
            "app.domains.rag.indexer.get_settings",
            lambda: Settings(
                openai_api_key="test-key",
                neo4j_uri="bolt://localhost:7687",
                neo4j_username="neo4j",
                neo4j_password="test",
            ),
        )

        return idx.build_graph(rebuild=rebuild)

    def test_returns_stats_dict_with_all_keys(self, monkeypatch, session):
        """통계 dict 에 모든 키가 존재한다 (데이터 있을 때)."""
        ins = _add_insurer(session)
        prod = _add_product(session, ins.id)
        ver = _add_version(session, prod.id)
        doc = _add_document(session, ver.id)
        _add_chunk(session, doc.id, "art1", chunk_type="article")
        _add_chunk(session, doc.id, "par1", chunk_type="paragraph", clause_no=None, parent_chunk_id="art1")

        fake_driver = FakeDriver()
        stats = self._run_build_graph(monkeypatch, session, fake_driver)

        # 데이터가 있는 경우 해당 키들이 존재한다
        assert stats["insurers"] == 1
        assert stats["products"] == 1
        assert stats["clauses"] == 1
        assert stats["subclauses"] == 1
        assert stats["edges_sells"] == 1

    def test_emits_merge_for_insurer(self, monkeypatch, session):
        """Insurer 가 있으면 MERGE (:Insurer ...) 쿼리 실행."""
        _add_insurer(session, "ins1", "한화손해보험")
        fake_driver = FakeDriver()
        self._run_build_graph(monkeypatch, session, fake_driver)

        assert fake_driver.neo_session.has_cypher_containing("Insurer")

    def test_emits_merge_for_product_and_sells_edge(self, monkeypatch, session):
        """Product 있으면 MERGE Product + MERGE SELLS 엣지."""
        ins = _add_insurer(session)
        _add_product(session, ins.id)
        fake_driver = FakeDriver()
        self._run_build_graph(monkeypatch, session, fake_driver)

        texts = fake_driver.neo_session.cypher_texts()
        assert any("Product" in t for t in texts)
        assert any("SELLS" in t for t in texts)

    def test_insurer_count_in_stats(self, monkeypatch, session):
        """보험사 2개 → stats["insurers"] == 2."""
        _add_insurer(session, "ins1", "한화")
        _add_insurer(session, "ins2", "삼성")
        fake_driver = FakeDriver()
        stats = self._run_build_graph(monkeypatch, session, fake_driver)

        assert stats["insurers"] == 2

    def test_article_chunk_counted_as_clause(self, monkeypatch, session):
        """article 청크 → clauses 카운트 증가."""
        ins = _add_insurer(session)
        prod = _add_product(session, ins.id)
        ver = _add_version(session, prod.id)
        doc = _add_document(session, ver.id)
        _add_chunk(session, doc.id, "chunk_art_1", chunk_type="article")
        _add_chunk(session, doc.id, "chunk_art_2", chunk_type="article", clause_no="제2조")

        fake_driver = FakeDriver()
        stats = self._run_build_graph(monkeypatch, session, fake_driver)

        assert stats["clauses"] == 2
        # subclauses 가 없으면 key 자체가 없으므로 get 으로 처리
        assert stats.get("subclauses", 0) == 0

    def test_non_article_chunk_counted_as_subclause(self, monkeypatch, session):
        """paragraph/item/table → subclauses 카운트."""
        ins = _add_insurer(session)
        prod = _add_product(session, ins.id)
        ver = _add_version(session, prod.id)
        doc = _add_document(session, ver.id)
        _add_chunk(session, doc.id, "art1", chunk_type="article")
        _add_chunk(session, doc.id, "par1", chunk_type="paragraph", clause_no=None, parent_chunk_id="art1")
        _add_chunk(session, doc.id, "item1", chunk_type="item", clause_no=None, parent_chunk_id="par1")

        fake_driver = FakeDriver()
        stats = self._run_build_graph(monkeypatch, session, fake_driver)

        assert stats["clauses"] == 1
        assert stats["subclauses"] == 2

    def test_rebuild_true_emits_detach_delete(self, monkeypatch, session):
        """rebuild=True → DETACH DELETE 쿼리 실행."""
        fake_driver = FakeDriver()
        self._run_build_graph(monkeypatch, session, fake_driver, rebuild=True)

        assert fake_driver.neo_session.has_cypher_containing("DETACH DELETE")

    def test_rebuild_false_does_not_detach_delete(self, monkeypatch, session):
        """rebuild=False → DETACH DELETE 없음."""
        fake_driver = FakeDriver()
        self._run_build_graph(monkeypatch, session, fake_driver, rebuild=False)

        assert not fake_driver.neo_session.has_cypher_containing("DETACH DELETE")

    def test_driver_is_closed_after_build(self, monkeypatch, session):
        """finally 블록에서 driver.close() 호출."""
        fake_driver = FakeDriver()
        self._run_build_graph(monkeypatch, session, fake_driver)

        assert fake_driver.closed is True

    def test_has_subclause_edge_emitted_for_child_chunk(self, monkeypatch, session):
        """parent_chunk_id 있는 non-article → HAS_SUBCLAUSE 엣지."""
        ins = _add_insurer(session)
        prod = _add_product(session, ins.id)
        ver = _add_version(session, prod.id)
        doc = _add_document(session, ver.id)
        _add_chunk(session, doc.id, "art1", chunk_type="article")
        _add_chunk(session, doc.id, "par1", chunk_type="paragraph", clause_no=None, parent_chunk_id="art1")

        fake_driver = FakeDriver()
        stats = self._run_build_graph(monkeypatch, session, fake_driver)

        assert fake_driver.neo_session.has_cypher_containing("HAS_SUBCLAUSE")
        assert stats["edges_has_subclause"] == 1

    def test_empty_db_returns_empty_or_zero_stats(self, monkeypatch, session):
        """DB 비어 있으면 stats 는 빈 dict 이거나 카운트 0."""
        fake_driver = FakeDriver()
        stats = self._run_build_graph(monkeypatch, session, fake_driver)

        # defaultdict → dict 변환 시 값이 없으면 키도 없음
        assert stats.get("insurers", 0) == 0
        assert stats.get("products", 0) == 0
        assert stats.get("clauses", 0) == 0
