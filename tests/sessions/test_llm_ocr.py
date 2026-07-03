"""tests.sessions.test_llm_ocr

app/sessions/llm.py 의 OCR 관련 함수 단위 테스트 (Sprint 15 REQ-11 T4).

테스트 대상:
    - classify_document — 5 유형 분류 + 신뢰도 < 0.7 폴백 + 빈 텍스트
    - extract_slots_from_document — 서류 유형별 매핑 + other 시 빈 dict + 빈 텍스트
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.domains.sessions import llm


def _make_tool_response(args: dict, tool_name: str):
    tc = SimpleNamespace(
        id="tc1",
        function=SimpleNamespace(name=tool_name, arguments=json.dumps(args)),
    )
    msg = SimpleNamespace(content="", tool_calls=[tc])
    choice = SimpleNamespace(message=msg, finish_reason="tool_calls")
    return SimpleNamespace(choices=[choice])


def _patch_openai(response):
    class _Client:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(*_a, **_kw):
                    return response

    return _Client()


# ===========================================================================
# classify_document
# ===========================================================================


class TestClassifyDocument:
    def test_empty_text_returns_other_zero_confidence(self):
        result = llm.classify_document("")
        assert result["doc_type"] == "other"
        assert result["confidence"] == 0.0

    def test_whitespace_only_returns_other(self):
        result = llm.classify_document("    \n  \t  ")
        assert result["doc_type"] == "other"

    def test_classifies_diagnosis_high_confidence(self):
        fake_response = _make_tool_response(
            {"doc_type": "diagnosis", "confidence": 0.95, "reason": "병명·치료기간 포함"},
            "classify_document",
        )
        with patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(fake_response)):
            result = llm.classify_document("진단명: 발목 골절\n치료기간: 4주")
        assert result["doc_type"] == "diagnosis"
        assert result["confidence"] == 0.95

    def test_low_confidence_falls_back_to_other(self):
        fake_response = _make_tool_response(
            {"doc_type": "claim_form", "confidence": 0.5, "reason": "모호"},
            "classify_document",
        )
        with patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(fake_response)):
            result = llm.classify_document("어떤 서류")
        # confidence < 0.7 폴백
        assert result["doc_type"] == "other"
        assert result["confidence"] == 0.5

    def test_other_not_fallback_when_already_other(self):
        fake_response = _make_tool_response(
            {"doc_type": "other", "confidence": 0.3, "reason": "식별 불가"},
            "classify_document",
        )
        with patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(fake_response)):
            result = llm.classify_document("뭔가")
        assert result["doc_type"] == "other"
        # 폴백 메시지가 추가되지 않음 (이미 other)
        assert "식별 불가" in result["reason"]


# ===========================================================================
# extract_slots_from_document
# ===========================================================================


class TestExtractSlotsFromDocument:
    def test_other_doc_type_now_attempts_free_extraction(self):
        """Sprint 15.5 — other 도 SlotState 전 필드 자유 추출 (빈 dict 반환 X).

        이전 (Sprint 15): other 매핑 비어있어 빈 dict 반환.
        이후 (Sprint 15.5): other 매핑 = _SLOT_FIELD_ENUM 15 필드 전체. LLM 호출 시도.
        """
        # LLM 응답이 본문에 필드 1개 발견했다고 가정
        fake_response = _make_tool_response(
            {"area": "accident_disease", "incident_date": "2026-05-10"},
            "extract_slots_from_document",
        )
        with patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(fake_response)):
            result = llm.extract_slots_from_document("상해 사고 신고 2026-05-10", "other")
        assert result["area"] == "accident_disease"
        assert result["incident_date"] == "2026-05-10"

    def test_other_doc_type_empty_text_returns_empty(self):
        """other 도 빈 텍스트면 LLM 호출 없이 빈 dict."""
        assert llm.extract_slots_from_document("", "other") == {}

    def test_empty_text_returns_empty(self):
        assert llm.extract_slots_from_document("", "diagnosis") == {}

    def test_unknown_doc_type_returns_empty(self):
        """매핑 자체에 없는 doc_type (예: insurance_card) 은 여전히 빈 dict."""
        assert llm.extract_slots_from_document("text", "unknown_type") == {}

    def test_diagnosis_extracts_expected_fields(self):
        fake_response = _make_tool_response(
            {"diagnosis": "발목 골절", "hospitalization_days": "5"},
            "extract_slots_from_document",
        )
        with patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(fake_response)):
            result = llm.extract_slots_from_document("진단서 본문", "diagnosis")
        assert result["diagnosis"] == "발목 골절"
        assert result["hospitalization_days"] == "5"

    def test_empty_string_values_are_removed(self):
        fake_response = _make_tool_response(
            {"diagnosis": "골절", "evidence": "", "hospitalization_days": "  "},
            "extract_slots_from_document",
        )
        with patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(fake_response)):
            result = llm.extract_slots_from_document("진단서", "diagnosis")
        assert result == {"diagnosis": "골절"}

    def test_police_report_extracts_fields(self):
        fake_response = _make_tool_response(
            {"incident_date": "2026-05-10", "incident_location": "강남대로"},
            "extract_slots_from_document",
        )
        with patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(fake_response)):
            result = llm.extract_slots_from_document("경찰 신고서", "police_report")
        assert result["incident_date"] == "2026-05-10"
        assert result["incident_location"] == "강남대로"

    def test_unknown_doc_type_not_in_mapping_returns_empty(self):
        """_DOC_TYPE_SLOT_FIELDS 에 없는 doc_type 은 LLM 호출 없이 빈 dict 반환."""
        # "insurance_card" 는 매핑에 없는 알려지지 않은 유형
        result = llm.extract_slots_from_document("보험증서 내용", "insurance_card")
        assert result == {}

    def test_receipt_extracts_evidence_field(self):
        fake_response = _make_tool_response(
            {"evidence": "치료비 영수증"},
            "extract_slots_from_document",
        )
        with patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(fake_response)):
            result = llm.extract_slots_from_document("영수증 내용 150,000원", "receipt")
        assert result["evidence"] == "치료비 영수증"

    def test_claim_form_extracts_insurer_and_product(self):
        fake_response = _make_tool_response(
            {"insurer": "한화손해보험", "product": "개인용자동차보험", "incident_date": "2026-05-01"},
            "extract_slots_from_document",
        )
        with patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(fake_response)):
            result = llm.extract_slots_from_document("보험 청구서", "claim_form")
        assert result["insurer"] == "한화손해보험"
        assert result["product"] == "개인용자동차보험"


# ===========================================================================
# classify_document — JSON 파싱 실패 (SchemaViolationError) 경로 (작업 13)
# ===========================================================================


class TestClassifyDocumentJsonParseError:
    """_call_with_tool 이 JSON 파싱 실패 시 SchemaViolationError 를 raise 한다."""

    def test_invalid_json_args_raises_schema_violation(self):
        """LLM 이 반환한 tool arguments 가 유효하지 않은 JSON 이면 SchemaViolationError."""
        from app.infrastructure.core.exceptions import SchemaViolationError

        # tool_calls 가 있지만 arguments 가 깨진 JSON
        tc = SimpleNamespace(
            id="tc1",
            function=SimpleNamespace(name="classify_document", arguments="{invalid json"),
        )
        msg = SimpleNamespace(content="", tool_calls=[tc])
        choice = SimpleNamespace(message=msg, finish_reason="tool_calls")
        bad_response = SimpleNamespace(choices=[choice])

        with (
            patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(bad_response)),
            pytest.raises(SchemaViolationError, match="JSON"),
        ):
            llm.classify_document("어떤 서류 텍스트")

    def test_no_tool_calls_raises_llm_error(self):
        """LLM 이 tool 을 호출하지 않으면 LLMError 가 발생한다."""
        from app.infrastructure.core.exceptions import LLMError

        # tool_calls 가 빈 리스트
        msg = SimpleNamespace(content="일반 텍스트", tool_calls=[])
        choice = SimpleNamespace(message=msg, finish_reason="stop")
        no_tool_response = SimpleNamespace(choices=[choice])

        with (
            patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(no_tool_response)),
            pytest.raises(LLMError),
        ):
            llm.classify_document("어떤 서류 텍스트")


# ===========================================================================
# extract_slots_from_document — JSON 파싱 실패 경로 (작업 13)
# ===========================================================================


class TestExtractSlotsJsonParseError:
    """extract_slots_from_document 에서 JSON 파싱 실패 시 SchemaViolationError."""

    def test_invalid_json_in_extract_raises_schema_violation(self):
        """diagnosis doc_type 으로 호출 시 arguments 가 깨진 JSON 이면 SchemaViolationError."""
        from app.infrastructure.core.exceptions import SchemaViolationError

        tc = SimpleNamespace(
            id="tc2",
            function=SimpleNamespace(
                name="extract_slots_from_document",
                arguments="not-valid-json!!!",
            ),
        )
        msg = SimpleNamespace(content="", tool_calls=[tc])
        choice = SimpleNamespace(message=msg, finish_reason="tool_calls")
        bad_response = SimpleNamespace(choices=[choice])

        with (
            patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(bad_response)),
            pytest.raises(SchemaViolationError, match="JSON"),
        ):
            llm.extract_slots_from_document("진단서 내용", "diagnosis")
