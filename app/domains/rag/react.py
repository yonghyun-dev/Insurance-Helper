"""app.domains.rag.react

파일 경로: app/rag/react.py
목적: ReActRunner — Think / Act / Observe loop. assessment 모드 정확도 향상.

설계 참조: docs/design/rag-architecture.md § 8 (시퀀스 + 종료 조건)

종료 조건 (우선순위):
    1. 누적 청크의 단일 score > 0.92 — 고신뢰 즉시 종료
    2. 누적 청크의 distinct clause 수 >= 3 — 정보 충분
    3. LLM Think 가 FINISH 액션 선택
    4. iter == max_iter (강제)

Refine 정책 (PoC):
    Slot 기반 검색이라 query refine 이 단순치 않음. 본 v0 은:
        - iter 1: 기본 top_k
        - iter 2+: top_k * 1.5 (다양성 + 신뢰성 보강)
    LLM 기반 query 합성 refine 은 Sprint 5+ 백로그.
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.domains.rag.prompts import REACT_THINK_PROMPT
from app.domains.rag.protocols import RetrievalResult, Retriever
from app.domains.sessions.schemas import SlotState
from app.infrastructure.core.logging import get_logger
from app.infrastructure.llm.client import get_chat_client, get_chat_model

logger = get_logger(__name__)


DEFAULT_MAX_ITER = 5
SCORE_THRESHOLD = 0.92
MIN_DISTINCT_CLAUSES = 3


def _get_openai_client() -> OpenAI:
    """추론 LLM 클라이언트 — 중앙 팩토리(app.infrastructure.llm.client)에 위임.

    제품 추론은 Upstage Solar 전용(provider=upstage 기본), OpenAI 폴백 없음.
    심볼명 유지 — 테스트가 본 함수를 패치한다. 캐시는 팩토리가 담당.
    """
    return get_chat_client()


class ReActRunner:
    """ReAct loop — assessment 검색 정확도 향상.

    각 iter:
        1. retrieve (top_k 또는 확장)
        2. 누적 dedupe
        3. 종료 조건 검사 (score / distinct / LLM Finish / max_iter)
        4. 종료 아니면 다음 iter
    """

    def __init__(
        self,
        retriever: Retriever,
        *,
        max_iter: int = DEFAULT_MAX_ITER,
    ) -> None:
        self._retriever = retriever
        self._max_iter = max_iter

    def run(self, slots: SlotState, top_k: int = 8) -> list[RetrievalResult]:
        accumulated: list[RetrievalResult] = []
        for iteration in range(self._max_iter):
            # Refine 정책 — iter 2+ 부터 top_k 확장
            current_k = top_k if iteration == 0 else int(top_k * 1.5)
            chunks = self._retriever.retrieve(slots, current_k)
            accumulated = _dedupe_by_id(accumulated + list(chunks))

            # 조건 1: 단일 high-score
            if any(c["score"] > SCORE_THRESHOLD for c in accumulated):
                logger.debug("ReAct 종료 (score>%.2f) iter=%d", SCORE_THRESHOLD, iteration)
                break

            # 조건 2: distinct clause 수
            if _distinct_clause_count(accumulated) >= MIN_DISTINCT_CLAUSES:
                logger.debug(
                    "ReAct 종료 (distinct clauses>=%d) iter=%d",
                    MIN_DISTINCT_CLAUSES,
                    iteration,
                )
                break

            # 조건 3: LLM Think — 마지막 iter 직전엔 호출 생략 (어차피 강제 종료)
            if iteration == self._max_iter - 1:
                logger.debug("ReAct 종료 (max_iter=%d 도달)", self._max_iter)
                break

            decision = self._think(slots, accumulated, iteration)
            if decision == "FINISH":
                logger.debug("ReAct 종료 (LLM Finish) iter=%d", iteration)
                break

        return accumulated[:top_k]

    def _think(
        self,
        slots: SlotState,
        accumulated: list[RetrievalResult],
        iteration: int,
    ) -> str:
        """LLM Think — FINISH 또는 REFINE 결정. 실패 시 REFINE 폴백 (안전).

        본 v0 은 refine 의 실효성이 낮으므로 LLM 호출이 적합치 않으면 단순히 다음 iter 진행.
        비용 절감 목적으로 누적 청크 1개 이하일 때만 Think 실행.
        """
        if len(accumulated) == 0:
            # 아무것도 안 잡혔으면 한 번 더 시도 (refine 무의미)
            return "REFINE"

        try:
            client = _get_openai_client()

            chunks_summary = "\n".join(
                f"- [{i}] score={c['score']:.2f} text={c['text'][:80]}..."
                for i, c in enumerate(accumulated[:5])
            )
            prompt = REACT_THINK_PROMPT.format(
                slots=_slot_summary(slots),
                chunks_summary=chunks_summary,
                iter=iteration + 1,
                max_iter=self._max_iter,
            )
            response = client.chat.completions.create(
                model=get_chat_model(),
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            parsed: dict[str, Any] = json.loads(content)
            return str(parsed.get("action", "REFINE")).upper()
        except Exception as exc:
            logger.warning("ReAct Think 실패 → REFINE 폴백: %s", exc)
            return "REFINE"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _dedupe_by_id(items: list[RetrievalResult]) -> list[RetrievalResult]:
    """동일 chunk id 중복 제거. score 높은 것 유지. 순서 보존."""
    by_id: dict[str, RetrievalResult] = {}
    order: list[str] = []
    for item in items:
        key = item["id"]
        existing = by_id.get(key)
        if existing is None:
            by_id[key] = item
            order.append(key)
        elif item["score"] > existing["score"]:
            by_id[key] = item
    return [by_id[k] for k in order]


def _distinct_clause_count(items: list[RetrievalResult]) -> int:
    """metadata.clause_no 기준 distinct 수. clause 가 없는 결과는 chunk_id 로 대체."""
    seen: set[str] = set()
    for item in items:
        clause = item.get("metadata", {}).get("clause_no")
        key = str(clause) if clause else str(item.get("id"))
        seen.add(key)
    return len(seen)


def _slot_summary(slots: SlotState) -> str:
    parts: list[str] = []
    if slots.area:
        parts.append(f"area={slots.area}")
    if slots.insurer:
        parts.append(f"insurer={slots.insurer}")
    if slots.product:
        parts.append(f"product={slots.product}")
    if slots.area == "auto" and slots.incident_type:
        parts.append(f"incident={slots.incident_type}")
    if slots.area == "fire" and slots.loss_type:
        parts.append(f"loss={slots.loss_type}")
    if slots.area == "accident_disease" and slots.diagnosis:
        parts.append(f"diagnosis={slots.diagnosis}")
    return ", ".join(parts) or "(empty)"
