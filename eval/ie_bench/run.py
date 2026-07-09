"""eval.ie_bench.run — IE 1단계 vs 구 2단계(OCR→LLM) A/B (Sprint 32 T4).

20케이스(서류4종×열화5)에 두 경로를 실행해 필드 정확도·지연을 실측한다.
결과가 attachments 라우터의 기본 경로를 결정한다 (미측정 기본값 금지).

판정: truth 의 각 필드에 대해 추출값이 기대값을 포함(부분 문자열, 숫자는 정규화 비교)하면 정답.

사용: .venv/bin/python -m eval.ie_bench.run  (fixtures 먼저: python -m eval.ie_bench.generate)
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def _norm_num(s: str) -> str:
    return re.sub(r"[^0-9]", "", str(s))


def field_correct(expected: Any, actual: Any) -> bool:
    if actual is None or str(actual).strip() == "":
        return False
    if isinstance(expected, int) or str(expected).isdigit():
        return _norm_num(actual) == _norm_num(expected)
    return str(expected) in str(actual)


def run_ie(data: bytes, doc_type: str) -> dict[str, Any]:
    from app.domains.attachments.ie_schemas import DOC_IE_SCHEMAS, ie_result_to_slots
    from app.infrastructure.external.ocr.adapter import get_ocr_adapter

    raw = get_ocr_adapter().extract_information(  # type: ignore[attr-defined]
        data, "image/png", DOC_IE_SCHEMAS[doc_type], schema_name=doc_type
    )
    return ie_result_to_slots(doc_type, raw)


def run_legacy(data: bytes, doc_type: str) -> dict[str, Any]:
    from app.domains.sessions import llm
    from app.infrastructure.external.ocr.adapter import get_ocr_adapter
    from app.shared.security.pii import mask_pii

    ocr = get_ocr_adapter().extract_text(data, "image/png")
    return llm.extract_slots_from_document(mask_pii(ocr["text"]), doc_type)


def main() -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for case in manifest:
        data = (FIXTURES / case["file"]).read_bytes()
        truth = case["truth"]
        entry: dict[str, Any] = {"case": case["file"]}
        for path_name, fn in (("ie", run_ie), ("legacy", run_legacy)):
            t0 = time.perf_counter()
            try:
                slots = fn(data, case["doc_type"])
                ok = sum(1 for k, v in truth.items() if field_correct(v, slots.get(k)))
            except Exception as exc:  # noqa: BLE001 — 실패도 데이터
                slots, ok = {"__error__": str(exc)[:80]}, 0
            entry[path_name] = {
                "correct": ok, "total": len(truth),
                "latency_s": round(time.perf_counter() - t0, 1),
            }
        rows.append(entry)
        print(f"{case['file']:34s} IE {entry['ie']['correct']}/{entry['ie']['total']} "
              f"({entry['ie']['latency_s']}s) | 2단계 {entry['legacy']['correct']}/"
              f"{entry['legacy']['total']} ({entry['legacy']['latency_s']}s)")

    def agg(name: str) -> dict[str, float]:
        c = sum(r[name]["correct"] for r in rows)
        t = sum(r[name]["total"] for r in rows)
        lat = sum(r[name]["latency_s"] for r in rows) / len(rows)
        return {"accuracy": round(c / t, 3), "correct": c, "total": t,
                "avg_latency_s": round(lat, 1)}

    summary = {"ie": agg("ie"), "legacy": agg("legacy")}
    print("\n==== 종합 ====")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    (FIXTURES / "results.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
