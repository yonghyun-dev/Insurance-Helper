"""보험사 단일 소스(app.shared.insurers) — PM-43 Tier 2 통합 검증."""

from __future__ import annotations

from app.shared import insurers


class TestInsurersSingleSource:
    def test_five_silson_insurers(self):
        assert insurers.all_codes() == ["samsung", "hyundai", "meritz", "hanwha", "lotte"]
        assert "삼성화재" in insurers.all_names()

    def test_name_to_code_exact_and_alias(self):
        assert insurers.name_to_code("삼성화재") == "samsung"
        assert insurers.name_to_code("삼성") == "samsung"
        assert insurers.name_to_code("한화손해보험") == "hanwha"
        assert insurers.name_to_code("한화") == "hanwha"

    def test_name_to_code_space_normalized(self):
        assert insurers.name_to_code("한화 손해보험") == "hanwha"

    def test_name_to_code_substring_fallback_prefers_longer(self):
        assert insurers.name_to_code("삼성생명보험") == "samsung"

    def test_name_to_code_unknown_none(self):
        assert insurers.name_to_code("DB손해보험") is None
        assert insurers.name_to_code(None) is None

    def test_code_to_name(self):
        assert insurers.code_to_name("hanwha") == "한화손해보험"
        assert insurers.code_to_name("unknown") is None

    def test_consumers_derive_from_single_source(self):
        from app.domains.rag._slots import insurer_display_name, insurer_to_code
        from app.infrastructure.external.mydata.adapter import _INSURER_NAME_PATTERNS

        assert insurer_to_code("메리츠화재") == "meritz"
        assert insurer_display_name("lotte") == "롯데손해보험"
        codes_in_patterns = {c for _, c, _ in _INSURER_NAME_PATTERNS}
        assert codes_in_patterns == set(insurers.all_codes())
