"""tests.tools.test_calc

app/tools/calc.py 단위 테스트.

테스트 대상:
    - validate_coverage_period: 4가지 reason code / 경계값 / 한국어 메시지

mock 정책:
    - 외부 의존 없음 (deterministic 순수 Python). monkeypatch 불필요.
"""

from __future__ import annotations

from datetime import date

from app.shared.tools.calc import (
    CoverageValidation,
    validate_coverage_period,
)

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
