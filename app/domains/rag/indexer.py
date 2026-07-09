"""app.domains.rag.indexer

SQLite → 그래프(Memgraph) v1 결정론 적재. LLM 0회.

Sprint 32 T2 — 뉴로심볼릭 심볼릭 채널의 그래프 스토어.
    - 노드: Insurer / Product / Version / Document / Clause(article) / SubClause(그 외)
    - 엣지: SELLS / HAS_VERSION / HAS_DOCUMENT / CONTAINS / HAS_SUBCLAUSE / REFERS_TO
    - v1 추가:
        * 모든 청크 노드에 document_id·insurer_id·clause_no 부착 (스코프·형제 확장용)
        * Clause.title — 조항 제목(첫 줄) 키워드 매칭용
        * REFERS_TO — 청크 텍스트의 "별표N/붙임N" 참조를 같은 문서의 annex 청크로 링크
        * UNWIND 배치 적재 (2.5k 청크 기준 수 초)
        * sync_document(document_id) — ingest 문서 단위 멱등 동기화 훅
    - 전부 MERGE (멱등). Memgraph/Neo4j Bolt 겸용 (DDL 은 Memgraph 네이티브 문법).
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from neo4j import Driver, GraphDatabase
from sqlalchemy.orm import Session

from app.domains.chunks.models import ClauseChunk
from app.domains.documents.models import Document, Insurer, Product, ProductVersion
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.database import session_scope
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

_BATCH = 500

# 텍스트 내 별표/붙임 참조 — annex 시작 헤더가 아닌 본문 참조를 폭넓게 잡는다.
_REF_RE = re.compile(r"(별표|붙임|별첨)\s*(\d+)")


def _connect() -> Driver:
    settings = get_settings()
    return GraphDatabase.driver(
        settings.graph_uri,
        auth=(settings.graph_username, settings.graph_password),
    )


# Memgraph 네이티브 DDL — unique 제약 + 조회 인덱스
_DDL: tuple[str, ...] = (
    "CREATE CONSTRAINT ON (n:Insurer) ASSERT n.id IS UNIQUE",
    "CREATE CONSTRAINT ON (n:Product) ASSERT n.id IS UNIQUE",
    "CREATE CONSTRAINT ON (n:Version) ASSERT n.id IS UNIQUE",
    "CREATE CONSTRAINT ON (n:Document) ASSERT n.id IS UNIQUE",
    "CREATE CONSTRAINT ON (n:Clause) ASSERT n.chunk_id IS UNIQUE",
    "CREATE CONSTRAINT ON (n:SubClause) ASSERT n.chunk_id IS UNIQUE",
    "CREATE INDEX ON :Clause(document_id)",
    "CREATE INDEX ON :Clause(insurer_id)",
    "CREATE INDEX ON :Clause(clause_no)",
    "CREATE INDEX ON :SubClause(document_id)",
    "CREATE INDEX ON :SubClause(insurer_id)",
    "CREATE INDEX ON :SubClause(clause_no)",
)


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


def build_graph(*, rebuild: bool = False) -> dict[str, int]:
    """SQLite → 그래프 전체 적재. 결정론 변환, LLM 0회.

    Args:
        rebuild: True 면 기존 그래프 전체 삭제 후 재구축. False 면 MERGE 멱등.

    Returns:
        통계 dict (노드/엣지 종류별 적재 수)
    """
    driver = _connect()
    stats: dict[str, int] = defaultdict(int)
    try:
        with driver.session() as neo:
            if rebuild:
                logger.info("그래프 전체 삭제 (rebuild=True)")
                neo.run("MATCH (n) DETACH DELETE n")
            _apply_ddl(neo)
            with session_scope() as sql:
                doc_ids = [d.id for d in sql.query(Document.id).all()]
                _load_entities(sql, neo, stats)
                for did in doc_ids:
                    _load_document_chunks(sql, neo, did, stats)
    finally:
        driver.close()
    logger.info("graph-build 완료: %s", dict(stats))
    return dict(stats)


def sync_document(document_id: int) -> dict[str, int]:
    """문서 1건의 그래프를 SQLite 와 동기화 (ingest 훅 — 멱등).

    해당 문서의 기존 청크 노드를 지우고 현재 SQLite 상태로 재적재한다.
    상위 엔티티(Insurer/Product/Version/Document)도 MERGE 로 갱신.
    """
    driver = _connect()
    stats: dict[str, int] = defaultdict(int)
    try:
        with driver.session() as neo:
            _apply_ddl(neo)
            neo.run(
                "MATCH (n) WHERE (n:Clause OR n:SubClause) AND n.document_id = $did "
                "DETACH DELETE n",
                did=document_id,
            )
            with session_scope() as sql:
                _load_entities(sql, neo, stats, only_document_id=document_id)
                _load_document_chunks(sql, neo, document_id, stats)
    finally:
        driver.close()
    logger.info("graph sync_document(%s) 완료: %s", document_id, dict(stats))
    return dict(stats)


def graph_counts() -> dict[str, int]:
    """verify 용 — 그래프 노드/엣지 카운트. 접속 실패 시 예외 전파(호출자 판단)."""
    driver = _connect()
    try:
        with driver.session() as neo:
            chunk_nodes = neo.run(
                "MATCH (n) WHERE n:Clause OR n:SubClause RETURN count(n) AS c"
            ).single()["c"]
            refers = neo.run("MATCH ()-[r:REFERS_TO]->() RETURN count(r) AS c").single()["c"]
            docs = neo.run("MATCH (d:Document) RETURN count(d) AS c").single()["c"]
            return {"chunk_nodes": chunk_nodes, "refers_to": refers, "documents": docs}
    finally:
        driver.close()


# ---------------------------------------------------------------------------
# 내부
# ---------------------------------------------------------------------------


def _apply_ddl(neo: Any) -> None:
    for stmt in _DDL:
        try:
            neo.run(stmt)
        except Exception as exc:  # noqa: BLE001 — 이미 존재하는 제약 재생성 등은 무시
            logger.debug("DDL skip (%s): %s", stmt[:40], exc)


def _doc_insurer_map(sql: Session) -> dict[int, str]:
    rows = (
        sql.query(Document.id, Product.insurer_id)
        .join(ProductVersion, ProductVersion.id == Document.version_id)
        .join(Product, Product.id == ProductVersion.product_id)
        .all()
    )
    return {doc_id: insurer_id for doc_id, insurer_id in rows}


def _load_entities(
    sql: Session, neo: Any, stats: dict[str, int], *, only_document_id: int | None = None
) -> None:
    """Insurer/Product/Version/Document 노드 + 구조 엣지 (배치 MERGE)."""
    insurers = [
        {"id": r.id, "name": r.name, "homepage_url": r.homepage_url}
        for r in sql.query(Insurer).all()
    ]
    neo.run(
        "UNWIND $rows AS r MERGE (n:Insurer {id: r.id}) "
        "SET n.name = r.name, n.homepage_url = r.homepage_url",
        rows=insurers,
    )
    stats["insurers"] += len(insurers)

    products = [
        {"id": r.id, "name": r.name, "area": r.area, "insurer_id": r.insurer_id}
        for r in sql.query(Product).all()
    ]
    neo.run(
        "UNWIND $rows AS r MERGE (n:Product {id: r.id}) SET n.name = r.name, n.area = r.area "
        "WITH r MATCH (i:Insurer {id: r.insurer_id}), (p:Product {id: r.id}) "
        "MERGE (i)-[:SELLS]->(p)",
        rows=products,
    )
    stats["products"] += len(products)

    versions = [
        {
            "id": r.id, "label": r.version_label, "product_id": r.product_id,
            "valid_from": r.valid_from.isoformat() if r.valid_from else None,
            "valid_to": r.valid_to.isoformat() if r.valid_to else None,
            "is_active": bool(r.is_active),
        }
        for r in sql.query(ProductVersion).all()
    ]
    neo.run(
        "UNWIND $rows AS r MERGE (n:Version {id: r.id}) "
        "SET n.version_label = r.label, n.is_active = r.is_active, "
        "    n.valid_from = r.valid_from, n.valid_to = r.valid_to "
        "WITH r MATCH (p:Product {id: r.product_id}), (v:Version {id: r.id}) "
        "MERGE (p)-[:HAS_VERSION]->(v)",
        rows=versions,
    )
    stats["versions"] += len(versions)

    q = sql.query(Document)
    if only_document_id is not None:
        q = q.filter(Document.id == only_document_id)
    documents = [
        {
            "id": r.id, "doc_type": r.doc_type, "file_path": r.file_path,
            "page_count": r.page_count, "version_id": r.version_id,
        }
        for r in q.all()
    ]
    neo.run(
        "UNWIND $rows AS r MERGE (n:Document {id: r.id}) "
        "SET n.doc_type = r.doc_type, n.file_path = r.file_path, n.page_count = r.page_count "
        "WITH r MATCH (v:Version {id: r.version_id}), (d:Document {id: r.id}) "
        "MERGE (v)-[:HAS_DOCUMENT]->(d)",
        rows=documents,
    )
    stats["documents"] += len(documents)


def _clause_title(text: str) -> str:
    """조항 제목 — 첫 줄 80자 (키워드 매칭용. 예: '제3조 (보장종목별 보상내용)')."""
    first = (text or "").split("\n", 1)[0]
    return first[:80]


def _load_document_chunks(
    sql: Session, neo: Any, document_id: int, stats: dict[str, int]
) -> None:
    """문서 1건의 청크 노드 + CONTAINS/HAS_SUBCLAUSE/REFERS_TO 엣지 (UNWIND 배치)."""
    insurer_id = _doc_insurer_map(sql).get(document_id)
    chunks = (
        sql.query(ClauseChunk).filter(ClauseChunk.document_id == document_id).all()
    )
    if not chunks:
        return

    clause_rows: list[dict[str, Any]] = []
    sub_rows: list[dict[str, Any]] = []
    for c in chunks:
        base = {
            "chunk_id": c.id, "document_id": c.document_id, "insurer_id": insurer_id,
            "clause_no": c.clause_no, "sub_no": c.sub_no, "chunk_type": c.chunk_type,
            "page_start": c.page_start, "page_end": c.page_end,
        }
        if c.chunk_type == "article":
            clause_rows.append({**base, "title": _clause_title(c.text)})
        else:
            sub_rows.append(base)

    for i in range(0, len(clause_rows), _BATCH):
        neo.run(
            "UNWIND $rows AS r MERGE (n:Clause {chunk_id: r.chunk_id}) "
            "SET n.document_id = r.document_id, n.insurer_id = r.insurer_id, "
            "    n.clause_no = r.clause_no, n.chunk_type = r.chunk_type, "
            "    n.page_start = r.page_start, n.page_end = r.page_end, n.title = r.title "
            "WITH r MATCH (d:Document {id: r.document_id}), (n:Clause {chunk_id: r.chunk_id}) "
            "MERGE (d)-[:CONTAINS]->(n)",
            rows=clause_rows[i : i + _BATCH],
        )
    stats["clauses"] += len(clause_rows)
    stats["edges_contains"] += len(clause_rows)

    for i in range(0, len(sub_rows), _BATCH):
        neo.run(
            "UNWIND $rows AS r MERGE (n:SubClause {chunk_id: r.chunk_id}) "
            "SET n.document_id = r.document_id, n.insurer_id = r.insurer_id, "
            "    n.clause_no = r.clause_no, n.sub_no = r.sub_no, "
            "    n.chunk_type = r.chunk_type, n.page_start = r.page_start "
            "WITH r MATCH (d:Document {id: r.document_id}), (n:SubClause {chunk_id: r.chunk_id}) "
            "MERGE (d)-[:CONTAINS]->(n)",
            rows=sub_rows[i : i + _BATCH],
        )
    stats["subclauses"] += len(sub_rows)
    stats["edges_contains"] += len(sub_rows)

    # HAS_SUBCLAUSE — 같은 문서·같은 clause_no 의 Clause → SubClause (구조 형제 관계)
    neo.run(
        "MATCH (p:Clause {document_id: $did}) "
        "MATCH (s:SubClause {document_id: $did, clause_no: p.clause_no}) "
        "MERGE (p)-[:HAS_SUBCLAUSE]->(s)",
        did=document_id,
    )

    # REFERS_TO — 청크 텍스트의 별표/붙임 참조 → 같은 문서의 annex 청크
    annex_targets: dict[str, list[str]] = defaultdict(list)
    for c in chunks:
        if c.chunk_type == "annex" and c.clause_no:
            annex_targets[c.clause_no].append(c.id)
    ref_rows: list[dict[str, str]] = []
    for c in chunks:
        if c.chunk_type == "annex":
            continue  # annex 자기참조 제외
        for kind, num in set(_REF_RE.findall(c.text or "")):
            label = f"{kind} {num}"
            for target_id in annex_targets.get(label, []):
                ref_rows.append({"src": c.id, "dst": target_id})
    for i in range(0, len(ref_rows), _BATCH):
        neo.run(
            "UNWIND $rows AS r "
            "MATCH (a) WHERE (a:Clause OR a:SubClause) AND a.chunk_id = r.src "
            "MATCH (b) WHERE (b:Clause OR b:SubClause) AND b.chunk_id = r.dst "
            "MERGE (a)-[:REFERS_TO]->(b)",
            rows=ref_rows[i : i + _BATCH],
        )
    stats["edges_refers_to"] += len(ref_rows)
