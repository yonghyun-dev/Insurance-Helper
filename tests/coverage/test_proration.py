"""tests.coverage.test_proration — 다중 실손 비례분담/비교 (Sprint 33 L3)."""

from __future__ import annotations

from app.domains.coverage.proration import compute
from app.domains.coverage.schemas import (
    CoverageAssessment,
    CoverageOutcome,
    DeductibleBreakdown,
)


def _cov(outcome: CoverageOutcome, payable: int | None = None) -> CoverageAssessment:
    ded = (
        DeductibleBreakdown(charged_amount=payable * 2, deductible=payable, payable_estimate=payable, formula="t")
        if payable is not None
        else None
    )
    return CoverageAssessment(outcome=outcome, deductible=ded)


class TestDeductibleView:
    def test_generation_rates_reflected(self):
        # 4세대(비급여 30%) vs 2세대(비급여 20%)
        res = compute([
            ("P4", 4, _cov(CoverageOutcome.COVERED)),
            ("P2", 2, _cov(CoverageOutcome.COVERED)),
        ])
        assert res.per_policy["P4"].non_covered_rate == 0.3
        assert res.per_policy["P2"].non_covered_rate == 0.2

    def test_unknown_generation_assumes_4th(self):
        res = compute([("P", None, _cov(CoverageOutcome.COVERED)),
                       ("Q", 3, _cov(CoverageOutcome.COVERED))])
        assert res.per_policy["P"].non_covered_rate == 0.3  # 4세대 가정


class TestRecommendation:
    def test_recommends_lower_deductible_among_covered(self):
        res = compute([
            ("HIGH", 4, _cov(CoverageOutcome.COVERED)),  # 비급여 30%
            ("LOW", 2, _cov(CoverageOutcome.COVERED)),   # 비급여 20%
        ])
        assert res.recommended_policy_no == "LOW"

    def test_excluded_policy_not_recommended(self):
        res = compute([
            ("EXC", 2, _cov(CoverageOutcome.EXCLUDED)),   # 자기부담 더 낮지만 면책
            ("COV", 4, _cov(CoverageOutcome.COVERED)),
        ])
        assert res.recommended_policy_no == "COV"

    def test_generation_diff_mentioned(self):
        res = compute([("A", 4, _cov(CoverageOutcome.COVERED)),
                       ("B", 2, _cov(CoverageOutcome.COVERED))])
        assert "세대" in res.summary


class TestProration:
    def test_numeric_split_when_amounts_present(self):
        # payable 60000 + 40000 → 총 100000 기준 비례
        res = compute([
            ("A", 4, _cov(CoverageOutcome.COVERED, 60000)),
            ("B", 4, _cov(CoverageOutcome.COVERED, 40000)),
        ])
        a, b = res.per_policy["A"].prorated_share, res.per_policy["B"].prorated_share
        assert a is not None and b is not None
        assert a + b <= 60000 + 40000  # 총액 한도
        assert a > b  # 보상책임 큰 쪽이 더 많이 분담

    def test_no_numeric_split_without_amounts(self):
        res = compute([("A", 4, _cov(CoverageOutcome.COVERED)),
                       ("B", 3, _cov(CoverageOutcome.COVERED))])
        assert res.per_policy["A"].prorated_share is None
        assert "비례로 나눠" in res.summary  # 설명은 항상 제공

    def test_excluded_not_in_proration(self):
        res = compute([
            ("COV", 4, _cov(CoverageOutcome.COVERED, 50000)),
            ("EXC", 3, _cov(CoverageOutcome.EXCLUDED, 50000)),
        ])
        # 면책 계약은 안분 대상 아님 → 단독이면 안분 없음
        assert res.per_policy["EXC"].prorated_share is None
