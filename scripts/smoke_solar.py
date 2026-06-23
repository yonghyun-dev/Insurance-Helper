"""scripts/smoke_solar.py — Sprint 16 · 1a 라이브 Solar 검증.

실 `UPSTAGE_API_KEY` (+ `.env` 의 `LLM_PROVIDER=upstage`) 가 필요하다.
제품 추론 7경로가 의존하는 LLM 능력을 Upstage Solar 에서 실측한다:

  1. extract_slots            — forced tool_choice (Function Calling 강제)
  2. next_question           — forced tool_choice (동적 enum)
  3. classify_document       — forced tool_choice (OCR 분류, 추론)
  4. extract_slots_from_document — forced tool_choice (OCR 슬롯 추출, 추론)
  5. (raw) json_schema strict — generate_assessment 핵심(환각차단)
  6. (raw) json_object        — react.py Think
  7. (raw) tools=auto         — agent.py / langgraph_agent.py

실행:  uv run python scripts/smoke_solar.py
키 없으면 ConfigurationError 로 즉시 실패(폴백 없음 — 정책대로).
"""

from __future__ import annotations

import json
import sys

from app.domains.sessions.llm import (
    classify_document,
    extract_slots,
    extract_slots_from_document,
    next_question,
)
from app.domains.sessions.schemas import SlotState
from app.infrastructure.core.config import get_settings
from app.infrastructure.llm.client import get_chat_client, get_chat_model

_results: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str) -> None:
    _results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name} — {detail}")


def probe_extract_slots() -> None:
    try:
        out = extract_slots(
            history=[],
            user_msg="2024년 3월 5일에 자동차 사고가 났어요. 삼성화재 자동차보험이에요.",
            current_slots=SlotState(),
        )
        ok = isinstance(out, dict) and bool(out)
        _record("1.extract_slots (forced FC)", ok, f"추출 키={list(out)}")
    except Exception as exc:  # noqa: BLE001
        _record("1.extract_slots (forced FC)", False, repr(exc))


def probe_next_question() -> None:
    try:
        ask = next_question(slots=SlotState(area="auto"), missing=["product", "incident_date"])
        ok = bool(ask.message)
        _record("2.next_question (forced FC)", ok, f"message={ask.message[:40]!r}")
    except Exception as exc:  # noqa: BLE001
        _record("2.next_question (forced FC)", False, repr(exc))


def probe_classify_document() -> None:
    try:
        out = classify_document(
            text="진 단 서\n병명: 급성 충수염\n입원기간: 2024-05-05 ~ 2024-05-07\n발급: 강남세브란스병원"
        )
        ok = isinstance(out, dict) and "doc_type" in out
        _record("3.classify_document (forced FC)", ok, f"doc_type={out.get('doc_type')}")
    except Exception as exc:  # noqa: BLE001
        _record("3.classify_document (forced FC)", False, repr(exc))


def probe_extract_doc_slots() -> None:
    try:
        out = extract_slots_from_document(
            text="진 단 서\n병명: 급성 충수염\n질병분류기호: K35\n의료기관: 강남세브란스병원",
            doc_type="diagnosis",
        )
        ok = isinstance(out, dict)
        _record("4.extract_slots_from_document (forced FC)", ok, f"추출 키={list(out)}")
    except Exception as exc:  # noqa: BLE001
        _record("4.extract_slots_from_document (forced FC)", False, repr(exc))


def probe_json_schema_strict() -> None:
    """generate_assessment 핵심 — response_format=json_schema, strict=True."""
    schema = {
        "name": "smoke_assessment",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "likelihood": {"type": "string", "enum": ["높음", "중간", "낮음"]},
                "summary": {"type": "string"},
            },
            "required": ["likelihood", "summary"],
        },
    }
    try:
        resp = get_chat_client().chat.completions.create(
            model=get_chat_model(),
            messages=[
                {"role": "system", "content": "보험 청구 가능성을 간단히 판단해 JSON 으로만 답하라."},
                {"role": "user", "content": "자동차 추돌, 과실 30%, 약관상 보상 대상."},
            ],
            response_format={"type": "json_schema", "json_schema": schema},
            temperature=0.2,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        ok = data.get("likelihood") in {"높음", "중간", "낮음"}
        _record("5.json_schema strict (assessment)", ok, f"likelihood={data.get('likelihood')}")
    except Exception as exc:  # noqa: BLE001
        _record("5.json_schema strict (assessment)", False, repr(exc))


def probe_json_object() -> None:
    """react.py — response_format=json_object."""
    try:
        resp = get_chat_client().chat.completions.create(
            model=get_chat_model(),
            messages=[
                {"role": "user", "content": '{"decision":"FINISH" 또는 "REFINE"} 형식 JSON 하나만 출력. 충분하면 FINISH.'}
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        ok = bool(data)
        _record("6.json_object (react)", ok, f"keys={list(data)}")
    except Exception as exc:  # noqa: BLE001
        _record("6.json_object (react)", False, repr(exc))


def probe_tools_auto() -> None:
    """agent.py — tools=[...], tool_choice='auto'."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_terms",
                "description": "약관 조항을 검색한다.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }
    ]
    try:
        resp = get_chat_client().chat.completions.create(
            model=get_chat_model(),
            messages=[{"role": "user", "content": "자동차보험 자기부담금 조항을 찾아줘."}],
            tools=tools,
            tool_choice="auto",
            temperature=0,
        )
        msg = resp.choices[0].message
        ok = bool(getattr(msg, "tool_calls", None)) or bool(msg.content)
        called = [tc.function.name for tc in (msg.tool_calls or [])]
        _record("7.tools=auto (agent)", ok, f"tool_calls={called or '없음(텍스트 응답)'}")
    except Exception as exc:  # noqa: BLE001
        _record("7.tools=auto (agent)", False, repr(exc))


def main() -> int:
    s = get_settings()
    print(
        f"== Solar 스모크 == provider={s.llm_provider} model={s.effective_llm_model} "
        f"base_url={s.effective_llm_base_url or '(SDK 기본)'}\n"
    )
    if s.llm_provider != "upstage":
        print("경고: LLM_PROVIDER 가 upstage 가 아님 — 제품 검증은 upstage 로 실행하세요.\n")

    probe_extract_slots()
    probe_next_question()
    probe_classify_document()
    probe_extract_doc_slots()
    probe_json_schema_strict()
    probe_json_object()
    probe_tools_auto()

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n== 결과: {passed}/{total} PASS ==")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
