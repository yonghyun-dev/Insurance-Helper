

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
