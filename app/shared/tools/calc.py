"""app.shared.tools.calc

파일 경로: app/tools/calc.py
목적: deterministic Python tool — LLM 산수/날짜 환각 차단.

Sprint 10 신규 — 뉴로심볼릭 아키텍처의 symbolic 부분.

주요 함수:
    - calc_claim_amount(loss_amount, fault_ratio, deductible) -> ClaimAmountResult
    - validate_coverage_period(incident_date, policy_start, policy_end) -> CoverageValidation

설계 참고:
    - docs/design/agent-architecture.md § 3.3 tool 카탈로그
    - docs/design/tech-decisions.md § Sprint 8~11 결정 (deterministic tool 정당성)

원칙:
    - LLM 호출 0건 — 순수 Python 산수/날짜
    - 모든 입력은 pydantic 검증 (잘못된 입력 → ValidationError → router 가 처리)
    - 결과는 dict 가 아닌 pydantic 모델 (Sprint 11 dispatcher 가 JSON 직렬화)
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# calc_claim_amount
# ---------------------------------------------------------------------------


class ClaimAmountResult(BaseModel):
    """보험금 산정 결과.

    공식: paid_amount = max(0, loss_amount * (1 - fault_ratio/100) - deductible)
    """

    model_config = ConfigDict(extra="forbid")

    paid_amount: int = Field(ge=0, description="지급 보험금 (원)")
    loss_amount: int = Field(ge=0, description="입력 손해액 (원)")
    fault_ratio: int = Field(ge=0, le=100, description="입력 과실비율 (0~100)")
    deductible: int = Field(ge=0, description="입력 자기부담금 (원)")
    formula: str = Field(description="적용한 산정 공식 (사용자에게 표시)")
    note: str | None = Field(
        default=None, description="특이사항 (예: 자기부담금이 더 커서 지급 0)"
    )


def calc_claim_amount(
    loss_amount: int,
    fault_ratio: int = 0,
    deductible: int = 0,
) -> ClaimAmountResult:
    """보험금 deterministic 산정.

    Args:
        loss_amount: 손해액 (원, ≥0)
        fault_ratio: 본인 과실비율 (0~100). 기본 0 (피보험자 무과실)
        deductible: 자기부담금 (원, ≥0). 기본 0

    Returns:
        ClaimAmountResult — paid_amount + 산정 내역

    Raises:
        pydantic ValidationError: 입력 범위 위반

    예시:
        >>> r = calc_claim_amount(2_000_000, fault_ratio=25, deductible=100_000)
        >>> r.paid_amount
        1400000  # = 2000000 * 0.75 - 100000
    """
    # pydantic 으로 입력 검증 (negative / >100 등 차단)
    _Input(loss_amount=loss_amount, fault_ratio=fault_ratio, deductible=deductible)

    base = loss_amount * (100 - fault_ratio) // 100
    paid = max(0, base - deductible)

    note: str | None = None
    if paid == 0 and base > 0:
        note = "자기부담금이 손해액 부담분보다 커서 지급액 0원"
    elif fault_ratio == 100:
        note = "본인 과실 100% — 지급액 0원"

    return ClaimAmountResult(
        paid_amount=paid,
        loss_amount=loss_amount,
        fault_ratio=fault_ratio,
        deductible=deductible,
        formula=f"{loss_amount:,} × (1 - {fault_ratio}/100) - {deductible:,} = {paid:,}원",
        note=note,
    )


class _Input(BaseModel):
    """calc_claim_amount 입력 검증 내부 모델."""

    model_config = ConfigDict(extra="forbid")

    loss_amount: int = Field(ge=0)
    fault_ratio: int = Field(ge=0, le=100)
    deductible: int = Field(ge=0)


# ---------------------------------------------------------------------------
# validate_coverage_period
# ---------------------------------------------------------------------------


class CoverageValidation(BaseModel):
    """보장기간 유효성 검증 결과."""

    model_config = ConfigDict(extra="forbid")

    valid: bool = Field(description="사고일이 보장기간 안에 있는가")
    reason: Literal[
        "in_period", "before_start", "after_end", "invalid_period"
    ] = Field(description="판정 사유 코드")
    message: str = Field(description="사용자에게 표시할 한국어 메시지")
    incident_date: date
    policy_start_date: date
    policy_end_date: date


def validate_coverage_period(
    incident_date: date,
    policy_start_date: date,
    policy_end_date: date,
) -> CoverageValidation:
    """사고일이 보장기간 (policy_start ~ policy_end) 안에 있는지 deterministic 검증.

    LLM 의 날짜 계산 환각 차단. 보장기간 양 끝(시작일·만료일) 포함.

    Args:
        incident_date: 사고 발생일
        policy_start_date: 보장 시작일
        policy_end_date: 보장 만료일

    Returns:
        CoverageValidation — valid 여부 + 사유 + 사용자 메시지

    예시:
        >>> from datetime import date
        >>> r = validate_coverage_period(date(2026, 5, 1), date(2026, 1, 1), date(2026, 12, 31))
        >>> r.valid
        True
        >>> r.reason
        'in_period'
    """
    # 입력 검증 (policy_end >= policy_start)
    if policy_end_date < policy_start_date:
        return CoverageValidation(
            valid=False,
            reason="invalid_period",
            message=(
                f"보장기간이 유효하지 않습니다 (만료일 {policy_end_date} 이 "
                f"시작일 {policy_start_date} 보다 빠릅니다). 가입 정보를 확인해 주세요."
            ),
            incident_date=incident_date,
            policy_start_date=policy_start_date,
            policy_end_date=policy_end_date,
        )

    if incident_date < policy_start_date:
        return CoverageValidation(
            valid=False,
            reason="before_start",
            message=(
                f"사고일 {incident_date} 이 보장 시작일 {policy_start_date} 이전입니다. "
                f"가입 전 사고는 청구 대상이 아닙니다."
            ),
            incident_date=incident_date,
            policy_start_date=policy_start_date,
            policy_end_date=policy_end_date,
        )

    if incident_date > policy_end_date:
        return CoverageValidation(
            valid=False,
            reason="after_end",
            message=(
                f"사고일 {incident_date} 이 보장 만료일 {policy_end_date} 이후입니다. "
                f"보장기간이 지난 사고는 청구 대상이 아닙니다."
            ),
            incident_date=incident_date,
            policy_start_date=policy_start_date,
            policy_end_date=policy_end_date,
        )

    return CoverageValidation(
        valid=True,
        reason="in_period",
        message=(
            f"사고일 {incident_date} 이 보장기간 "
            f"({policy_start_date} ~ {policy_end_date}) 안에 있어 청구 대상입니다."
        ),
        incident_date=incident_date,
        policy_start_date=policy_start_date,
        policy_end_date=policy_end_date,
    )
