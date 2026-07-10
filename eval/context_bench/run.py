"""컨텍스트 전략 3종 실측 벤치 (Sprint 35) — 전 시나리오.

시나리오 6종(scenarios.py) × 8턴 × 전략 3종을 동일 모델(Solar)로 실행해
토큰·지연·사실유지(최종 답변 명시)를 비교한다.

전략:
  S1 two-layer  — 슬롯(정형) + 세션 메모(비정형 요약 사실)   ← 현 제품 방식
  S2 full       — 전체 대화 이력을 매 턴 그대로 전달
  S3 summary    — 이력이 임계(1200자) 초과 시 LLM 롤링 요약 + 최근 2턴

실행: .venv/bin/python -m eval.context_bench.run
출력: 표준출력 요약 + eval/context_bench/results.json (시나리오별 + 집계)
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from app.infrastructure.llm.client import get_chat_client, get_chat_model

from eval.context_bench.scenarios import SCENARIOS

SYSTEM = (
    "당신은 실손의료보험 청구 안내 어시스턴트다. 사용자의 상황 정보를 바탕으로 "
    "청구 가능성과 유의사항을 3~5문장 한국어로 안내한다. 단정 금지(어시스턴트 톤). "
    "이미 확인된 사실을 다시 묻지 않는다. 교통사고 대인배상 기지급분은 실손 보상에서 "
    "제외되고, 실손 중복가입은 비례분담(이중 수령 불가)임을 알고 있다."
)

# 재질문 검출 — 이미 준 사실을 다시 묻는 패턴 (있으면 감점)
REASK = re.compile(
    r"(입원[을은 ]*(하셨|했)나요|며칠[이나 ]*입원|진단명[을은 ]*알려|수술[을은 ]*(받으|하셨)"
    r"|산재[인가 ]*(신가|인지)|몇 번[이나 ]*(통원|가셨))"
)

STRATEGIES = ("S1_two_layer", "S2_full", "S3_summary")


def _ask(client, model: str, messages: list[dict[str, str]]) -> tuple[str, int, int, float]:
    t0 = time.perf_counter()
    r = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
    dt = time.perf_counter() - t0
    u = r.usage
    return (r.choices[0].message.content or "", u.prompt_tokens, u.completion_tokens, dt)


def _summarize(client, model: str, transcript: str) -> tuple[str, int, int, float]:
    msgs = [
        {"role": "system", "content": "다음 보험 상담 대화를 판정에 필요한 사실 위주로 5문장 이내 한국어로 요약하라."},
        {"role": "user", "content": transcript},
    ]
    return _ask(client, model, msgs)


def _turn_states(turns: list[dict[str, Any]]) -> list[tuple[dict, list]]:
    slots: dict[str, Any] = {}
    notes: list[str] = []
    out = []
    for t in turns:
        slots.update(t.get("slots", {}))
        slots.update(t.get("slots_add", {}))
        notes += t.get("notes", []) + t.get("notes_add", [])
        out.append((dict(slots), list(notes)))
    return out


def run_scenario(client, model: str, scenario: dict[str, Any]) -> dict[str, Any]:
    turns = scenario["turns"]
    states = _turn_states(turns)
    result: dict[str, Any] = {}

    for strategy in STRATEGIES:
        rows = []
        transcript: list[str] = []
        summary = ""
        ov_pt = ov_ct = ov_calls = 0
        last_response = ""
        for i, t in enumerate(turns):
            user = t["user"]
            st_slots, st_notes = states[i]
            if strategy == "S1_two_layer":
                payload = json.dumps(
                    {"slots": st_slots, "session_notes": st_notes, "question": user},
                    ensure_ascii=False,
                )
                messages = [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": payload}]
            elif strategy == "S2_full":
                messages = [{"role": "system", "content": SYSTEM}]
                for line in transcript:
                    role, content = line.split("\t", 1)
                    messages.append({"role": role, "content": content})
                messages.append({"role": "user", "content": user})
            else:  # S3_summary
                joined = "\n".join(c.split("\t", 1)[1] for c in transcript)
                if len(joined) > 1200:
                    summary, spt, sct, _ = _summarize(client, model, joined)
                    ov_pt += spt
                    ov_ct += sct
                    ov_calls += 1
                    transcript = transcript[-4:]
                messages = [{"role": "system", "content": SYSTEM}]
                if summary:
                    messages.append({"role": "system", "content": f"이전 대화 요약: {summary}"})
                for line in transcript:
                    role, content = line.split("\t", 1)
                    messages.append({"role": role, "content": content})
                messages.append({"role": "user", "content": user})

            text, pt, ct, dt = _ask(client, model, messages)
            rows.append({"turn": i + 1, "prompt_tokens": pt, "completion_tokens": ct,
                         "latency_s": round(dt, 2)})
            transcript.append(f"user\t{user}")
            transcript.append(f"assistant\t{text}")
            last_response = text

        facts = {name: bool(p.search(last_response)) for name, p in scenario["facts"]}
        result[strategy] = {
            "total_prompt_tokens": sum(r["prompt_tokens"] for r in rows) + ov_pt,
            "total_completion_tokens": sum(r["completion_tokens"] for r in rows) + ov_ct,
            "final_turn_prompt_tokens": rows[-1]["prompt_tokens"],
            "avg_latency_s": round(sum(r["latency_s"] for r in rows) / len(rows), 2),
            "summary_overhead": {"calls": ov_calls, "prompt_tokens": ov_pt, "completion_tokens": ov_ct},
            "fact_retention": facts,
            "fact_score": sum(facts.values()),
            "reask_detected": bool(REASK.search(last_response)),
            "turn_prompt_tokens": [r["prompt_tokens"] for r in rows],
            "final_response": last_response,
        }
    return result


def run() -> dict[str, Any]:
    client = get_chat_client()
    model = get_chat_model()
    all_results: dict[str, Any] = {"scenarios": {}, "aggregate": {}}

    for sc in SCENARIOS:
        print(f"\n### 시나리오: {sc['name']}")
        res = run_scenario(client, model, sc)
        all_results["scenarios"][sc["name"]] = res
        for s in STRATEGIES:
            v = res[s]
            print(f"  [{s}] total_pt={v['total_prompt_tokens']} final_pt={v['final_turn_prompt_tokens']} "
                  f"avg_lat={v['avg_latency_s']}s facts={v['fact_score']}/5 reask={v['reask_detected']}")

    # 집계 (시나리오 평균/합)
    n = len(SCENARIOS)
    for s in STRATEGIES:
        vals = [all_results["scenarios"][sc["name"]][s] for sc in SCENARIOS]
        all_results["aggregate"][s] = {
            "scenarios": n,
            "mean_total_prompt_tokens": round(sum(v["total_prompt_tokens"] for v in vals) / n),
            "mean_final_turn_prompt_tokens": round(sum(v["final_turn_prompt_tokens"] for v in vals) / n),
            "mean_avg_latency_s": round(sum(v["avg_latency_s"] for v in vals) / n, 2),
            "fact_score_total": f"{sum(v['fact_score'] for v in vals)}/{n * 5}",
            "reask_count": sum(1 for v in vals if v["reask_detected"]),
            "summary_calls_total": sum(v["summary_overhead"]["calls"] for v in vals),
        }
    print("\n=== 집계 ===")
    for s, a in all_results["aggregate"].items():
        print(f"[{s}] mean_total_pt={a['mean_total_prompt_tokens']} "
              f"mean_final_pt={a['mean_final_turn_prompt_tokens']} "
              f"mean_lat={a['mean_avg_latency_s']}s facts={a['fact_score_total']} "
              f"reask={a['reask_count']}")

    out = Path(__file__).parent / "results.json"
    out.write_text(json.dumps(all_results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {out}")
    return all_results


if __name__ == "__main__":
    run()
