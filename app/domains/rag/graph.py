"""app.domains.rag.graph

파일 경로: app/rag/graph.py
목적: GraphRetriever — Neo4j + langchain_neo4j.GraphCypherQAChain.

설계 참조:
    - docs/design/graph-schema.md (노드/엣지)
    - docs/design/rag-architecture.md § 6
    - prompts.CYPHER_FEW_SHOT_EXAMPLES (한국어 few-shot)

graceful 동작:
    - Neo4j 다운 / Cypher 실패 시 빈 list 반환 (호출자 service.retrieve 가 vector 폴백)
    - health() 가 connection ping 으로 사전 검사
"""

from __future__ import annotations

from functools import cached_property
from typing import Any

from app.domains.rag._slots import slots_to_question
from app.domains.rag.prompts import CYPHER_FEW_SHOT_EXAMPLES
from app.domains.rag.protocols import RetrievalResult
from app.domains.sessions.schemas import SlotState
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)


class GraphRetriever:
    """Neo4j + GraphCypherQAChain 기반 graph RAG.

    LangChain 의존:
        - langchain_neo4j.Neo4jGraph
        - langchain_neo4j.GraphCypherQAChain
        - langchain_openai.ChatOpenAI

    Lazy initialization (cached_property) — 모듈 import 시점에 Neo4j 연결 시도 안 함.
    실제 retrieve / health 호출 시점에만 연결.
    """

    @cached_property
    def _graph(self) -> Any:
        from langchain_neo4j import Neo4jGraph

        settings = get_settings()
        return Neo4jGraph(
            url=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            enhanced_schema=True,
        )

    @cached_property
    def _chain(self) -> Any:
        from langchain_neo4j import GraphCypherQAChain
        from langchain_openai import ChatOpenAI

        # Sprint 16 1a — 추론 provider 중앙 정책 적용 (Upstage Solar 전용, OpenAI 폴백 없음).
        # langchain_openai 는 base_url 주입으로 Upstage OpenAI 호환 엔드포인트를 흡수한다.
        settings = get_settings()
        llm = ChatOpenAI(
            model=settings.effective_llm_model,
            temperature=0,
            api_key=settings.effective_llm_api_key,
            base_url=settings.effective_llm_base_url or None,
        )
        return GraphCypherQAChain.from_llm(
            llm=llm,
            graph=self._graph,
            verbose=False,
            allow_dangerous_requests=True,
            return_intermediate_steps=True,
            validate_cypher=True,
            top_k=10,
            cypher_prompt=None,  # enhanced_schema=True 가 기본 프롬프트에 schema 주입
        )

    def retrieve(self, slots: SlotState, top_k: int = 8) -> list[RetrievalResult]:
        question = (
            slots_to_question(slots)
            + "\n\n참고 Cypher 예시:\n"
            + CYPHER_FEW_SHOT_EXAMPLES
        )

        try:
            result = self._chain.invoke({"query": question})
        except Exception as exc:
            logger.warning("GraphCypherQAChain 실행 실패: %s", exc)
            return []

        # intermediate_steps = [{"query": cypher}, {"context": rows}]
        steps = result.get("intermediate_steps") or []
        rows = _extract_rows(steps)
        return _rows_to_results(rows, top_k)

    def health(self) -> bool:
        """Neo4j 연결 검사 (간단 ping)."""
        try:
            self._graph.query("RETURN 1 AS ok")
            return True
        except Exception as exc:
            logger.debug("Neo4j health 실패: %s", exc)
            return False


# ---------------------------------------------------------------------------
# helpers — Cypher 결과 → RetrievalResult
# ---------------------------------------------------------------------------


def _extract_rows(steps: list[Any]) -> list[dict[str, Any]]:
    """intermediate_steps 의 context (rows) 만 추출.

    GraphCypherQAChain 의 steps 형식: [{"query": cypher_str}, {"context": rows}]
    rows 는 list[dict] — 각 dict 가 RETURN 절의 컬럼/값.
    """
    for step in reversed(steps):
        if isinstance(step, dict) and "context" in step:
            ctx = step["context"]
            return ctx if isinstance(ctx, list) else []
    return []


def _rows_to_results(rows: list[dict[str, Any]], top_k: int) -> list[RetrievalResult]:
    """Cypher rows → RetrievalResult.

    Cypher 가 `chunk_id` 컬럼을 RETURN 한 경우만 결과로 채택 (vector dedupe 가능).
    텍스트 컬럼은 c.text 또는 s.text (자동 인식 — 가장 긴 string 값).
    """
    results: list[RetrievalResult] = []
    for i, row in enumerate(rows[:top_k]):
        chunk_id = _pick_first(row, ["c.chunk_id", "chunk_id", "s.chunk_id"])
        if not chunk_id:
            continue
        text = _pick_first(row, ["c.text", "s.text", "text"], default="")
        clause_no = _pick_first(row, ["c.clause_no", "clause_no"], default=None)
        sub_no = _pick_first(row, ["s.sub_no", "sub_no"], default=None)
        page = _pick_first(row, ["c.page_start", "s.page_start", "page_start"], default=0)
        results.append(
            {
                "id": str(chunk_id),
                "text": str(text),
                "score": _rank_to_score(i, len(rows)),
                "metadata": {
                    k: v for k, v in {
                        "clause_no": clause_no,
                        "sub_no": sub_no,
                        "page_start": page,
                    }.items() if v is not None
                },
                "source": "graph",
            }
        )
    return results


def _pick_first(row: dict[str, Any], keys: list[str], *, default: Any = None) -> Any:
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return default


def _rank_to_score(rank: int, total: int) -> float:
    """Cypher 결과에는 score 가 없어 rank 기반 가짜 점수 (0.5~0.9 범위)."""
    if total <= 1:
        return 0.8
    return 0.9 - 0.4 * (rank / max(total - 1, 1))
