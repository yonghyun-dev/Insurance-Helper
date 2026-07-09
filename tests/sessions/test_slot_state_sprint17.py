"""tests.sessions.test_slot_state_sprint17

Sprint 17 — SlotState 6 신규 필드 + document_metadata 회귀.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.domains.sessions.schemas import SlotState
from app.domains.sessions.service import _compute_missing
from pydantic import ValidationError


class TestSlotStateNewFields:
    def test_new_fields_default_to_none_or_empty(self):
        s = SlotState()
        assert s.hospital is None
        assert s.diagnosis_code is None
        assert s.treatment_period is None
        assert s.policy_no is None
        assert s.claim_amount is None
        assert s.incident_location is None
        assert s.document_metadata == {}

    def test_new_fields_accept_values(self):
        s = SlotState(
            hospital="한강병원",
            diagnosis_code="S82.5",
            treatment_period="2026-05-10 ~ 2026-05-20",
            policy_no="POLICY-2026-001",
            claim_amount=1_500_000,
            incident_location="서울시 강남구",
        )
        assert s.hospital == "한강병원"
        assert s.diagnosis_code == "S82.5"
        assert s.claim_amount == 1_500_000

    def test_claim_amount_rejects_negative(self):
        with pytest.raises(ValidationError):
            SlotState(claim_amount=-1)

    def test_document_metadata_arbitrary_keys(self):
        s = SlotState(
            document_metadata={
                "issued_at": "2026-05-15",
                "doctor": "김의사",
            }
        )
        assert s.document_metadata["issued_at"] == "2026-05-15"
        assert s.document_metadata["doctor"] == "김의사"


class TestComputeMissingPolicy:
    """_compute_missing 이 Sprint 17 신규 필드를 필수로 안 봄."""

    def test_new_fields_not_required_for_accident_disease(self):
        s = SlotState(
            area="accident_disease",
            insurer="hanwha",
            product="health",
            incident_date="2026-05-10",
            diagnosis="발목 골절",
            hospitalization_days=5,
            outpatient_visits=3,
        )
        missing = _compute_missing(s)
        assert missing == []

    def test_only_common_required_when_minimal(self):
        # Sprint 34 — insurer/product/incident_date 는 차단 필수 제외(표준약관 모드로 진행)
        s = SlotState()
        missing = _compute_missing(s)
        assert set(missing) == {"area"}


class TestSlotStateRoundTrip:
    def test_dump_load_with_new_fields(self):
        s = SlotState(
            area="accident_disease",
            insurer="hanwha",
            hospital="한강병원",
            claim_amount=500_000,
            document_metadata={"key": "value"},
        )
        dumped = s.model_dump(mode="json")
        loaded = SlotState.model_validate(dumped)
        assert loaded.hospital == "한강병원"
        assert loaded.claim_amount == 500_000
        assert loaded.document_metadata == {"key": "value"}

    def test_dump_minimal_excludes_default_empty_metadata(self):
        s = SlotState(area="accident_disease")
        dumped = s.model_dump(mode="json")
        assert dumped.get("document_metadata") == {}
        assert dumped.get("hospital") is None


def _make_tool_response(args: dict, tool_name: str = "extract_slots"):
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


class TestExtractSlotsLlmAcceptsNewFields:
    """extract_slots LLM 응답이 신규 필드 (Sprint 17) 를 받아 들이는지."""

    def test_extract_includes_hospital_and_claim_amount(self):
        from app.domains.sessions import llm

        fake = _make_tool_response(
            {
                "slot_updates": {
                    "area": "accident_disease",
                    "diagnosis": "골절",
                    "hospital": "한강병원",
                    "claim_amount": 1_500_000,
                    "diagnosis_code": "S82.5",
                },
                "unknown_slots": [],
            }
        )
        with patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(fake)):
            updates = llm.extract_slots([], "병원에서 골절 진단", SlotState())
        # extract_slots 반환은 filtered {필드명: 값} dict 직접
        assert updates["hospital"] == "한강병원"
        assert updates["claim_amount"] == 1_500_000
        assert updates["diagnosis_code"] == "S82.5"

    def test_extract_includes_document_metadata(self):
        from app.domains.sessions import llm

        fake = _make_tool_response(
            {
                "slot_updates": {
                    "area": "accident_disease",
                    "document_metadata": {"발급일": "2026-05-15", "의사명": "김의사"},
                },
                "unknown_slots": [],
            }
        )
        with patch("app.domains.sessions.llm._get_client", return_value=_patch_openai(fake)):
            updates = llm.extract_slots([], "진단서 첨부", SlotState())
        meta = updates["document_metadata"]
        assert meta["발급일"] == "2026-05-15"
