"""E2E 정량 평가 러너 (Sprint 36) — 실손 21문항 × (결정론 채점 + Bedrock judge).

실행:
    .venv/bin/python -m eval.e2e_judge.runner            # 전량 (결정론 + judge)
    .venv/bin/python -m eval.e2e_judge.runner --no-judge  # 결정론만 (Bedrock 불필요)

산출:
    - 표준출력 집계: "등급 일치 X% · 인용 적합 Y% · 사실 반영 Z% …"
    - eval/e2e_judge/results.json (문항별 상세)

설계:
    - 제품 파이프라인을 in-process 직호출(eval/runner.py 패턴) — create_session →
      seed_slots → post_message. HTTP 서버 불필요.
    - 결정론 채점(1차): 응답 타입 / 기대 등급(likelihood ∈ 기대집합) / 인용 ≥1 /
      필수 언급(must_mention_any) / 금지 패턴(regex).
    - LLM-as-judge(2차, Bedrock Claude 오프라인 전용): 인용 적합·사실 반영·재질문 없음·톤.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from app.domains.sessions.schemas import AssistantAssessment, AssistantComparison
from app.domains.sessions.service import create_session, post_message, seed_slots

_EVAL_SET = Path(__file__).parent / "eval_set.json"
_RESULTS = Path(__file__).parent / "results.json"


def _final_text_and_citations(assistant: Any) -> tuple[str, list[dict[str, str]], str | None]:
    """최종 응답에서 (본문, 인용 리스트, likelihood) 추출 — 타입별 분기."""
    if isinstance(assistant, AssistantAssessment):
        cites = [{"clause": c.clause, "text": c.text} for c in assistant.citations]
        # 사용자 가시 텍스트 전체 — 서류·기한 안내는 next_steps 로 나가므로
        # summary 만 보면 복합 질문 응답이 저평가된다(측정 충실도)
        text = "\n".join([assistant.summary, *assistant.next_steps])
        return text, cites, assistant.likelihood
    if isinstance(assistant, AssistantComparison):
        cites = []
        for p in assistant.policies:
            cites += [{"clause": c.clause, "text": c.text} for c in p.assessment.citations]
        return assistant.summary, cites, None
    # AssistantAnswer / AssistantAsk
    msg = getattr(assistant, "message", "") or ""
    cites = [
        {"clause": c.clause, "text": c.text} for c in getattr(assistant, "citations", []) or []
    ]
    return msg, cites, None


def run_item(item: dict[str, Any]) -> dict[str, Any]:
    """문항 1건 실행 + 결정론 채점."""
    session, _ = create_session(initial_message=None)
    seed = dict(item.get("seed_slots") or {})
    if seed:
        seed_slots(session.session_id, seed)

    assistant = None
    for turn in item["turns"]:
        response = post_message(session.session_id, turn)
        assistant = response.assistant

    final_text, citations, likelihood = _final_text_and_citations(assistant)
    atype = getattr(assistant, "type", "?")

    checks: dict[str, bool] = {}
    # 응답 타입
    if "expected_type" in item:
        checks["type_ok"] = atype == item["expected_type"]
    elif "expected_type_in" in item:
        checks["type_ok"] = atype in item["expected_type_in"]
    # 등급 (assessment 한정)
    if "expected_likelihood_in" in item and likelihood is not None:
        checks["likelihood_ok"] = likelihood in item["expected_likelihood_in"]
    # 인용 존재 (판정/비교/answer 공통 — ask 는 제외)
    if atype in ("assessment", "comparison", "answer"):
        checks["has_citation"] = len(citations) >= 1
    # 필수 언급
    if item.get("must_mention_any"):
        checks["mention_ok"] = any(k in final_text for k in item["must_mention_any"])
    # 결정론 인용 적합 (Sprint 36 고도화) — 인용 조항/본문에 기대 키워드 중 하나라도 존재.
    # judge 의존 없는 1차 인용 지표 (judge 는 의미 적합성, 본 채점은 키워드 존재).
    if item.get("expected_citation_keywords") and citations:
        joined = " ".join(f"{c.get('clause') or ''} {c.get('text') or ''}" for c in citations)
        checks["citation_kw_ok"] = any(k in joined for k in item["expected_citation_keywords"])
    # 금지 패턴
    violations = [p for p in item.get("forbidden_patterns", []) if re.search(p, final_text)]
    checks["no_forbidden"] = not violations

    return {
        "id": item["id"],
        "category": item["category"],
        "actual_type": atype,
        "actual_likelihood": likelihood,
        "final_text": final_text,
        "citations": citations,
        "deterministic": checks,
        "forbidden_violations": violations,
    }


def aggregate(records: list[dict[str, Any]], judged: bool) -> dict[str, Any]:
    def rate(key: str, source: str) -> tuple[int, int]:
        vals = [r[source].get(key) for r in records if key in r.get(source, {})]
        return sum(1 for v in vals if v), len(vals)

    agg: dict[str, Any] = {"items": len(records)}
    for key in ("type_ok", "likelihood_ok", "has_citation", "citation_kw_ok",
                "mention_ok", "no_forbidden"):
        ok, n = rate(key, "deterministic")
        if n:
            agg[f"det_{key}"] = f"{ok}/{n} ({round(ok / n * 100)}%)"
    if judged:
        for key in ("citation_relevant", "facts_reflected", "no_reask", "tone_ok"):
            ok, n = rate(key, "judge")
            if n:
                agg[f"judge_{key}"] = f"{ok}/{n} ({round(ok / n * 100)}%)"
    return agg


def consistency_run(items: list[dict[str, Any]], repeat: int) -> dict[str, Any]:
    """등급 명시 문항을 repeat 회 반복 실행 — run-to-run 등급 일관성 측정.

    judge 미호출(결정론만). 문항별로 매 실행의 likelihood 가 전부 동일하면 consistent.
    """
    targets = [i for i in items if "expected_likelihood_in" in i]
    per_item: list[dict[str, Any]] = []
    for item in targets:
        grades: list[str | None] = []
        for _ in range(repeat):
            try:
                rec = run_item(item)
                grades.append(rec["actual_likelihood"])
            except Exception as exc:  # noqa: BLE001
                grades.append(f"ERROR:{str(exc)[:40]}")
        per_item.append({
            "id": item["id"],
            "grades": grades,
            "consistent": len(set(grades)) == 1,
        })
        print(f"  {item['id']}: {grades} {'✓' if len(set(grades)) == 1 else '✗ 변동'}")
    n = len(per_item)
    ok = sum(1 for r in per_item if r["consistent"])
    return {
        "repeat": repeat,
        "items": n,
        "consistency": f"{ok}/{n} ({round(ok / n * 100) if n else 0}%)",
        "per_item": per_item,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-judge", action="store_true", help="결정론 채점만 (Bedrock 미호출)")
    parser.add_argument("--only", help="특정 문항 id 만 실행")
    parser.add_argument("--repeat", type=int, default=0,
                        help="등급 명시 문항을 N회 반복해 등급 일관성만 측정 (judge 미호출)")
    args = parser.parse_args()

    eval_set = json.loads(_EVAL_SET.read_text(encoding="utf-8"))
    items = eval_set["items"]
    if args.only:
        items = [i for i in items if i["id"] == args.only]

    if args.repeat:
        print(f"=== 등급 일관성 측정 (repeat={args.repeat}) ===")
        cons = consistency_run(items, args.repeat)
        print(f"\n일관성: {cons['consistency']}")
        out = _RESULTS.parent / "consistency.json"
        out.write_text(json.dumps(cons, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"저장: {out}")
        return

    judge = None
    if not args.no_judge:
        from eval.e2e_judge.judge import BedrockJudge

        judge = BedrockJudge()

    records = []
    for item in items:
        print(f"▶ {item['id']} ({item['category']})")
        try:
            rec = run_item(item)
        except Exception as exc:  # noqa: BLE001 — 한 문항 실패가 전체를 막지 않게
            print(f"  ✗ 실행 실패: {exc}")
            records.append({"id": item["id"], "category": item["category"],
                            "error": str(exc)[:200], "deterministic": {}})
            continue
        det = rec["deterministic"]
        print(f"  결정론: {det}")
        if judge is not None:
            try:
                rec["judge"] = judge.grade(item, rec["final_text"], rec["citations"])
                print(f"  judge: {rec['judge']}")
            except Exception as exc:  # noqa: BLE001
                rec["judge"] = {"error": str(exc)[:200]}
                print(f"  ✗ judge 실패: {exc}")
        records.append(rec)

    agg = aggregate(records, judged=judge is not None)
    print("\n=== 집계 ===")
    for k, v in agg.items():
        print(f"  {k}: {v}")

    _RESULTS.write_text(
        json.dumps({"aggregate": agg, "records": records}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"\n저장: {_RESULTS}")


if __name__ == "__main__":
    main()
