

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
