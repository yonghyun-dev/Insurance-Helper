"""app.domains.rag.graph

심볼릭 그래프 채널 — 뉴로심볼릭 검색의 결정론 절반 (Sprint 32 T2).

구 GraphCypherQAChain(LLM 이 Cypher 생성) 을 폐기하고 **LLM 0회 결정론 질의**로 재작성:
    - clause_candidates(): 슬롯 스코프(보험사) 안에서 조항 제목 토큰 ↔ 질의 키워드 매칭
    - expand(): 뉴럴(벡터) 히트 청크의 구조 이웃 — 같은 조의 형제 청크(HAS_SUBCLAUSE),
      본문이 참조하는 별표/붙임(REFERS_TO) — 을 후보로 확장
    - health(): Bolt 접속 가능 여부 (다운 시 뉴로심볼릭 retriever 가 뉴럴 단독으로 graceful)

심볼릭 채널에 LLM 을 넣지 않는 것이 개념 정합(구조 지식은 결정론)이며 환각이 0 이다.
"""

from __future__ import annotations

import re
from typing import Any

from neo4j import Driver, GraphDatabase

from app.infrastructure.core.config import get_settings
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

# 조항 제목에서 의미 토큰 추출: "제3조 (보장종목별 보상내용)" → {보장종목별, 보상내용}
_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_TITLE_STOPWORDS = {
    "제", "조", "관한", "관련", "경우", "사항", "내용", "기타", "등의", "대한", "위한",
}


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text or "") if t not in _TITLE_STOPWORDS}


class SymbolicGraphChannel:
    """Memgraph(Bolt) 기반 결정론 구조 검색 채널."""

    def __init__(self, driver: Driver | None = None) -> None:
        self._driver = driver

    @property
    def driver(self) -> Driver:
        if self._driver is None:
            settings = get_settings()
            self._driver = GraphDatabase.driver(
                settings.graph_uri,
                auth=(settings.graph_username, settings.graph_password),
            )
        return self._driver

    def health(self) -> bool:
        try:
            with self.driver.session() as s:
                s.run("RETURN 1").single()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("그래프 스토어 health 실패: %s", exc)
            return False

    def clause_candidates(
        self, query: str, insurer_id: str | None, limit: int = 12
    ) -> list[dict[str, Any]]:
        """질의 키워드 ↔ 조항 제목 토큰 매칭 후보 (결정론).

        Returns:
            [{chunk_id, match_score, clause_no, title}] — match_score 내림차순.
            제목 토큰 중 질의에 등장한 개수(완전 포함 기준)가 score.
        """
        cypher = (
            "MATCH (c:Clause) "
            + ("WHERE c.insurer_id = $iid " if insurer_id else "")
            + "RETURN c.chunk_id AS chunk_id, c.title AS title, c.clause_no AS clause_no"
        )
        query_text = query or ""
        scored: list[dict[str, Any]] = []
        with self.driver.session() as s:
            for rec in s.run(cypher, iid=insurer_id):
                title_tokens = _tokens(rec["title"] or "")
                if not title_tokens:
                    continue
                score = sum(1 for t in title_tokens if t in query_text)
                if score > 0:
                    scored.append(
                        {
                            "chunk_id": rec["chunk_id"],
                            "match_score": score,
                            "clause_no": rec["clause_no"],
                            "title": rec["title"],
                        }
                    )
        scored.sort(key=lambda r: -r["match_score"])
        return scored[:limit]

    def expand(self, chunk_ids: list[str], limit: int = 16) -> list[dict[str, Any]]:
        """뉴럴 히트의 구조 이웃 확장 (결정론).

        - REFERS_TO: 히트 본문이 참조하는 별표/붙임 청크 (예: 제3조 → 별표2 비급여대상)
        - HAS_SUBCLAUSE 형제: 같은 문서·같은 조의 다른 청크 (항이 잘려 검색된 경우 문맥 보완)

        Returns:
            [{chunk_id, via, src_rank}] — 입력 순위(src_rank) 오름차순, 입력 자신 제외.
        """
        if not chunk_ids:
            return []
        out: list[dict[str, Any]] = []
        seen: set[str] = set(chunk_ids)
        rank_of = {cid: i for i, cid in enumerate(chunk_ids)}
        with self.driver.session() as s:
            # REFERS_TO 를 형제보다 먼저 (별표/붙임은 내용 자체가 답인 경우가 많음)
            for kind, cypher in (
                (
                    "refers_to",
                    "MATCH (n)-[:REFERS_TO]->(t) "
                    "WHERE (n:Clause OR n:SubClause) AND n.chunk_id IN $ids "
                    "RETURN n.chunk_id AS src, t.chunk_id AS dst",
                ),
                (
                    "sibling",
                    "MATCH (n) WHERE (n:Clause OR n:SubClause) AND n.chunk_id IN $ids "
                    "MATCH (sib) WHERE (sib:Clause OR sib:SubClause) "
                    "AND sib.document_id = n.document_id AND sib.clause_no = n.clause_no "
                    "AND sib.chunk_id <> n.chunk_id "
                    "RETURN n.chunk_id AS src, sib.chunk_id AS dst",
                ),
            ):
                rows = sorted(
                    s.run(cypher, ids=chunk_ids),
                    key=lambda r: rank_of.get(r["src"], 999),
                )
                for rec in rows:
                    dst = rec["dst"]
                    if dst in seen:
                        continue
                    seen.add(dst)
                    out.append(
                        {"chunk_id": dst, "via": kind, "src_rank": rank_of.get(rec["src"], 999)}
                    )
                    if len(out) >= limit:
                        return out
        return out


_singleton: SymbolicGraphChannel | None = None


def get_symbolic_channel() -> SymbolicGraphChannel:
    global _singleton  # noqa: PLW0603 — 모듈 싱글턴 (드라이버 재사용)
    if _singleton is None:
        _singleton = SymbolicGraphChannel()
    return _singleton
