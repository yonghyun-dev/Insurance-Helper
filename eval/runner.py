"""eval.runner

파일 경로: eval/runner.py
목적: 평가 시나리오 JSON 1건/전체를 실행하고 메트릭을 출력한다.
사용:
    python -m eval.runner --scenario eval/scenarios/auto_basic.json
    python -m eval.runner --all

설계 참고:
    - docs/design/tech-decisions.md § Sprint 8~11 결정 11 (평가 셋)
    - docs/agents/researcher/06_sprint8-ops-integration.md (eval 디렉토리 격리 이유)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.sessions.schemas import AssistantAssessment
from app.sessions.service import create_session, post_message

_SCENARIO_DIR = Path(__file__).parent / "scenarios"


def run_scenario(path: Path) -> dict[str, Any]:
    """시나리오 1건 실행 후 결과 dict 반환.

    각 turn 의 응답을 expected 값과 비교 — 단순 substring/dict-subset 매칭 (Sprint 8 골격).
    Sprint 11: LLM-as-judge 도입.
    """
    with path.open(encoding="utf-8") as f:
        scenario = json.load(f)

    print(f"\n[{scenario['id']}] {scenario['description']}")

    session, _ = create_session(initial_message=None)
    results = []
    for i, turn in enumerate(scenario["turns"], 1):
        print(f"  turn {i} 입력: {turn['user']!r}")
        response = post_message(session.session_id, turn["user"])
        assistant = response.assistant
        turn_result = {
            "turn": i,
            "actual_response_type": assistant.type,
            "actual_slots": response.slots.model_dump(exclude_none=True),
        }
        # 기본 검증
        expected_type = turn.get("expected_response_type")
        expected_type_in = turn.get("expected_response_type_in")
        if expected_type:
            turn_result["response_type_ok"] = assistant.type == expected_type
        elif expected_type_in:
            turn_result["response_type_ok"] = assistant.type in expected_type_in

        if isinstance(assistant, AssistantAssessment):
            turn_result["actual_confidence"] = assistant.confidence
            turn_result["actual_citations_count"] = len(assistant.citations)
            min_c = turn.get("min_citations")
            if min_c is not None:
                turn_result["citations_ok"] = len(assistant.citations) >= min_c
            ec = turn.get("expected_confidence")
            if ec:
                turn_result["confidence_ok"] = assistant.confidence == ec

        # 슬롯 부분 일치
        es = turn.get("expected_slots_partial")
        if es:
            actual = response.slots.model_dump(exclude_none=True)
            turn_result["slots_ok"] = all(actual.get(k) == v for k, v in es.items())
        results.append(turn_result)
        print(f"  → {assistant.type}  슬롯={turn_result['actual_slots']}")

    summary = {"scenario": scenario["id"], "turns": results}
    print(f"\n[{scenario['id']}] 결과: {summary}\n")
    return summary


def run_all() -> list[dict[str, Any]]:
    """모든 시나리오 일괄 실행."""
    results = []
    for path in sorted(_SCENARIO_DIR.glob("*.json")):
        try:
            results.append(run_scenario(path))
        except Exception as exc:
            print(f"  ERROR running {path.name}: {exc}", file=sys.stderr)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="평가 셋 runner (Sprint 8 골격)")
    parser.add_argument("--scenario", type=Path, help="시나리오 JSON 1건 경로")
    parser.add_argument("--all", action="store_true", help="모든 시나리오 일괄 실행")
    args = parser.parse_args()

    if args.all:
        run_all()
    elif args.scenario:
        run_scenario(args.scenario)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
