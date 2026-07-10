"""app.domains.rag.neurosymbolic

뉴로심볼릭 retriever — 뉴럴(벡터·의미)과 심볼릭(그래프·구조)을 **항상 함께** 실행해
RRF(Reciprocal Rank Fusion)로 융합한다 (Sprint 32 T2, rag_mode 토글 폐지).

    뉴럴  : 임베딩 top-N (의미 유사)                      — 기존 VectorRetriever
    심볼릭: ① 조항 제목 키워드 후보 ② 뉴럴 히트의 구조 이웃  — SymbolicGraphChannel
    융합  : RRF(k=60). 두 채널 모두에 잡힌 청크가 자연 부스트.
    강등  : 그래프 다운/비활성(rag_graph_enabled=false) → 뉴럴 단독 (graceful)

심볼릭 후보는 벡터 점수가 없으므로 SQLite 에서 본문·메타를 하이드레이트한다
(SQLite = source of truth. 메타 키는 Chroma upsert 메타와 동일 계약).
"""

from __future__ import annotations

from typing import Any

from app.domains.chunks.models import ClauseChunk
from app.domains.documents.models import Document, Insurer, Product, ProductVersion
from app.domains.rag._slots import slots_to_filters, slots_to_query
from app.domains.rag.graph import SymbolicGraphChannel, get_symbolic_channel
from app.domains.rag.protocols import RetrievalResult
from app.domains.rag.vector import VectorRetriever
from app.domains.sessions.schemas import SlotState
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.database import session_scope
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

_RRF_K = 60  # RRF 표준 상수 — 순위 융합 완만화


def _rrf(rankings: list[list[str]], weights: list[float] | None = None) -> dict[str, float]:
    """청크ID 순위 목록들 → 가중 RRF 점수 맵.

    weights[i] 는 rankings[i] 의 기여 가중. 골든셋 실측(2026-07-09)에서 동가중(1.0) 융합은
    심볼릭 노이즈가 뉴럴 정답을 top-3 에서 밀어내 MRR 0.663→0.467 로 악화 —
    뉴럴 지배(1.0) + 심볼릭 보조(rag_symbolic_weight) 가중으로 해소한다.
    두 채널이 동시에 잡은 청크는 가중 후에도 합산 부스트를 받는다.
    """
    weights = weights or [1.0] * len(rankings)
    scores: dict[str, float] = {}
    for ranking, w in zip(rankings, weights, strict=True):
        for rank, cid in enumerate(ranking, 1):
            scores[cid] = scores.get(cid, 0.0) + w / (_RRF_K + rank)
    return scores


def _hydrate_chunks(chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
    """SQLite 에서 청크 본문+메타 조회 — Chroma 메타 계약과 동일 키."""
    if not chunk_ids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    with session_scope() as sql:  # type: Session
        rows = (
            sql.query(ClauseChunk, Document, ProductVersion, Product, Insurer)
            .join(Document, Document.id == ClauseChunk.document_id)
            .join(ProductVersion, ProductVersion.id == Document.version_id)
            .join(Product, Product.id == ProductVersion.product_id)
            .join(Insurer, Insurer.id == Product.insurer_id)
            .filter(ClauseChunk.id.in_(chunk_ids))
            .all()
        )
        for chunk, doc, ver, prod, ins in rows:
            out[chunk.id] = {
                "id": chunk.id,
                "text": chunk.text,
                "score": None,  # 심볼릭 경로 — 벡터 점수 없음 (RRF 로만 순위화)
                "metadata": {
                    "document_id": doc.id,
                    "doc_type": doc.doc_type,
                    "insurer_id": ins.id,
                    "insurer_name": ins.name,
                    "product_id": prod.id,
                    "product_name": prod.name,
                    "area": prod.area,
                    "version_id": ver.id,
                    "version_label": ver.version_label,
                    "chunk_type": chunk.chunk_type,
                    "clause_no": chunk.clause_no,
                    "sub_no": chunk.sub_no,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                },
                "source": "symbolic",
            }
    return out


class NeuroSymbolicRetriever:
    """뉴럴+심볼릭 융합 retriever — rag.service.retrieve() 의 단일 구현."""

    def __init__(
        self,
        vector: VectorRetriever | None = None,
        symbolic: SymbolicGraphChannel | None = None,
    ) -> None:
        self._vector = vector or VectorRetriever()
        self._symbolic = symbolic

    @property
    def symbolic(self) -> SymbolicGraphChannel:
        if self._symbolic is None:
            self._symbolic = get_symbolic_channel()
        return self._symbolic

    def health(self) -> bool:
        """벡터 backend 기준 (그래프는 부가 채널 — 다운이어도 검색 자체는 가능)."""
        return self._vector.health()

    def retrieve(self, slots: SlotState, top_k: int = 8) -> list[RetrievalResult]:
        query = slots_to_query(slots)
        filters = slots_to_filters(slots)
        insurer_id = (filters or {}).get("insurer_id")
        return self.retrieve_fused(query, insurer_id, filters, top_k)

    def retrieve_freeform(
        self, text: str, top_k: int = 8, insurer_id: str | None = None
    ) -> list[RetrievalResult]:
        """자유 질의(도움 챗봇/일반 QA) — 동일 융합 파이프라인.

        Sprint 35 — insurer_id 가 주어지면(로그인 사용자의 세션 QA) 가입 보험사 약관으로
        스코프해 타 보험사 기준 답변('메리츠화재 약관 기준으로는…' 오귀속)을 막는다.
        미지정(익명/도움 챗봇)은 기존대로 무필터 교차검색.
        """
        filters = {"insurer_id": insurer_id} if insurer_id else None
        return self.retrieve_fused(text, insurer_id, filters, top_k)

    # ------------------------------------------------------------------
    def retrieve_fused(
        self,
        query: str,
        insurer_id: str | None,
        filters: dict[str, Any] | None,
        top_k: int,
    ) -> list[RetrievalResult]:
        settings = get_settings()

        # ① 뉴럴 채널 — 융합 여지를 위해 2×top_k. 상대 점수컷(rag_score_ratio)은
        # 벡터 점수가 있는 뉴럴 리스트에만 융합 전 적용(심볼릭 후보는 RRF 로만 순위화).
        neural = self._vector.adapter.query(query, top_k=top_k * 2, filters=filters)
        ratio = settings.rag_score_ratio
        if ratio > 0 and neural and isinstance(neural[0].get("score"), (int, float)):
            cut = neural[0]["score"] * ratio
            kept = [r for r in neural if (r.get("score") or 0) >= cut]
            neural = kept or neural[:1]
        neural_ids = [r["id"] for r in neural]
        by_id: dict[str, dict[str, Any]] = {r["id"]: {**r, "source": "neural"} for r in neural}

        # ② 심볼릭 채널 (graceful — 비활성/다운 시 뉴럴 단독)
        symbolic_rankings: list[list[str]] = []
        if settings.rag_graph_enabled:
            try:
                cands = self.symbolic.clause_candidates(query, insurer_id, limit=top_k)
                expanded = self.symbolic.expand(neural_ids[:top_k], limit=top_k * 2)
                # 보험사 스코프 밖 확장 차단은 그래프 속성(insurer_id) 기반 — 하이드레이트 후 검증
                symbolic_ids = [c["chunk_id"] for c in cands] + [
                    e["chunk_id"] for e in expanded
                ]
                # 순위 리스트 2개: 제목매칭(점수순), 구조확장(원 히트 순위순)
                if cands:
                    symbolic_rankings.append([c["chunk_id"] for c in cands])
                if expanded:
                    symbolic_rankings.append([e["chunk_id"] for e in expanded])
                missing = [cid for cid in symbolic_ids if cid not in by_id]
                hydrated = _hydrate_chunks(missing)
                # 스코프 검증: insurer 필터가 있으면 타 보험사 청크 제외 (정합 불변식)
                for cid, chunk in hydrated.items():
                    if insurer_id and chunk["metadata"].get("insurer_id") != insurer_id:
                        continue
                    by_id[cid] = {**chunk, "source": "symbolic"}
            except Exception as exc:  # noqa: BLE001 — 심볼릭 실패는 검색 실패가 아니다
                logger.warning("심볼릭 채널 실패 — 뉴럴 단독 강등: %s", exc)

        # ③ 가중 RRF 융합 — 뉴럴(1.0) 지배 + 심볼릭(보조 가중) 순위들
        rankings = ([neural_ids] if neural_ids else []) + symbolic_rankings
        if not rankings:
            return []
        sym_w = settings.rag_symbolic_weight
        weights = ([1.0] if neural_ids else []) + [sym_w] * len(symbolic_rankings)
        fused = _rrf(rankings, weights)
        ordered = [cid for cid in sorted(fused, key=lambda c: -fused[c]) if cid in by_id]

        results: list[RetrievalResult] = []
        for cid in ordered[:top_k]:
            r = by_id[cid]
            results.append(
                {
                    "id": r["id"],
                    "text": r["text"],
                    "score": r.get("score"),
                    "metadata": r.get("metadata", {}),
                    "source": r.get("source", "neural"),
                }
            )
        n_sym = sum(1 for r in results if r["source"] == "symbolic")
        if n_sym:
            logger.info("뉴로심볼릭 융합: top%d 중 심볼릭 %d건 편입", len(results), n_sym)
        return results
