"""준비도 스코어(결정론) — 배점·경계·불변식 검증 (Sprint 37)."""

from __future__ import annotations

import pytest
from app.domains.sessions.readiness import compute_readiness


class TestComputeReadiness:
    def test_best_case_full(self):
        r = compute_readiness("높음", ["a", "b", "c"], [], "full")
        assert r.score == 100
        assert r.level == "high"

    def test_worst_case(self):
        r = compute_readiness("낮음", [], ["a", "b"], "partial")
        assert r.score == 15 + 0 + 5 == 20
        assert r.level == "low"

    def test_mid_case(self):
        r = compute_readiness("중간", ["a"], ["b"], "partial")
        assert r.score == 35 + 15 + 5 == 55
        assert r.level == "medium"

    def test_no_requirement_list_is_neutral(self):
        r = compute_readiness("높음", [], [], "full")
        assert r.score == 55 + 15 + 15 == 85

    @pytest.mark.parametrize("likelihood", ["높음", "중간", "낮음"])
    def test_factors_sum_equals_score(self, likelihood):
        r = compute_readiness(likelihood, ["a", "b"], ["c"], "full")
        assert sum(f.points for f in r.factors) == r.score
        assert sum(f.max_points for f in r.factors) == 100

    def test_caption_is_not_payout_probability(self):
        r = compute_readiness("높음", [], [], "full")
        assert "지급 확률이 아닙니다" in r.caption

    def test_unknown_likelihood_defaults_low(self):
        r = compute_readiness("모름", [], [], "partial")
        assert r.factors[0].points == 15
