"""tests.tools.test_definitions

app/tools/definitions.py 단위 테스트.

테스트 대상:
    - ALL_TOOLS 8개 — OpenAI Function Calling 스키마 준수 (type/function/name/description/parameters)
    - TOOLS_BY_AREA 3 영역 — mandatory/recommended 키 + 값이 tool_names() 안에 있는지
    - tool_names() 헬퍼 — 8개 이름 반환
    - tools_for_area() 헬퍼 — 각 영역 dict 반환

mock 정책:
    - 외부 의존 없음 (constants/helper 함수만). monkeypatch 불필요.
"""

from __future__ import annotations

import pytest
from app.shared.tools.definitions import (
    ALL_TOOLS,
    CALC_CLAIM_AMOUNT,
    FINISH,
    GET_DISEASE_CODE,
    GET_FAULT_RATIO_STANDARD,
    GET_PRODUCT_META,
    LOOKUP_LAW_CLAUSE,
    SEARCH_TERMS,
    TOOLS_BY_AREA,
    VALIDATE_COVERAGE_PERIOD,
    tool_names,
    tools_for_area,
)

# 예상 tool 이름 8개
EXPECTED_TOOL_NAMES = {
    "search_terms",
    "lookup_law_clause",
    "get_disease_code",
    "get_fault_ratio_standard",
    "get_product_meta",
    "calc_claim_amount",
    "validate_coverage_period",
    "finish",
}


# ===========================================================================
# ALL_TOOLS — 전체 카탈로그 검증
# ===========================================================================


class TestAllToolsCount:
    """ALL_TOOLS 개수 및 기본 구조 검증."""

    def test_all_tools_has_8_items(self):
        assert len(ALL_TOOLS) == 8

    def test_all_tools_is_list(self):
        assert isinstance(ALL_TOOLS, list)

    def test_all_tool_names_are_unique(self):
        names = [t["function"]["name"] for t in ALL_TOOLS]
        assert len(names) == len(set(names)), "중복 tool 이름 존재"

    def test_all_expected_tool_names_present(self):
        names = set(t["function"]["name"] for t in ALL_TOOLS)
        assert names == EXPECTED_TOOL_NAMES


# ===========================================================================
# ALL_TOOLS — OpenAI Function Calling 스키마 준수
# ===========================================================================


class TestToolSchemaCompliance:
    """각 tool 이 OpenAI Function Calling 스키마를 준수하는지 검증."""

    @pytest.mark.parametrize("tool_def", ALL_TOOLS, ids=lambda t: t["function"]["name"])
    def test_tool_has_type_function(self, tool_def):
        assert tool_def.get("type") == "function"

    @pytest.mark.parametrize("tool_def", ALL_TOOLS, ids=lambda t: t["function"]["name"])
    def test_tool_has_function_key(self, tool_def):
        assert "function" in tool_def

    @pytest.mark.parametrize("tool_def", ALL_TOOLS, ids=lambda t: t["function"]["name"])
    def test_tool_has_name(self, tool_def):
        assert "name" in tool_def["function"]
        assert isinstance(tool_def["function"]["name"], str)
        assert len(tool_def["function"]["name"]) > 0

    @pytest.mark.parametrize("tool_def", ALL_TOOLS, ids=lambda t: t["function"]["name"])
    def test_tool_has_description(self, tool_def):
        assert "description" in tool_def["function"]
        assert isinstance(tool_def["function"]["description"], str)
        assert len(tool_def["function"]["description"]) > 0

    @pytest.mark.parametrize("tool_def", ALL_TOOLS, ids=lambda t: t["function"]["name"])
    def test_tool_has_parameters(self, tool_def):
        assert "parameters" in tool_def["function"]

    @pytest.mark.parametrize("tool_def", ALL_TOOLS, ids=lambda t: t["function"]["name"])
    def test_parameters_has_type_object(self, tool_def):
        params = tool_def["function"]["parameters"]
        assert params.get("type") == "object"

    @pytest.mark.parametrize("tool_def", ALL_TOOLS, ids=lambda t: t["function"]["name"])
    def test_parameters_has_properties(self, tool_def):
        params = tool_def["function"]["parameters"]
        assert "properties" in params
        assert isinstance(params["properties"], dict)


# ===========================================================================
# 개별 tool — required 필드 검증
# ===========================================================================


class TestIndividualToolRequired:
    """각 tool 의 required 필드가 올바른지 검증."""

    def test_search_terms_requires_query(self):
        params = SEARCH_TERMS["function"]["parameters"]
        assert "query" in params["required"]

    def test_lookup_law_clause_requires_law_name_and_keyword(self):
        params = LOOKUP_LAW_CLAUSE["function"]["parameters"]
        assert "law_name" in params["required"]
        assert "keyword_or_article" in params["required"]

    def test_get_disease_code_requires_diagnosis_korean(self):
        params = GET_DISEASE_CODE["function"]["parameters"]
        assert "diagnosis_korean" in params["required"]

    def test_get_fault_ratio_standard_requires_scenario_keyword(self):
        params = GET_FAULT_RATIO_STANDARD["function"]["parameters"]
        assert "scenario_keyword" in params["required"]

    def test_get_product_meta_requires_insurer_and_product_name(self):
        params = GET_PRODUCT_META["function"]["parameters"]
        assert "insurer" in params["required"]
        assert "product_name" in params["required"]

    def test_calc_claim_amount_requires_loss_amount(self):
        params = CALC_CLAIM_AMOUNT["function"]["parameters"]
        assert "loss_amount" in params["required"]

    def test_validate_coverage_period_requires_all_three_dates(self):
        params = VALIDATE_COVERAGE_PERIOD["function"]["parameters"]
        required = params["required"]
        assert "incident_date" in required
        assert "policy_start_date" in required
        assert "policy_end_date" in required

    def test_finish_requires_reason(self):
        params = FINISH["function"]["parameters"]
        assert "reason" in params["required"]


# ===========================================================================
# TOOLS_BY_AREA — 3 영역 검증
# ===========================================================================


class TestToolsByArea:
    """TOOLS_BY_AREA 영역별 mandatory/recommended 검증."""

    def test_tools_by_area_has_three_areas(self):
        assert set(TOOLS_BY_AREA.keys()) == {"auto", "fire", "accident_disease"}

    @pytest.mark.parametrize("area", ["auto", "fire", "accident_disease"])
    def test_area_has_mandatory_key(self, area):
        assert "mandatory" in TOOLS_BY_AREA[area]

    @pytest.mark.parametrize("area", ["auto", "fire", "accident_disease"])
    def test_area_has_recommended_key(self, area):
        assert "recommended" in TOOLS_BY_AREA[area]

    @pytest.mark.parametrize("area", ["auto", "fire", "accident_disease"])
    def test_mandatory_tools_in_tool_names(self, area):
        known = set(tool_names())
        for name in TOOLS_BY_AREA[area]["mandatory"]:
            assert name in known, f"{area}.mandatory: '{name}' 이 tool_names() 에 없음"

    @pytest.mark.parametrize("area", ["auto", "fire", "accident_disease"])
    def test_recommended_tools_in_tool_names(self, area):
        known = set(tool_names())
        for name in TOOLS_BY_AREA[area]["recommended"]:
            assert name in known, f"{area}.recommended: '{name}' 이 tool_names() 에 없음"

    def test_all_areas_mandatory_includes_validate_coverage_period(self):
        # 모든 영역에서 validate_coverage_period 는 의무
        for area in ("auto", "fire", "accident_disease"):
            assert "validate_coverage_period" in TOOLS_BY_AREA[area]["mandatory"]

    def test_all_areas_mandatory_includes_search_terms(self):
        # 모든 영역에서 search_terms 는 의무
        for area in ("auto", "fire", "accident_disease"):
            assert "search_terms" in TOOLS_BY_AREA[area]["mandatory"]

    def test_auto_recommended_includes_get_fault_ratio_standard(self):
        # auto 영역: 과실비율 tool 이 recommended
        assert "get_fault_ratio_standard" in TOOLS_BY_AREA["auto"]["recommended"]

    def test_accident_disease_recommended_includes_get_disease_code(self):
        # accident_disease 영역: 진단 코드 tool 이 recommended
        assert "get_disease_code" in TOOLS_BY_AREA["accident_disease"]["recommended"]

    @pytest.mark.parametrize("area", ["auto", "fire", "accident_disease"])
    def test_no_duplicates_within_area(self, area):
        mandatory = TOOLS_BY_AREA[area]["mandatory"]
        recommended = TOOLS_BY_AREA[area]["recommended"]
        assert len(mandatory) == len(set(mandatory)), f"{area}.mandatory 에 중복 있음"
        assert len(recommended) == len(set(recommended)), f"{area}.recommended 에 중복 있음"


# ===========================================================================
# tool_names() 헬퍼
# ===========================================================================


class TestToolNamesHelper:
    """tool_names() 헬퍼 함수 검증."""

    def test_tool_names_returns_list(self):
        result = tool_names()
        assert isinstance(result, list)

    def test_tool_names_has_8_items(self):
        result = tool_names()
        assert len(result) == 8

    def test_tool_names_all_strings(self):
        result = tool_names()
        assert all(isinstance(name, str) for name in result)

    def test_tool_names_contains_expected_names(self):
        result = set(tool_names())
        assert result == EXPECTED_TOOL_NAMES

    def test_tool_names_no_duplicates(self):
        result = tool_names()
        assert len(result) == len(set(result))


# ===========================================================================
# tools_for_area() 헬퍼
# ===========================================================================


class TestToolsForAreaHelper:
    """tools_for_area() 헬퍼 함수 검증."""

    def test_tools_for_area_auto_returns_dict(self):
        result = tools_for_area("auto")
        assert isinstance(result, dict)

    def test_tools_for_area_fire_returns_dict(self):
        result = tools_for_area("fire")
        assert isinstance(result, dict)

    def test_tools_for_area_accident_disease_returns_dict(self):
        result = tools_for_area("accident_disease")
        assert isinstance(result, dict)

    @pytest.mark.parametrize("area", ["auto", "fire", "accident_disease"])
    def test_tools_for_area_has_mandatory_and_recommended(self, area):
        result = tools_for_area(area)
        assert "mandatory" in result
        assert "recommended" in result

    @pytest.mark.parametrize("area", ["auto", "fire", "accident_disease"])
    def test_tools_for_area_returns_same_as_tools_by_area(self, area):
        # tools_for_area 가 TOOLS_BY_AREA 와 동일한 값 반환
        assert tools_for_area(area) == TOOLS_BY_AREA[area]
