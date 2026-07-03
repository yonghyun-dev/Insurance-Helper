"""app.domains.claims.service

규칙 기반 필요서류 체크리스트 + 청구 요약 + 더미 접수.
LLM 비호출 — area + 슬롯에서 결정적으로 산출(설명가능).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domains.claims.schemas import (
    ChecklistItem,
    ClaimChecklist,
    ClaimReceipt,
    ClaimSummary,
)
from app.domains.sessions.schemas import Session, SlotState

# 모든 청구 공통 서류
_COMMON: tuple[tuple[str, str, bool, str], ...] = (
    ("claim_form", "보험금 청구서", True, "모든 청구의 기본 서류입니다."),
    ("id_copy", "신분증 사본", True, "청구인 본인 확인용입니다."),
    ("bankbook", "통장 사본", True, "보험금 입금 계좌(본인 명의) 확인용입니다."),
)

# 영역별 추가 서류 (실손 전용, PM-33)
_AREA: dict[str, tuple[tuple[str, str, bool, str], ...]] = {
    "accident_disease": (
        ("diagnosis", "진단서", True, "상해·질병명과 치료 내용을 확인합니다."),
        ("receipt_detail", "진료비 영수증·세부내역서", True, "청구 금액 산정 근거입니다."),
    ),
}


def build_checklist(slots: SlotState) -> ClaimChecklist:
    """area + 슬롯에 따라 필요 서류 목록을 산출한다."""
    items = [
        ChecklistItem(id=i, label=label, required=req, reason=reason)
        for (i, label, req, reason) in _COMMON
    ]
    area = slots.area
    items += [
        ChecklistItem(id=i, label=label, required=req, reason=reason)
        for (i, label, req, reason) in _AREA.get(area or "", ())
    ]

    # 조건부 서류 (슬롯 기반)
    if (slots.hospitalization_days or 0) > 0:
        items.append(
            ChecklistItem(
                id="admission_cert",
                label="입·퇴원 확인서",
                required=True,
                reason="입원 사실 확인용입니다.",
            )
        )
    return ClaimChecklist(area=area, items=items)


def build_summary(session: Session) -> ClaimSummary:
    """세션 슬롯 + 마지막 assessment + 체크리스트를 청구 요약으로 집계."""
    s = session.slots
    a = session.last_assessment
    return ClaimSummary(
        insurer=s.insurer,
        product=s.product,
        area=s.area,
        likelihood=a.likelihood if a else None,
        summary=a.summary if a else None,
        satisfied=list(a.satisfied) if a else [],
        unsatisfied=list(a.unsatisfied) if a else [],
        next_steps=list(a.next_steps) if a else [],
        checklist=build_checklist(s).items,
    )


def submit_claim(session: Session) -> ClaimReceipt:
    """청구 접수(가정) — 실제 전송 없이 더미 접수 결과를 반환한다."""
    now = datetime.now(UTC)
    receipt_no = f"CLM-{now.strftime('%Y%m%d')}-{session.session_id[:6].upper()}"
    insurer = session.slots.insurer
    return ClaimReceipt(
        receipt_no=receipt_no,
        submitted_at=now.isoformat(),
        status="접수완료",
        insurer=insurer,
        estimated_days=5,
        message=(
            f"{insurer or '보험사'}에 청구가 접수되었습니다. (데모 — 실제 전송 아님) "
            "영업일 기준 약 5일 내 심사 결과가 안내됩니다."
        ),
    )
