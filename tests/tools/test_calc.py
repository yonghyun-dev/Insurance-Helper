"""tests.tools.test_calc

app/tools/calc.py 단위 테스트.

테스트 대상:
    - calc_claim_amount: 정상/경계값/입력검증/formula 포맷
    - validate_coverage_period: 4가지 reason code / 경계값 / 한국어 메시지

mock 정책:
    - 외부 의존 없음 (deterministic 순수 Python). monkeypatch 불필요.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.shared.tools.calc import (
    ClaimAmountResult,
    CoverageValidation,
    calc_claim_amount,
    validate_coverage_period,
)
from pydantic import ValidationError

# ===========================================================================
# calc_claim_amount — 정상 케이스 (Happy Path)
# ===========================================================================


class TestCalcClaimAmountHappyPath:
    """calc_claim_amount 정상 동작 검증."""

    def test_basic_no_fault_no_deductible(self):
        # Arrange
        loss_amount = 1_000_000
        # Act
        result = calc_claim_amount(loss_amount)
        # Assert
        assert result.paid_amount == 1_000_000
        assert result.loss_amount == 1_000_000
        assert result.fault_ratio == 0
        assert result.deductible == 0

    def test_with_fault_ratio_25_percent(self):
        # Arrange: 손해액 2,000,000 / 과실 25% / 부담금 100,000
        # 기대: 2,000,000 * 0.75 - 100,000 = 1,400,000
        result = calc_claim_amount(
            loss_amount=2_000_000,
            fault_ratio=25,
            deductible=100_000,
        )
        assert result.paid_amount == 1_400_000

    def test_fault_ratio_50_percent(self):
        # 손해액 1,000,000 / 과실 50% → 500,000
        result = calc_claim_amount(loss_amount=1_000_000, fault_ratio=50)
        assert result.paid_amount == 500_000

    def test_large_loss_amount(self):
        # 손해액 10억 / 과실 0% / 부담금 0 → 10억
        result = calc_claim_amount(loss_amount=1_000_000_000)
        assert result.paid_amount == 1_000_000_000

    def test_result_is_claim_amount_result_type(self):
        result = calc_claim_amount(loss_amount=500_000)
        assert isinstance(result, ClaimAmountResult)

    def test_note_is_none_for_normal_case(self):
        result = calc_claim_amount(loss_amount=1_000_000, fault_ratio=20, deductible=50_000)
        # 정상 케이스 — note 없음
        assert result.note is None

    def test_deductible_subtracted_correctly(self):
        # 손해액 500,000 / 과실 0% / 부담금 100,000 → 400,000
        result = calc_claim_amount(loss_amount=500_000, deductible=100_000)
        assert result.paid_amount == 400_000

    def test_various_fault_ratios(self):
        # 여러 과실비율 조합 검증
        cases = [
            (1_000_000, 10, 0, 900_000),
            (1_000_000, 30, 0, 700_000),
            (1_000_000, 75, 0, 250_000),
        ]
        for loss, fault, ded, expected in cases:
            result = calc_claim_amount(loss_amount=loss, fault_ratio=fault, deductible=ded)
            assert result.paid_amount == expected, (
                f"loss={loss}, fault={fault}, ded={ded}: 기대 {expected}, 실제 {result.paid_amount}"
            )


# ===========================================================================
# calc_claim_amount — 경계값 (Boundary)
# ===========================================================================


class TestCalcClaimAmountBoundary:
    """경계값 조건 검증."""

    def test_fault_ratio_zero_no_fault(self):
        # 무과실 (0%) — 손해액 전액 지급
        result = calc_claim_amount(loss_amount=1_000_000, fault_ratio=0)
        assert result.paid_amount == 1_000_000
        assert result.note is None

    def test_fault_ratio_100_full_fault(self):
        # 전과실 (100%) — 지급 0원 + note
        result = calc_claim_amount(loss_amount=1_000_000, fault_ratio=100)
        assert result.paid_amount == 0
        assert result.note is not None
        assert "100%" in result.note or "100" in result.note

    def test_deductible_exceeds_claimable_amount_paid_zero(self):
        # 부담금(500,000) > 손해액 부담분(300,000) → paid = 0 + note
        result = calc_claim_amount(
            loss_amount=300_000,
            fault_ratio=0,
            deductible=500_000,
        )
        assert result.paid_amount == 0
        assert result.note is not None
        assert "자기부담금" in result.note

    def test_deductible_equals_claimable_amount_paid_zero(self):
        # 부담금 = 손해액 부담분 → paid = 0
        result = calc_claim_amount(
            loss_amount=500_000,
            fault_ratio=0,
            deductible=500_000,
        )
        assert result.paid_amount == 0

    def test_loss_amount_zero(self):
        # 손해액 0 → paid = 0
        result = calc_claim_amount(loss_amount=0)
        assert result.paid_amount == 0

    def test_deductible_zero_default(self):
        # 부담금 기본값 0 확인
        result = calc_claim_amount(loss_amount=1_000_000)
        assert result.deductible == 0

    def test_paid_amount_never_negative(self):
        # 어떤 경우에도 paid_amount >= 0
        result = calc_claim_amount(
            loss_amount=100_000,
            fault_ratio=50,
            deductible=1_000_000,
        )
        assert result.paid_amount >= 0


# ===========================================================================
# calc_claim_amount — 입력 검증 (Error Path)
# ===========================================================================


class TestCalcClaimAmountValidation:
    """잘못된 입력에 대한 pydantic ValidationError 검증."""

    def test_negative_loss_amount_raises_validation_error(self):
        with pytest.raises(ValidationError):
            calc_claim_amount(loss_amount=-1)

    def test_fault_ratio_over_100_raises_validation_error(self):
        with pytest.raises(ValidationError):
            calc_claim_amount(loss_amount=1_000_000, fault_ratio=101)

    def test_negative_fault_ratio_raises_validation_error(self):
        with pytest.raises(ValidationError):
            calc_claim_amount(loss_amount=1_000_000, fault_ratio=-1)

    def test_negative_deductible_raises_validation_error(self):
        with pytest.raises(ValidationError):
            calc_claim_amount(loss_amount=1_000_000, deductible=-100)

    def test_fault_ratio_exactly_100_is_valid(self):
        # 100은 유효 (경계)
        result = calc_claim_amount(loss_amount=1_000_000, fault_ratio=100)
        assert result.paid_amount == 0

    def test_fault_ratio_exactly_0_is_valid(self):
        # 0은 유효 (경계)
        result = calc_claim_amount(loss_amount=1_000_000, fault_ratio=0)
        assert result.paid_amount == 1_000_000


# ===========================================================================
# calc_claim_amount — formula 포맷
# ===========================================================================


class TestCalcClaimAmountFormula:
    """formula 문자열 포맷 검증 (천 단위 콤마 + '원')."""

    def test_formula_contains_won_unit(self):
        result = calc_claim_amount(loss_amount=1_000_000)
        assert "원" in result.formula

    def test_formula_uses_comma_separator(self):
        # 천 단위 콤마: 1,000,000 형태 포함
        result = calc_claim_amount(loss_amount=1_000_000)
        assert "1,000,000" in result.formula

    def test_formula_contains_fault_ratio(self):
        result = calc_claim_amount(loss_amount=1_000_000, fault_ratio=25)
        assert "25" in result.formula

    def test_formula_contains_deductible_with_comma(self):
        result = calc_claim_amount(loss_amount=2_000_000, deductible=100_000)
        assert "100,000" in result.formula

    def test_formula_structure(self):
        # formula 에 ×, -, = 연산자 포함 확인
        result = calc_claim_amount(
            loss_amount=2_000_000, fault_ratio=25, deductible=100_000
        )
        assert "×" in result.formula
        assert "-" in result.formula
        assert "=" in result.formula

    def test_formula_paid_amount_with_comma(self):
        # 결과값도 콤마 포맷 확인 (1,400,000원)
        result = calc_claim_amount(
            loss_amount=2_000_000, fault_ratio=25, deductible=100_000
        )
        assert "1,400,000원" in result.formula


# ===========================================================================
# validate_coverage_period — 4가지 reason code
# ===========================================================================


class TestValidateCoveragePeriodReasonCodes:
    """reason code 4종 각각 검증."""

    def test_in_period_returns_valid_true(self):
        # Arrange: 사고일이 보장기간 중간
        result = validate_coverage_period(
            incident_date=date(2026, 5, 15),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        # Assert
        assert result.valid is True
        assert result.reason == "in_period"

    def test_before_start_returns_valid_false(self):
        # 사고일이 보장 시작일 이전
        result = validate_coverage_period(
            incident_date=date(2025, 12, 31),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert result.valid is False
        assert result.reason == "before_start"

    def test_after_end_returns_valid_false(self):
        # 사고일이 보장 만료일 이후
        result = validate_coverage_period(
            incident_date=date(2027, 1, 1),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert result.valid is False
        assert result.reason == "after_end"

    def test_invalid_period_when_end_before_start(self):
        # 보장 만료일이 시작일보다 빠름
        result = validate_coverage_period(
            incident_date=date(2026, 5, 15),
            policy_start_date=date(2026, 12, 31),
            policy_end_date=date(2026, 1, 1),
        )
        assert result.valid is False
        assert result.reason == "invalid_period"

    def test_result_is_coverage_validation_type(self):
        result = validate_coverage_period(
            incident_date=date(2026, 5, 15),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert isinstance(result, CoverageValidation)


# ===========================================================================
# validate_coverage_period — 경계값
# ===========================================================================


class TestValidateCoveragePeriodBoundary:
    """사고일 = 시작일 / 사고일 = 만료일 경계 포함 검증."""

    def test_incident_date_equals_policy_start_is_valid(self):
        # 사고일 = 시작일 → 포함 (in_period)
        result = validate_coverage_period(
            incident_date=date(2026, 1, 1),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert result.valid is True
        assert result.reason == "in_period"

    def test_incident_date_equals_policy_end_is_valid(self):
        # 사고일 = 만료일 → 포함 (in_period)
        result = validate_coverage_period(
            incident_date=date(2026, 12, 31),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert result.valid is True
        assert result.reason == "in_period"

    def test_one_day_before_start_is_before_start(self):
        # 시작일 하루 전 → before_start
        result = validate_coverage_period(
            incident_date=date(2025, 12, 31),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert result.reason == "before_start"

    def test_one_day_after_end_is_after_end(self):
        # 만료일 하루 후 → after_end
        result = validate_coverage_period(
            incident_date=date(2027, 1, 1),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert result.reason == "after_end"

    def test_same_start_and_end_date_valid(self):
        # 보장기간이 하루인 경우, 당일 사고 → in_period
        result = validate_coverage_period(
            incident_date=date(2026, 6, 1),
            policy_start_date=date(2026, 6, 1),
            policy_end_date=date(2026, 6, 1),
        )
        assert result.valid is True
        assert result.reason == "in_period"

    def test_date_fields_preserved_in_result(self):
        # 결과에 입력 날짜값이 그대로 보존됨
        incident = date(2026, 5, 15)
        start = date(2026, 1, 1)
        end = date(2026, 12, 31)
        result = validate_coverage_period(incident, start, end)
        assert result.incident_date == incident
        assert result.policy_start_date == start
        assert result.policy_end_date == end


# ===========================================================================
# validate_coverage_period — 한국어 메시지 포함
# ===========================================================================


class TestValidateCoveragePeriodMessages:
    """메시지에 한국어 문구 포함 여부 검증."""

    def test_in_period_message_contains_korean(self):
        result = validate_coverage_period(
            incident_date=date(2026, 5, 15),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert "청구" in result.message or "보장기간" in result.message

    def test_before_start_message_contains_korean(self):
        result = validate_coverage_period(
            incident_date=date(2025, 12, 31),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert "가입" in result.message or "이전" in result.message

    def test_after_end_message_contains_korean(self):
        result = validate_coverage_period(
            incident_date=date(2027, 1, 1),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert "만료" in result.message or "이후" in result.message

    def test_invalid_period_message_contains_korean(self):
        result = validate_coverage_period(
            incident_date=date(2026, 5, 15),
            policy_start_date=date(2026, 12, 31),
            policy_end_date=date(2026, 1, 1),
        )
        assert "유효하지 않" in result.message or "보장기간" in result.message

    def test_message_contains_incident_date_string(self):
        # 메시지에 사고일 날짜 문자열이 포함됨
        result = validate_coverage_period(
            incident_date=date(2026, 5, 15),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert "2026-05-15" in result.message

    def test_message_is_nonempty_string(self):
        result = validate_coverage_period(
            incident_date=date(2026, 5, 15),
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
        )
        assert isinstance(result.message, str)
        assert len(result.message) > 0
