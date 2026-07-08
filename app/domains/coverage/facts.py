"""app.domains.coverage.facts

SlotState(자연어 추출 슬롯) → ClaimFacts(정규화 판정 입력) 매퍼.

경계: 여기까지가 뉴럴(자연어→구조화). 이 아래(engine)는 순수 심볼릭.
현재 SlotState 에 없는 사실(세대·급여구분·목적·보장기간)은 None/기본값으로 두고,
Phase 2 에서 슬롯 추출(뉴럴)을 확장해 채운다. 엔진은 부족분을 missing 으로 알린다.
"""

from __future__ import annotations

from app.domains.coverage.schemas import ClaimFacts, ClaimPurpose, TreatmentType
from app.domains.sessions.schemas import SlotState


def _infer_treatment_type(slots: SlotState) -> TreatmentType | None:
    """입원일수/외래횟수로 치료구분 추론. 둘 다 없으면 미상(None)."""
    if slots.hospitalization_days and slots.hospitalization_days > 0:
        return TreatmentType.INPATIENT
    if slots.outpatient_visits and slots.outpatient_visits > 0:
        return TreatmentType.OUTPATIENT
    return None


def _map_purpose(raw: str | None) -> ClaimPurpose:
    """SlotState.purpose(문자열) → ClaimPurpose. 미상/미인식은 치료 목적."""
    if not raw:
        return ClaimPurpose.TREATMENT
    try:
        return ClaimPurpose(raw.strip())
    except ValueError:
        return ClaimPurpose.TREATMENT


def build_facts_from_slots(
    slots: SlotState,
    *,
    generation: int | None = None,
    purpose: ClaimPurpose | None = None,
) -> ClaimFacts:
    """가용 슬롯을 ClaimFacts 로 정규화(best-effort).

    generation/purpose 는 슬롯(마이데이터 seed·LLM 목적추출)에서 읽되, 인자로 덮어쓸 수 있다.
    """
    return ClaimFacts(
        insurer_id=slots.insurer_id,
        generation=generation if generation is not None else slots.generation,
        treatment_type=_infer_treatment_type(slots),
        diagnosis=slots.diagnosis,
        diagnosis_code=slots.diagnosis_code,
        purpose=purpose if purpose is not None else _map_purpose(slots.purpose),
        charged_amount=slots.claim_amount,
        incident_date=slots.incident_date,
        hospitalization_days=slots.hospitalization_days,
        outpatient_visits=slots.outpatient_visits,
    )
