"""app.domains.attachments.ie_schemas

Sprint 31 D3 — Upstage Information Extraction 용 서류 유형별 json_schema + 슬롯 매핑.

기존 경로(OCR 텍스트 → Solar 재추출 2단계) 대신, 서류 원본 이미지를 IE 에 스키마와 함께
1회 호출해 구조화 필드를 직접 뽑는다. 필드명은 SlotState 와 일치시켜 매핑 비용을 없앤다.
(스키마는 실서류 육안 검토 기반 설계 — 진단서/영수증/청구서/사고사실확인원의 표준 서식 항목)
"""

from __future__ import annotations

from typing import Any

# 서류 유형 → IE json_schema (schema 부). description 은 한국 표준 서식 표기 기준.
_COMMON_DATE = "YYYY-MM-DD 형식으로. 서류에 연월일이 한글로 있어도 변환."

DOC_IE_SCHEMAS: dict[str, dict[str, Any]] = {
    "diagnosis": {
        "type": "object",
        "properties": {
            "diagnosis": {
                "type": "string",
                "description": "병명/진단명 (한글 병명. 예: 손목터널증후군, 발목 골절)",
            },
            "diagnosis_code": {
                "type": "string",
                "description": "질병분류기호/KCD 코드 (예: S82.3, G56.0)",
            },
            "incident_date": {
                "type": "string",
                "description": f"발병일 또는 진단일. {_COMMON_DATE}",
            },
            "hospital": {"type": "string", "description": "의료기관(병원) 명칭"},
            "treatment_period": {
                "type": "string",
                "description": "치료기간/입원기간 (예: 2026-03-01 ~ 2026-03-05)",
            },
            "hospitalization_days": {
                "type": "integer",
                "description": "입원일수 (입원 안 했으면 0)",
            },
            "outpatient_visits": {
                "type": "integer",
                "description": "통원(외래) 횟수 (서류에 없으면 생략)",
            },
        },
    },
    "receipt": {
        "type": "object",
        "properties": {
            "hospital": {"type": "string", "description": "의료기관/발행처 명칭"},
            "treatment_period": {
                "type": "string",
                "description": "진료기간 (예: 2026-03-01 ~ 2026-03-05)",
            },
            "incident_date": {
                "type": "string",
                "description": f"진료일/발행일. {_COMMON_DATE}",
            },
            "claim_amount": {
                "type": "string",
                "description": "환자부담총액(본인부담 합계) 원 단위 숫자만 (예: 154000)",
            },
            "diagnosis": {"type": "string", "description": "진단명/질병명 (기재된 경우만)"},
            "diagnosis_code": {"type": "string", "description": "질병군/질병분류 번호 (기재된 경우만)"},
        },
    },
    "claim_form": {
        "type": "object",
        "properties": {
            "insurer": {"type": "string", "description": "보험회사 명칭 (예: 삼성화재)"},
            "product": {"type": "string", "description": "보험상품명 (예: 실손의료보험)"},
            "policy_no": {"type": "string", "description": "증권번호/계약번호"},
            "incident_date": {"type": "string", "description": f"사고일자/발병일. {_COMMON_DATE}"},
            "claim_amount": {"type": "string", "description": "청구금액 원 단위 숫자만"},
            "incident_location": {"type": "string", "description": "사고 장소"},
        },
    },
    "police_report": {
        "type": "object",
        "properties": {
            "incident_date": {"type": "string", "description": f"사고 발생 일시. {_COMMON_DATE}"},
            "incident_location": {"type": "string", "description": "사고 발생 장소"},
            "diagnosis": {"type": "string", "description": "부상명/피해 내용 (기재된 경우만)"},
        },
    },
}


def ie_result_to_slots(doc_type: str, result: dict[str, Any]) -> dict[str, Any]:
    """IE 응답 → SlotState 필드 dict. 빈 값 제거 + 정수형 보정.

    필드명이 SlotState 와 동일하게 설계돼 있어 필터링/타입 보정만 한다.
    receipt/diagnosis 는 의료 서류이므로 area 를 실손 영역으로 보정한다.
    """
    allowed = set(DOC_IE_SCHEMAS.get(doc_type, {}).get("properties", {}))
    slots: dict[str, Any] = {}
    for key, value in (result or {}).items():
        if key not in allowed or value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if key in ("hospitalization_days", "outpatient_visits"):
            try:
                value = int(str(value).strip().rstrip("일회"))
            except ValueError:
                continue
        slots[key] = value
    if slots and doc_type in ("diagnosis", "receipt"):
        slots.setdefault("area", "accident_disease")
    return slots
