"""app.infrastructure.external.health_data.mapper

진료내역(TreatmentDict) → SlotState 부분 dict 매핑 + 사용자 확인 카드 형식.

설계 (REQ-14 § 슬롯 매핑 + PM-22 결정 4):
    - claim_amount = patient_paid (환자 본인부담분 — 실제 청구 가능 액수)
    - diagnosis = diagnosis_names[0] (한국어 첫 진단명)
    - diagnosis_code = diagnosis_codes[0] (KCD-7 첫 코드)
    - area = "accident_disease" (의료 분야 고정)
    - 다른 필드는 1:1 매핑
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.infrastructure.external.health_data.adapter import TreatmentDict


class TreatmentCard(TypedDict):
    """사용자 확인 카드 — 진료 1건 (UI 노출용 + slot_mapping 사전 계산)."""

    treatment_id: str
    treatment_date: str
    hospital_name: str
    department: str
    diagnosis_summary: str
    is_hospitalization: bool
    hospitalization_days: int
    outpatient_visits: int
    total_cost: int
    claim_amount: int
    slot_mapping: dict[str, Any]


def treatment_to_slot_dict(t: TreatmentDict) -> dict[str, Any]:
    """진료내역 1건 → SlotState 부분 dict.

    None/빈 값은 제외 (extract_slots merge 정책과 일관).
    """
    result: dict[str, Any] = {
        "area": "accident_disease",
        "incident_date": t["treatment_date"],
        "treatment_period": t["treatment_period"],
        "hospital": t["hospital_name"],
        "hospitalization_days": t["hospitalization_days"],
        "outpatient_visits": t["outpatient_visits"],
        "claim_amount": t["patient_paid"],
    }
    if t["diagnosis_names"]:
        result["diagnosis"] = t["diagnosis_names"][0]
    if t["diagnosis_codes"]:
        result["diagnosis_code"] = t["diagnosis_codes"][0]
    return result


def treatment_to_card(t: TreatmentDict) -> TreatmentCard:
    """진료내역 1건 → UI 카드 형식 (사용자 선택용)."""
    diagnosis_summary = (
        ", ".join(t["diagnosis_names"]) if t["diagnosis_names"] else "진단명 없음"
    )
    return TreatmentCard(
        treatment_id=t["treatment_id"],
        treatment_date=t["treatment_date"],
        hospital_name=t["hospital_name"],
        department=t["department"],
        diagnosis_summary=diagnosis_summary,
        is_hospitalization=t["is_hospitalization"],
        hospitalization_days=t["hospitalization_days"],
        outpatient_visits=t["outpatient_visits"],
        total_cost=t["total_cost"],
        claim_amount=t["patient_paid"],
        slot_mapping=treatment_to_slot_dict(t),
    )
