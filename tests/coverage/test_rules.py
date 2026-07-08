"""tests.coverage.test_rules

규칙 scope 필터링 + SlotState→ClaimFacts 매퍼 회귀 — PM-35 Phase 1.
"""

from __future__ import annotations

from datetime import date

from app.domains.coverage.facts import build_facts_from_slots
from app.domains.coverage.rules import RuleScope, rules_for
from app.domains.coverage.schemas import ClaimFacts, ClaimPurpose, TreatmentType
from app.domains.sessions.schemas import SlotState


def _facts(**kw) -> ClaimFacts:
    base = {"insurer_id": "samsung", "generation": 4}
    base.update(kw)
    return ClaimFacts(**base)


class TestRuleScope:
    def test_generation_scope_matches(self):
        scope = RuleScope(generations=frozenset({4}))
        assert scope.applies_to(_facts(generation=4)) is True
        assert scope.applies_to(_facts(generation=2)) is False

    def test_insurer_scope_matches(self):
        scope = RuleScope(insurers=frozenset({"samsung"}))
        assert scope.applies_to(_facts(insurer_id="samsung")) is True
        assert scope.applies_to(_facts(insurer_id="hyundai")) is False

    def test_unknown_generation_uses_effective_4(self):
        # generation=None → effective_generation=4 로 scope 판정
        scope = RuleScope(generations=frozenset({4}))
        assert scope.applies_to(_facts(generation=None)) is True

    def test_effective_period_by_incident_date(self):
        scope = RuleScope(effective_from=date(2021, 7, 1))  # 4세대 시행일
        assert scope.applies_to(_facts(incident_date=date(2026, 1, 1))) is True
        assert scope.applies_to(_facts(incident_date=date(2020, 1, 1))) is False


class TestRulesFor:
    def test_returns_seed_rules_for_silson(self):
        applicable = rules_for(_facts())
        ids = {r.id for r in applicable}
        assert "basis_treatment" in ids
        assert "exc_cosmetic" in ids
        assert "period_out_of_coverage" in ids

    def test_sorted_by_priority(self):
        applicable = rules_for(_facts())
        priorities = [r.priority for r in applicable]
        assert priorities == sorted(priorities)


class TestFactsMapper:
    def test_hospitalization_infers_inpatient(self):
        slots = SlotState(area="accident_disease", hospitalization_days=3)
        f = build_facts_from_slots(slots)
        assert f.treatment_type == TreatmentType.INPATIENT

    def test_outpatient_visits_infers_outpatient(self):
        slots = SlotState(area="accident_disease", outpatient_visits=2)
        f = build_facts_from_slots(slots)
        assert f.treatment_type == TreatmentType.OUTPATIENT

    def test_no_treatment_signal_is_none(self):
        slots = SlotState(area="accident_disease")
        f = build_facts_from_slots(slots)
        assert f.treatment_type is None

    def test_maps_insurer_and_amount_and_purpose(self):
        slots = SlotState(insurer_id="hyundai", claim_amount=500_000)
        f = build_facts_from_slots(slots, generation=3, purpose=ClaimPurpose.COSMETIC)
        assert f.insurer_id == "hyundai"
        assert f.charged_amount == 500_000
        assert f.generation == 3
        assert f.purpose == ClaimPurpose.COSMETIC
