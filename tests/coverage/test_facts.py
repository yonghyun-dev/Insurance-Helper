

class TestPurposeMapping:
    """purpose 는 뉴럴 추출(enum) → _map_purpose → 심볼릭 룰. 키워드 폴백 없음(Sprint 37)."""

    def test_enum_values_map(self):
        from app.domains.coverage import build_facts_from_slots
        from app.domains.coverage.schemas import ClaimPurpose
        from app.domains.sessions.schemas import SlotState

        for raw, expected in [
            ("cosmetic", ClaimPurpose.COSMETIC),
            ("preventive", ClaimPurpose.PREVENTIVE),
            ("pregnancy", ClaimPurpose.PREGNANCY),
            ("treatment", ClaimPurpose.TREATMENT),
            (None, ClaimPurpose.TREATMENT),
            ("garbage", ClaimPurpose.TREATMENT),
        ]:
            facts = build_facts_from_slots(SlotState(area="accident_disease", purpose=raw))
            assert facts.purpose == expected

    def test_cosmetic_purpose_triggers_exclusion(self):
        """뉴럴이 purpose=cosmetic 을 채우면 심볼릭 룰이 면책 판정 (죽은 필드 → 살아있는 경로)."""
        from app.domains.coverage import build_facts_from_slots
        from app.domains.coverage import evaluate as evaluate_coverage
        from app.domains.coverage.schemas import CoverageOutcome
        from app.domains.sessions.schemas import SlotState

        facts = build_facts_from_slots(
            SlotState(area="accident_disease", insurer_id="samsung", purpose="cosmetic")
        )
        assert evaluate_coverage(facts).outcome == CoverageOutcome.EXCLUDED

    def test_all_six_purpose_exclusions_reachable(self):
        """PM-43 T1.1 — 6종 purpose enum 전부 뉴럴 추출→심볼릭 발화 가능(죽은 룰 0).

        특히 self_harm/crime_war 는 이전에 extract enum 이 4종뿐이라 절대 발화 못 했다.
        """
        from app.domains.coverage import build_facts_from_slots
        from app.domains.coverage import evaluate as evaluate_coverage
        from app.domains.coverage.schemas import CoverageOutcome
        from app.domains.sessions import llm
        from app.domains.sessions.schemas import SlotState

        enum = llm._EXTRACT_SLOTS_TOOL["parameters"]["properties"]["slot_updates"][
            "properties"
        ]["purpose"]["enum"]
        assert set(enum) == {
            "treatment", "cosmetic", "preventive", "pregnancy", "self_harm", "crime_war"
        }
        for purpose in ("cosmetic", "preventive", "pregnancy", "self_harm", "crime_war"):
            facts = build_facts_from_slots(
                SlotState(area="accident_disease", insurer_id="samsung", purpose=purpose)
            )
            assert evaluate_coverage(facts).outcome == CoverageOutcome.EXCLUDED, purpose


class TestPartialCoverageRules:
    """PM-43 coverage 모델링 — 한방/해외/치과질병/산재 부분보상(CONDITIONAL). 약관 근거 기반."""

    def _facts(self, **over):
        from app.domains.coverage import build_facts_from_slots
        from app.domains.sessions.schemas import SlotState

        base = dict(area="accident_disease", insurer_id="samsung",
                    diagnosis="치료", hospitalization_days=2)
        return build_facts_from_slots(SlotState(**{**base, **over}))

    def test_oriental_medicine_conditional(self):
        from app.domains.coverage import evaluate as ev
        from app.domains.coverage.schemas import CoverageOutcome

        r = ev(self._facts(is_oriental_medicine=True))
        assert r.outcome == CoverageOutcome.CONDITIONAL
        assert r.hits[0].rule_id == "partial_oriental_medicine"
        assert "한방" in r.hits[0].clause_ref or "한의사" in r.hits[0].clause_ref

    def test_overseas_conditional(self):
        from app.domains.coverage import evaluate as ev
        from app.domains.coverage.schemas import CoverageOutcome

        r = ev(self._facts(treatment_overseas=True))
        assert r.outcome == CoverageOutcome.CONDITIONAL
        assert r.hits[0].rule_id == "partial_overseas"

    def test_dental_disease_conditional(self):
        from app.domains.coverage import evaluate as ev
        from app.domains.coverage.schemas import CoverageOutcome

        r = ev(self._facts(dental_disease=True))
        assert r.outcome == CoverageOutcome.CONDITIONAL
        assert "K00" in r.hits[0].clause_ref

    def test_other_insurance_conditional(self):
        from app.domains.coverage import evaluate as ev
        from app.domains.coverage.schemas import CoverageOutcome

        r = ev(self._facts(other_insurance_settled=True))
        assert r.outcome == CoverageOutcome.CONDITIONAL
        assert r.hits[0].rule_id == "partial_other_insurance"

    def test_plain_treatment_still_covered(self):
        """대조군 — 정황 없으면 기본 보장(covered), 부분보상 룰 오발화 없음."""
        from app.domains.coverage import evaluate as ev
        from app.domains.coverage.schemas import CoverageOutcome

        assert ev(self._facts()).outcome == CoverageOutcome.COVERED

    def test_exclusion_precedes_partial(self):
        """전면 면책(고의 자해)이 부분보상보다 우선 — 엔진 순서 검증."""
        from app.domains.coverage import evaluate as ev
        from app.domains.coverage.schemas import CoverageOutcome

        r = ev(self._facts(purpose="self_harm", is_oriental_medicine=True))
        assert r.outcome == CoverageOutcome.EXCLUDED

    def test_slot_wiring_reaches_facts(self):
        """SlotState → build_facts → ClaimFacts 배선 무결성(뉴럴이 채운 값 전달)."""
        f = self._facts(is_oriental_medicine=True, treatment_overseas=True)
        assert f.is_oriental_medicine is True
        assert f.treatment_overseas is True
