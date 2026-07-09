"""eval.retrieval_metrics

검색 골든셋(eval/golden/retrieval_v1.json) 평가 — Sprint 32 T1.

지표:
    - hit@k (k=3, 8): 상위 k 안에 정답 청크 존재 비율
    - MRR@8: 첫 정답 순위의 역수 평균
    - nDCG@8: 정답 다건 대비 순위 품질
    - filter_integrity: 결과 전부가 기대 보험사(insurer_id)인 비율 (반드시 1.0)

relevance 판정(결정론): 청크가 정답이려면
    ① metadata.insurer_id == item.insurer_id
    ② metadata.clause_no ∈ expected.clause_no (null 허용 목록에 null 명시 시 None 허용)
    ③ expected.must_contain 의 모든 키워드가 청크 text 에 포함
    ④ (선택) expected.chunk_type 일치

사용:
    .venv/bin/python -m eval.retrieval_metrics            # 전체 실행 + 표 출력
    .venv/bin/python -m eval.retrieval_metrics --validate # 골든셋-코퍼스 정합만 검증
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GOLDEN_PATH = Path(__file__).parent / "golden" / "retrieval_v1.json"

# 회귀 게이트 임계 — 베이스라인 실측(2026-07-09, vector 단독) 기준으로 고정.
# 이 값 미달 = 검색 회귀. Sprint 32 T2 뉴로심볼릭(hit@8 0.867/MRR 0.666) 반영 상향.
THRESHOLDS = {"hit@8": 0.85, "mrr@8": 0.60, "filter_integrity": 1.0}


def load_golden(path: Path = GOLDEN_PATH) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)["items"]


def is_relevant(chunk: dict[str, Any], item: dict[str, Any]) -> bool:
    """검색 결과 청크 1건이 골든 항목의 정답인지 결정론 판정."""
    meta = chunk.get("metadata") or {}
    exp = item["expected"]
    if meta.get("insurer_id") != item["insurer_id"]:
        return False
    clause_ok = meta.get("clause_no") in exp["clause_no"]
    if not clause_ok:
        return False
    text = chunk.get("text") or ""
    if not all(kw in text for kw in exp.get("must_contain", [])):
        return False
    return not (exp.get("chunk_type") and meta.get("chunk_type") != exp["chunk_type"])


@dataclass
class EvalResult:
    per_item: list[dict[str, Any]] = field(default_factory=list)

    def metrics(self) -> dict[str, float]:
        n = len(self.per_item)
        if n == 0:
            return {}
        hit3 = sum(1 for r in self.per_item if r["first_rank"] is not None and r["first_rank"] <= 3) / n
        hit8 = sum(1 for r in self.per_item if r["first_rank"] is not None and r["first_rank"] <= 8) / n
        mrr = sum(1.0 / r["first_rank"] for r in self.per_item if r["first_rank"] is not None) / n
        ndcg = sum(r["ndcg"] for r in self.per_item) / n
        fi = sum(1 for r in self.per_item if r["filter_ok"]) / n
        return {"n": n, "hit@3": round(hit3, 3), "hit@8": round(hit8, 3),
                "mrr@8": round(mrr, 3), "ndcg@8": round(ndcg, 3),
                "filter_integrity": round(fi, 3)}


def _ndcg_at_k(rel_flags: list[bool], k: int = 8) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, r in enumerate(rel_flags[:k]) if r)
    n_rel = sum(rel_flags[:k])
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_rel))
    return dcg / idcg if idcg > 0 else 0.0


def evaluate(retrieve_fn, items: list[dict[str, Any]] | None = None, top_k: int = 8) -> EvalResult:
    """retrieve_fn(item) -> list[chunk dict] 로 골든셋 전체 평가.

    retrieve_fn 은 호출자가 주입 — 프로덕션 retrieve(슬롯 경유)와 동일 경로를 쓰게 해
    '평가용 별도 경로' 왜곡을 차단한다.
    """
    items = items if items is not None else load_golden()
    result = EvalResult()
    for item in items:
        chunks = retrieve_fn(item)[:top_k]
        flags = [is_relevant(c, item) for c in chunks]
        first = next((i + 1 for i, f in enumerate(flags) if f), None)
        filter_ok = all(
            (c.get("metadata") or {}).get("insurer_id") == item["insurer_id"] for c in chunks
        ) if chunks else False
        result.per_item.append({
            "id": item["id"], "first_rank": first, "ndcg": _ndcg_at_k(flags),
            "filter_ok": filter_ok, "returned": len(chunks),
        })
    return result


def default_retrieve_fn(item: dict[str, Any]) -> list[dict[str, Any]]:
    """프로덕션 동일 경로 — rag.service.retrieve(SlotState 경유)."""
    from app.domains.rag import service as rag_service
    from app.domains.sessions.schemas import SlotState

    slots = SlotState(
        area="accident_disease",
        insurer_id=item["insurer_id"],
        diagnosis=item["query"],  # slots_to_query 가 diagnosis 를 질의 본문으로 사용
    )
    return rag_service.retrieve(slots, top_k=8)


def validate_against_corpus(db_path: str = "app.db") -> list[str]:
    """골든셋 각 항목의 정답 청크가 코퍼스에 실제 존재하는지 검증. 실패 id 목록 반환."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    doc_insurer = {
        r["id"]: r["iid"] for r in con.execute(
            "select d.id, p.insurer_id iid from documents d "
            "join product_versions pv on pv.id=d.version_id "
            "join products p on p.id=pv.product_id"
        )
    }
    failures: list[str] = []
    for item in load_golden():
        exp = item["expected"]
        found = False
        for r in con.execute("select document_id, clause_no, chunk_type, text from clause_chunks"):
            if doc_insurer.get(r["document_id"]) != item["insurer_id"]:
                continue
            if r["clause_no"] not in exp["clause_no"]:
                continue
            if exp.get("chunk_type") and r["chunk_type"] != exp["chunk_type"]:
                continue
            if all(kw in (r["text"] or "") for kw in exp.get("must_contain", [])):
                found = True
                break
        if not found:
            failures.append(item["id"])
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="검색 골든셋 평가")
    parser.add_argument("--validate", action="store_true", help="골든셋-코퍼스 정합 검증만")
    args = parser.parse_args()

    if args.validate:
        fails = validate_against_corpus()
        if fails:
            print(f"정합 실패 {len(fails)}건: {fails}")
            raise SystemExit(1)
        print("골든셋-코퍼스 정합 OK (30/30)")
        return

    result = evaluate(default_retrieve_fn)
    m = result.metrics()
    print(json.dumps(m, ensure_ascii=False))
    for r in result.per_item:
        mark = "○" if r["first_rank"] else "✗"
        print(f"  {mark} {r['id']}: rank={r['first_rank']} ndcg={r['ndcg']:.2f} filter={'OK' if r['filter_ok'] else 'FAIL'}")
    bad = [k for k, v in THRESHOLDS.items() if m.get(k, 0) < v]
    if bad:
        print(f"임계 미달: {bad} (기준 {THRESHOLDS})")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
