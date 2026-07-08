"""tests.coverage.test_engine

실손 보장 판정 엔진(심볼릭)의 결정론 회귀 — PM-35 Phase 1.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.domains.coverage.engine import evaluate
from app.domains.coverage.schemas import (
    ClaimFacts,
    ClaimPurpose,
    CoverageOutcome,
    TreatmentType,
)


def _facts(**kw) -> ClaimFacts:
    base = dict(
        insurer_id="samsung",
        generation=4,
        treatment_type=TreatmentType.INPATIENT,
        purpose=ClaimPurpose.TREATMENT,
    )
    base.update(kw)
    return ClaimFacts(**base)


class TestCoveredBasis:
    def test_treatment_inpatient_is_covered(self):
        r = evaluate(_facts())
        assert r.outcome == CoverageOutcome.COVERED
        assert any(h.rule_id == "basis_treatment" for h in r.hits)
        assert r.hits[0].clause_ref  # 근거 조항 부착

    def test_outpatient_treatment_covered(self):
        r = evaluate(_facts(treatment_type=TreatmentType.OUTPATIENT, outpatient_visits=2))
        assert r.outcome == CoverageOutcome.COVERED

    def test_prescription_only_is_conditional(self):
        # 처방조제만 — 기본 보장 요건과 달라 조건부
        r = evaluate(_facts(treatment_type=TreatmentType.PRESCRIPTION))
        assert r.outcome == CoverageOutcome.CONDITIONAL


class TestExclusions:
    @pytest.mark.parametrize(
        "purpose,rule_id",
        [
            (ClaimPurpose.COSMETIC, "exc_cosmetic"),
            (ClaimPurpose.PREVENTIVE, "exc_preventive"),
            (ClaimPurpose.PREGNANCY, "exc_pregnancy"),
            (ClaimPurpose.SELF_HARM, "exc_self_harm"),
            (ClaimPurpose.CRIME_WAR, "exc_crime_war"),
        ],
    )
    def test_purpose_exclusions(self, purpose, rule_id):
        r = evaluate(_facts(purpose=purpose))
        assert r.outcome == CoverageOutcome.EXCLUDED
        assert any(h.rule_id == rule_id for h in r.hits)
        assert r.hits[0].clause_ref


class TestCoveragePeriod:
    def test_incident_before_period_excluded(self):
        r = evaluate(
            _facts(
                incident_date=date(2025, 1, 1),
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
            )
        )
        assert r.outcome == CoverageOutcome.EXCLUDED
        assert r.hits[0].rule_id == "period_out_of_coverage"

    def test_incident_in_period_not_blocked(self):
        r = evaluate(
            _facts(
                incident_date=date(2026, 6, 1),
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
            )
        )
        assert r.outcome == CoverageOutcome.COVERED

    def test_period_takes_priority_over_exclusion(self):
        # 보장기간 밖이면 목적과 무관하게 하드 배제(우선순위)
        r = evaluate(
            _facts(
                purpose=ClaimPurpose.COSMETIC,
                incident_date=date(2025, 1, 1),
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
            )
        )
        assert r.hits[0].rule_id == "period_out_of_coverage"


class TestInsufficientInfo:
    def test_no_treatment_type_is_insufficient(self):
        r = evaluate(_facts(treatment_type=None))
        assert r.outcome == CoverageOutcome.INSUFFICIENT_INFO
        assert "treatment_type" in r.missing


class TestDeductible:
    def test_gen4_inpatient_deductible(self):
        # 급여 100만(20%) + 비급여 100만(30%) = 공제 50만, 청구가능 150만
        r = evaluate(
            _facts(covered_amount=1_000_000, non_covered_amount=1_000_000)
        )
        assert r.outcome == CoverageOutcome.COVERED
        assert r.deductible is not None
        assert r.deductible.deductible == 500_000
        assert r.deductible.payable_estimate == 1_500_000

    def test_gen4_outpatient_min_copay(self):
        # 비급여 10만 통원, 4세대 최소공제 3만 적용 → 공제 3만, 청구가능 7만
        r = evaluate(
            _facts(
                treatment_type=TreatmentType.OUTPATIENT,
                outpatient_visits=1,
                covered_amount=0,
                non_covered_amount=100_000,
            )
        )
        assert r.deductible.deductible == 30_000
        assert r.deductible.payable_estimate == 70_000

    def test_generation_changes_rate(self):
        # 동일 금액이라도 2세대(비급여 20%)와 4세대(30%)의 공제가 다르다
        g4 = evaluate(_facts(generation=4, covered_amount=0, non_covered_amount=1_000_000))
        g2 = evaluate(_facts(generation=2, covered_amount=0, non_covered_amount=1_000_000))
        assert g4.deductible.deductible == 300_000
        assert g2.deductible.deductible == 200_000

    def test_covered_without_amount_flags_missing(self):
        # 금액 정보 없음 → 보장은 성립하나 공제 계산 보류 + missing
        r = evaluate(_facts())
        assert r.outcome == CoverageOutcome.COVERED
        assert r.deductible is None
        assert "benefit_split" in r.missing


class TestNeedsGeneration:
    def test_unknown_generation_flags(self):
        r = evaluate(_facts(generation=None))
        assert r.needs_generation is True

    def test_known_generation_no_flag(self):
        r = evaluate(_facts(generation=4))
        assert r.needs_generation is False
