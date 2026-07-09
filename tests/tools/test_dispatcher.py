"""tests.tools.test_dispatcher

app/tools/dispatcher.py 단위 테스트.

테스트 대상:
    - invoke(): 정상 라우팅 (validate_coverage_period / finish)
    - invoke(): 미구현 stub (get_disease_code)
                              → ToolNotImplementedError
    - invoke(): 정의되지 않은 tool → ToolNotFoundError
    - _parse_iso_date(): ISO 문자열 → date / date 객체 직접 전달
    - serialize_for_llm(): JSON 직렬화 (한글 unescape)

mock 정책:
    - 외부 의존 없음 (deterministic). monkeypatch 불필요.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from app.shared.tools.dispatcher import (
    ToolNotFoundError,
    ToolNotImplementedError,
    _parse_iso_date,
    invoke,
    serialize_for_llm,
)

# ===========================================================================
# invoke() — 정상 라우팅: validate_coverage_period
# ===========================================================================


class TestInvokeValidateCoveragePeriod:
    """invoke('validate_coverage_period', ...) 정상 라우팅 검증."""

    def test_in_period_returns_valid_true(self):
        args = {
            "incident_date": "2026-05-15",
            "policy_start_date": "2026-01-01",
            "policy_end_date": "2026-12-31",
        }
        result = invoke("validate_coverage_period", args)
        assert result["valid"] is True
        assert result["reason"] == "in_period"

    def test_before_start_returns_valid_false(self):
        args = {
            "incident_date": "2025-12-31",
            "policy_start_date": "2026-01-01",
            "policy_end_date": "2026-12-31",
        }
        result = invoke("validate_coverage_period", args)
        assert result["valid"] is False
        assert result["reason"] == "before_start"

    def test_after_end_returns_valid_false(self):
        args = {
            "incident_date": "2027-01-01",
            "policy_start_date": "2026-01-01",
            "policy_end_date": "2026-12-31",
        }
        result = invoke("validate_coverage_period", args)
        assert result["valid"] is False
        assert result["reason"] == "after_end"

    def test_result_is_dict(self):
        args = {
            "incident_date": "2026-05-15",
            "policy_start_date": "2026-01-01",
            "policy_end_date": "2026-12-31",
        }
        result = invoke("validate_coverage_period", args)
        assert isinstance(result, dict)

    def test_result_contains_message(self):
        args = {
            "incident_date": "2026-05-15",
            "policy_start_date": "2026-01-01",
            "policy_end_date": "2026-12-31",
        }
        result = invoke("validate_coverage_period", args)
        assert "message" in result
        assert len(result["message"]) > 0

    def test_dates_serialized_as_strings_in_json_mode(self):
        # model_dump(mode="json") 이므로 날짜가 문자열로 직렬화됨
        args = {
            "incident_date": "2026-05-15",
            "policy_start_date": "2026-01-01",
            "policy_end_date": "2026-12-31",
        }
        result = invoke("validate_coverage_period", args)
        # JSON 모드에서 날짜 필드는 문자열
        assert isinstance(result["incident_date"], str)


# ===========================================================================
# invoke() — 정상 라우팅: finish
# ===========================================================================


class TestInvokeFinish:
    """invoke('finish', ...) — ReAct loop 종료 신호 검증."""

    def test_finish_returns_dict(self):
        result = invoke("finish", {"reason": "all slots filled"})
        assert isinstance(result, dict)

    def test_finish_returns_finished_true(self):
        result = invoke("finish", {"reason": "충분한 정보 수집"})
        assert result["finished"] is True

    def test_finish_contains_reason(self):
        reason = "all required slots filled + 3 sources gathered"
        result = invoke("finish", {"reason": reason})
        assert result["reason"] == reason

    def test_finish_empty_reason_defaults_to_empty_string(self):
        # reason 없이 호출 시 기본값 빈 문자열
        result = invoke("finish", {})
        assert result["reason"] == ""


# ===========================================================================
# invoke() — 미구현 stub → ToolNotImplementedError
# ===========================================================================


class TestInvokeNotImplementedStubs:
    """미구현 stub tool 호출 시 ToolNotImplementedError 발생 검증."""

    def test_search_terms_returns_chunks(self, monkeypatch):
        # Sprint 32 T2 — search_terms 는 뉴로심볼릭 단일 경로 경유. retriever mock 으로 격리.
        fake_results = [
            {"id": "c1", "text": "조항1 본문", "score": 0.91, "metadata": {"clause_no": "제1조"}},
            {"id": "c2", "text": "조항2 본문", "score": 0.82, "metadata": {"clause_no": "제2조"}},
        ]
        import app.shared.tools.dispatcher as dispatcher_mod

        class FakeRetriever:
            def retrieve_fused(self, query, insurer_id, filters, top_k):
                return fake_results

        monkeypatch.setattr(dispatcher_mod, "_search_retriever", lambda: FakeRetriever())
        result = invoke("search_terms", {"query": "자기부담금"})
        assert result["count"] == 2
        assert len(result["chunks"]) == 2
        assert result["chunks"][0]["id"] == "c1"

    def test_get_disease_code_raises_not_implemented(self):
        with pytest.raises(ToolNotImplementedError):
            invoke("get_disease_code", {"diagnosis_korean": "발목 골절"})

    @pytest.mark.parametrize(
        "tool_name,args",
        [
            # Sprint 11: search_terms 도 활성 (vector 직접) — 제외
            ("get_disease_code", {"diagnosis_korean": "뇌졸중"}),
        ],
    )
    def test_stub_tools_raise_tool_not_implemented_error(self, tool_name, args):
        with pytest.raises(ToolNotImplementedError):
            invoke(tool_name, args)

    def test_not_implemented_error_is_not_not_found_error(self):
        # get_disease_code 는 미구현 stub (NotImplemented)
        with pytest.raises(ToolNotImplementedError):
            invoke("get_disease_code", {"diagnosis_korean": "test"})
        # ToolNotFoundError 가 아님을 확인
        try:
            invoke("get_disease_code", {"diagnosis_korean": "test"})
        except ToolNotImplementedError:
            pass
        except ToolNotFoundError:
            pytest.fail("ToolNotFoundError 가 아닌 ToolNotImplementedError 가 기대됨")


# ===========================================================================
# invoke() — 정의되지 않은 tool → ToolNotFoundError
# ===========================================================================


class TestInvokeNotFoundError:
    """정의되지 않은 tool 호출 시 ToolNotFoundError 발생 검증."""

    def test_unknown_tool_raises_not_found_error(self):
        with pytest.raises(ToolNotFoundError):
            invoke("nonexistent_tool", {})

    def test_hallucinated_tool_name_raises_not_found_error(self):
        with pytest.raises(ToolNotFoundError):
            invoke("get_policy_details", {"policy_id": "ABC123"})

    def test_typo_tool_name_raises_not_found_error(self):
        # 오타가 있는 tool 이름
        with pytest.raises(ToolNotFoundError):
            invoke("calc_claim_amounts", {"loss_amount": 1_000_000})

    def test_empty_tool_name_raises_not_found_error(self):
        with pytest.raises(ToolNotFoundError):
            invoke("", {})

    def test_not_found_error_is_not_not_implemented_error(self):
        # ToolNotFoundError != ToolNotImplementedError
        with pytest.raises(ToolNotFoundError):
            invoke("nonexistent_tool", {})
        try:
            invoke("nonexistent_tool", {})
        except ToolNotFoundError:
            pass
        except ToolNotImplementedError:
            pytest.fail("ToolNotFoundError 가 기대됨, ToolNotImplementedError 발생")

    def test_error_message_contains_tool_name(self):
        tool_name = "hallucinated_tool_xyz"
        with pytest.raises(ToolNotFoundError, match=tool_name):
            invoke(tool_name, {})


# ===========================================================================
# _parse_iso_date — ISO 문자열 / date 객체 직접 전달
# ===========================================================================


class TestParseIsoDate:
    """_parse_iso_date 함수 검증."""

    def test_iso_string_parsed_to_date(self):
        # Arrange
        iso_str = "2026-05-15"
        # Act
        result = _parse_iso_date(iso_str)
        # Assert
        assert result == date(2026, 5, 15)
        assert isinstance(result, date)

    def test_date_object_returned_unchanged(self):
        # date 객체 직접 전달 → 그대로 반환
        d = date(2026, 5, 15)
        result = _parse_iso_date(d)
        assert result == d
        assert result is d

    def test_various_iso_strings(self):
        cases = [
            ("2026-01-01", date(2026, 1, 1)),
            ("2026-12-31", date(2026, 12, 31)),
            ("2000-02-29", date(2000, 2, 29)),  # 윤년
        ]
        for iso_str, expected in cases:
            assert _parse_iso_date(iso_str) == expected

    def test_invalid_iso_string_raises_value_error(self):
        with pytest.raises(ValueError):
            _parse_iso_date("2026-13-01")

    def test_non_iso_format_raises_value_error(self):
        with pytest.raises(ValueError):
            _parse_iso_date("15/05/2026")


# ===========================================================================
# serialize_for_llm — JSON 직렬화 + 한글 unescape
# ===========================================================================


class TestSerializeForLlm:
    """serialize_for_llm 함수 검증."""

    def test_returns_string(self):
        result = serialize_for_llm({"key": "value"})
        assert isinstance(result, str)

    def test_valid_json_output(self):
        data = {"paid_amount": 1_400_000, "formula": "test"}
        result = serialize_for_llm(data)
        parsed = json.loads(result)
        assert parsed == data

    def test_korean_characters_not_escaped(self):
        # ensure_ascii=False → 한글이 \uXXXX 로 이스케이프되지 않음
        data = {"message": "사고일이 보장기간 안에 있습니다"}
        result = serialize_for_llm(data)
        assert "사고일" in result
        # \u 이스케이프 시퀀스가 없는지 확인
        assert "\\u" not in result

    def test_empty_dict_serialized(self):
        result = serialize_for_llm({})
        assert result == "{}"

    def test_nested_dict_serialized(self):
        data = {"result": {"valid": True, "reason": "in_period"}}
        result = serialize_for_llm(data)
        parsed = json.loads(result)
        assert parsed["result"]["valid"] is True
        assert parsed["result"]["reason"] == "in_period"

    def test_list_values_serialized(self):
        data = {"items": [1, 2, 3]}
        result = serialize_for_llm(data)
        parsed = json.loads(result)
        assert parsed["items"] == [1, 2, 3]

    def test_none_value_serialized_as_null(self):
        data = {"note": None}
        result = serialize_for_llm(data)
        parsed = json.loads(result)
        assert parsed["note"] is None

    def test_tool_result_dict_roundtrip(self):
        # tool 결과를 직렬화 후 역직렬화 → 동일 값 보장
        args = {
            "incident_date": "2026-05-15",
            "policy_start_date": "2026-01-01",
            "policy_end_date": "2026-12-31",
        }
        tool_result = invoke("validate_coverage_period", args)
        serialized = serialize_for_llm(tool_result)
        parsed = json.loads(serialized)
        assert parsed["valid"] is True
        assert parsed["reason"] == "in_period"

    def test_korean_in_formula_not_escaped(self):
        # formula 의 '원' 문자가 이스케이프되지 않음
        data = {"formula": "2,000,000 × (1 - 25/100) - 100,000 = 1,400,000원"}
        result = serialize_for_llm(data)
        assert "원" in result
