"""app.domains.rag.indexer

파일 경로: app/rag/indexer.py
목적: SQLite → Neo4j v0 결정론 변환. LLM 0회.

설계 참조: docs/design/graph-schema.md (v0 노드/엣지)

적재 규칙:
    - 노드: Insurer / Product / Version / Document / Clause / SubClause
    - 엣지: SELLS / HAS_VERSION / HAS_DOCUMENT / CONTAINS / HAS_SUBCLAUSE
    - article 청크 → Clause, 그 외 (paragraph/item/table/annex/other) → SubClause
    - 모든 적재는 MERGE (멱등). 재실행 안전.

Neo4j 미설치/미실행 시 ServiceUnavailable. CLI 가 친절한 안내.
"""

from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Neo4j driver helpers
# ---------------------------------------------------------------------------


def _connect() -> Driver:
    settings = get_settings()
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )


_DDL: tuple[str, ...] = (
    "CREATE CONSTRAINT insurer_id_unique IF NOT EXISTS "
    "FOR (n:Insurer) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT product_id_unique IF NOT EXISTS "
    "FOR (n:Product) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT version_id_unique IF NOT EXISTS "
    "FOR (n:Version) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT document_id_unique IF NOT EXISTS "
    "FOR (n:Document) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT clause_chunk_id_unique IF NOT EXISTS "
    "FOR (n:Clause) REQUIRE n.chunk_id IS UNIQUE",
    "CREATE CONSTRAINT subclause_chunk_id_unique IF NOT EXISTS "
    "FOR (n:SubClause) REQUIRE n.chunk_id IS UNIQUE",
    "CREATE INDEX clause_no_index IF NOT EXISTS FOR (n:Clause) ON (n.clause_no)",
    "CREATE INDEX product_area_index IF NOT EXISTS FOR (n:Product) ON (n.area)",
    "CREATE INDEX version_active_index IF NOT EXISTS FOR (n:Version) ON (n.is_active)",
)


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


def build_graph(*, rebuild: bool = False) -> dict[str, int]:
    """SQLite → Neo4j v0 적재. 결정론 변환, LLM 0회.

    Args:
        rebuild: True 면 기존 그래프 전체 삭제 후 재구축. False 면 MERGE 멱등.

    Returns:
        통계 dict — {insurers, products, versions, documents, clauses, subclauses,
                   edges_sells, edges_has_version, edges_has_document, edges_contains,
                   edges_has_subclause}
    """
    driver = _connect()
    stats: dict[str, int] = defaultdict(int)

    try:
        with driver.session() as neo:
            if rebuild:
                logger.info("Neo4j 전체 삭제 (rebuild=True)")
                neo.run("MATCH (n) DETACH DELETE n")

            # 1) DDL — 제약/인덱스
            for stmt in _DDL:
                neo.run(stmt)

            # 2) SQLite 에서 데이터 load
            with session_scope() as sql:
                _load_insurers(sql, neo, stats)
                _load_products(sql, neo, stats)
                _load_versions(sql, neo, stats)
                _load_documents(sql, neo, stats)
                _load_chunks(sql, neo, stats)
    finally:
        driver.close()

    logger.info("graph-build 완료: %s", dict(stats))
    return dict(stats)


# ---------------------------------------------------------------------------
# 내부 — 테이블별 적재
# ---------------------------------------------------------------------------


def _load_insurers(sql: Session, neo: Any, stats: dict[str, int]) -> None:
    rows = sql.query(Insurer).all()
    for row in rows:
        neo.run(
            "MERGE (n:Insurer {id: $id}) "
            "SET n.name = $name, n.homepage_url = $homepage_url",
            id=row.id,
            name=row.name,
            homepage_url=row.homepage_url,
        )
        stats["insurers"] += 1


def _load_products(sql: Session, neo: Any, stats: dict[str, int]) -> None:
    rows = sql.query(Product).all()
    for row in rows:
        neo.run(
            "MERGE (n:Product {id: $id}) "
            "SET n.name = $name, n.area = $area",
            id=row.id,
            name=row.name,
            area=row.area,
        )
        # 엣지 (Insurer)-[:SELLS]->(Product)
        neo.run(
            "MATCH (i:Insurer {id: $insurer_id}), (p:Product {id: $product_id}) "
            "MERGE (i)-[:SELLS]->(p)",
            insurer_id=row.insurer_id,
            product_id=row.id,
        )
        stats["products"] += 1
        stats["edges_sells"] += 1


def _load_versions(sql: Session, neo: Any, stats: dict[str, int]) -> None:
    rows = sql.query(ProductVersion).all()
    for row in rows:
        neo.run(
            "MERGE (n:Version {id: $id}) "
            "SET n.version_label = $label, "
            "    n.valid_from = date($valid_from), "
            "    n.valid_to = CASE WHEN $valid_to IS NULL THEN null ELSE date($valid_to) END, "
            "    n.is_active = $is_active",
            id=row.id,
            label=row.version_label,
            valid_from=row.valid_from.isoformat() if row.valid_from else None,
            valid_to=row.valid_to.isoformat() if row.valid_to else None,
            is_active=bool(row.is_active),
        )
        neo.run(
            "MATCH (p:Product {id: $product_id}), (v:Version {id: $version_id}) "
            "MERGE (p)-[:HAS_VERSION]->(v)",
            product_id=row.product_id,
            version_id=row.id,
        )
        stats["versions"] += 1
        stats["edges_has_version"] += 1


def _load_documents(sql: Session, neo: Any, stats: dict[str, int]) -> None:
    rows = sql.query(Document).all()
    for row in rows:
        neo.run(
            "MERGE (n:Document {id: $id}) "
            "SET n.doc_type = $doc_type, n.file_path = $file_path, n.page_count = $page_count",
            id=row.id,
            doc_type=row.doc_type,
            file_path=row.file_path,
            page_count=row.page_count,
        )
        neo.run(
            "MATCH (v:Version {id: $version_id}), (d:Document {id: $document_id}) "
            "MERGE (v)-[:HAS_DOCUMENT]->(d)",
            version_id=row.version_id,
            document_id=row.id,
        )
        stats["documents"] += 1
        stats["edges_has_document"] += 1


def _load_chunks(sql: Session, neo: Any, stats: dict[str, int]) -> None:
    """Clause (article) + SubClause (그 외) 분리 적재.

    other 청크는 SubClause 의 catch-all 로 분류 (graph-schema.md § 2.6 CRIT-1 보정).
    """
    chunks = sql.query(ClauseChunk).all()

    # 1) 노드 적재 (article → Clause, 나머지 → SubClause)
    for c in chunks:
        if c.chunk_type == "article":
            neo.run(
                "MERGE (n:Clause {chunk_id: $chunk_id}) "
                "SET n.clause_no = $clause_no, n.text = $text, "
                "    n.page_start = $page_start, n.page_end = $page_end, "
                "    n.token_count = $token_count, n.summary = $summary",
                chunk_id=c.id,
                clause_no=c.clause_no,
                text=c.text,
                page_start=c.page_start,
                page_end=c.page_end,
                token_count=c.token_count,
                summary=c.summary,
            )
            stats["clauses"] += 1
        else:
            neo.run(
                "MERGE (n:SubClause {chunk_id: $chunk_id}) "
                "SET n.sub_no = $sub_no, n.text = $text, "
                "    n.page_start = $page_start, n.chunk_type = $chunk_type",
                chunk_id=c.id,
                sub_no=c.sub_no,
                text=c.text,
                page_start=c.page_start,
                chunk_type=c.chunk_type,
            )
            stats["subclauses"] += 1

    # 2) Document -[:CONTAINS]-> Clause 엣지 (article 만)
    for c in chunks:
        if c.chunk_type == "article":
            neo.run(
                "MATCH (d:Document {id: $document_id}), (n:Clause {chunk_id: $chunk_id}) "
                "MERGE (d)-[:CONTAINS]->(n)",
                document_id=c.document_id,
                chunk_id=c.id,
            )
            stats["edges_contains"] += 1

    # 3) HAS_SUBCLAUSE 엣지 (parent_chunk_id 기반 — Clause|SubClause → SubClause)
    chunks_by_id = {c.id: c for c in chunks}
    for c in chunks:
        if c.parent_chunk_id is None or c.chunk_type == "article":
            continue
        parent = chunks_by_id.get(c.parent_chunk_id)
        if parent is None:
            logger.warning("parent_chunk_id 미존재: chunk=%s parent=%s", c.id, c.parent_chunk_id)
            continue
        parent_label = "Clause" if parent.chunk_type == "article" else "SubClause"
        # I-1 보정 — Cypher 레이블은 driver 가 파라미터화 못 함. f-string 사용 불가피.
        # injection 의심 패턴으로 반복 지적될 여지 차단 위해 allowlist 명시.
        assert parent_label in {"Clause", "SubClause"}, (
            f"허용되지 않는 Neo4j 레이블: {parent_label}"
        )
        neo.run(
            f"MATCH (p:{parent_label} {{chunk_id: $parent_id}}), "
            f"      (child:SubClause {{chunk_id: $child_id}}) "
            "MERGE (p)-[:HAS_SUBCLAUSE]->(child)",
            parent_id=c.parent_chunk_id,
            child_id=c.id,
        )
        stats["edges_has_subclause"] += 1
