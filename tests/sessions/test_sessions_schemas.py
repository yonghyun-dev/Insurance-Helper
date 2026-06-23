"""tests.sessions.test_sessions_schemas

app/sessions/schemas.py 단위 테스트.

테스트 대상:
    - SlotState._coerce_date: None / date / ISO 문자열 / 잘못된 문자열
    - SlotState 필드 제약 (fault_ratio, hospitalization_days, outpatient_visits 경계값)
    - SlotState.unknown_slots: Sprint 6 신규 필드 (기본값, 유효 리스트)
    - Message 필드 제약 (content min_length=1, extra 금지)
    - AssistantAsk 필드 제약 (expected_slots min/max 1~2)
    - Citation 필드 제약 (text min_length=5, page ge=1)
    - AssistantAssessment 필드 제약 (citations min_length=1, summary min_length=10)
    - AssistantAssessment.confidence: Sprint 6 신규 필드 (기본값 'full', partial 허용)
    - SessionResponse discriminator 분기 (ask / assessment)
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from app.domains.sessions.schemas import (
    AssistantAsk,
    AssistantAssessment,
    Citation,
    Message,
    SessionResponse,
    SlotState,
)
from pydantic import ValidationError

# ===========================================================================
# SlotState._coerce_date
# ===========================================================================


class TestSlotStateCoerceDate:
    """incident_date validator 검증."""

    def test_none_stays_none(self):
        # None → 그대로 None
        slot = SlotState(incident_date=None)
        assert slot.incident_date is None

    def test_date_object_stays_unchanged(self):
        # date 객체 → 그대로
        d = date(2025, 3, 15)
        slot = SlotState(incident_date=d)
        assert slot.incident_date == d

    def test_iso_string_converted_to_date(self):
        # 'YYYY-MM-DD' 문자열 → date
        slot = SlotState(incident_date="2025-03-15")
        assert slot.incident_date == date(2025, 3, 15)

    def test_invalid_string_becomes_none(self):
        # '지난주' 같은 모호한 표현 → None
        slot = SlotState(incident_date="지난주")
        assert slot.incident_date is None

    def test_partial_date_string_becomes_none(self):
        # '2025-13-01' (월 13 → ValueError) → None
        slot = SlotState(incident_date="2025-13-01")
        assert slot.incident_date is None

    def test_relative_expression_becomes_none(self):
        # '며칠 전' 같은 자연어 → None
        slot = SlotState(incident_date="며칠 전")
        assert slot.incident_date is None

    def test_today_iso_string_converted_correctly(self):
        # 오늘 날짜 ISO 문자열 → 오늘 date
        today_str = date.today().isoformat()
        slot = SlotState(incident_date=today_str)
        assert slot.incident_date == date.today()


# ===========================================================================
# SlotState 필드 제약
# ===========================================================================


class TestSlotStateFieldConstraints:
    """SlotState 개별 필드 제약 검증."""

    def test_fault_ratio_zero_is_valid(self):
        # fault_ratio = 0 → 유효 (ge=0)
        slot = SlotState(area="auto", fault_ratio=0)
        assert slot.fault_ratio == 0

    def test_fault_ratio_hundred_is_valid(self):
        # fault_ratio = 100 → 유효 (le=100)
        slot = SlotState(area="auto", fault_ratio=100)
        assert slot.fault_ratio == 100

    def test_fault_ratio_over_max_raises_validation_error(self):
        # fault_ratio = 101 → ValidationError
        with pytest.raises(ValidationError):
            SlotState(area="auto", fault_ratio=101)

    def test_fault_ratio_negative_raises_validation_error(self):
        # fault_ratio = -1 → ValidationError
        with pytest.raises(ValidationError):
            SlotState(area="auto", fault_ratio=-1)

    def test_hospitalization_days_zero_is_valid(self):
        # hospitalization_days = 0 → 유효
        slot = SlotState(area="accident_disease", hospitalization_days=0)
        assert slot.hospitalization_days == 0

    def test_hospitalization_days_negative_raises_validation_error(self):
        # hospitalization_days = -1 → ValidationError
        with pytest.raises(ValidationError):
            SlotState(area="accident_disease", hospitalization_days=-1)

    def test_outpatient_visits_zero_is_valid(self):
        # outpatient_visits = 0 → 유효 (0회 통원도 정상)
        slot = SlotState(area="accident_disease", outpatient_visits=0)
        assert slot.outpatient_visits == 0

    def test_evidence_default_empty_list(self):
        # evidence 기본값 = []
        slot = SlotState()
        assert slot.evidence == []

    def test_extra_field_raises_validation_error(self):
        # extra="forbid" → 알 수 없는 필드 ValidationError
        with pytest.raises(ValidationError):
            SlotState(unknown_field="x")

    def test_area_invalid_value_raises_validation_error(self):
        # 허용되지 않는 area 값
        with pytest.raises(ValidationError):
            SlotState(area="health")

    def test_empty_slots_all_none(self):
        # 빈 SlotState → 모든 선택 필드 None
        slot = SlotState()
        assert slot.area is None
        assert slot.insurer is None
        assert slot.incident_date is None


# ===========================================================================
# Message
# ===========================================================================


class TestMessage:
    """Message 모델 검증."""

    def test_valid_user_message(self):
        # 정상 user 메시지
        now = datetime.now(UTC)
        msg = Message(role="user", content="자동차 사고가 났어요", created_at=now)
        assert msg.role == "user"
        assert msg.response_type is None

    def test_valid_assistant_ask_message(self):
        # assistant ask 메시지
        now = datetime.now(UTC)
        msg = Message(role="assistant", content="보험사 이름을 알려주세요", created_at=now, response_type="ask")
        assert msg.response_type == "ask"

    def test_empty_content_raises_validation_error(self):
        # content 최소 1자 → 빈 문자열 거부
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            Message(role="user", content="", created_at=now)

    def test_extra_field_raises_validation_error(self):
        # extra="forbid"
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            Message(role="user", content="안녕", created_at=now, unknown="x")

    def test_invalid_role_raises_validation_error(self):
        # role 은 user / assistant 만 허용
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            Message(role="system", content="안녕", created_at=now)


# ===========================================================================
# AssistantAsk
# ===========================================================================


class TestAssistantAsk:
    """AssistantAsk 모델 검증."""

    def test_valid_ask(self):
        # 정상 ask 응답
        ask = AssistantAsk(
            message="어떤 보험사인가요?",
            expected_slots=["insurer"],
            options=["한화", "삼성"],
        )
        assert ask.type == "ask"
        assert len(ask.expected_slots) == 1

    def test_expected_slots_two_items_valid(self):
        # expected_slots 2개 → 유효
        ask = AssistantAsk(
            message="보험사와 상품을 알려주세요",
            expected_slots=["insurer", "product"],
        )
        assert len(ask.expected_slots) == 2

    def test_expected_slots_empty_raises_validation_error(self):
        # expected_slots 최소 1개 → 빈 리스트 거부
        with pytest.raises(ValidationError):
            AssistantAsk(message="질문입니다", expected_slots=[])

    def test_expected_slots_three_items_raises_validation_error(self):
        # expected_slots 최대 2개 → 3개 거부
        with pytest.raises(ValidationError):
            AssistantAsk(
                message="질문입니다",
                expected_slots=["insurer", "product", "area"],
            )

    def test_options_default_empty(self):
        # options 기본값 = []
        ask = AssistantAsk(message="질문입니다", expected_slots=["area"])
        assert ask.options == []

    def test_empty_message_raises_validation_error(self):
        # message 최소 1자
        with pytest.raises(ValidationError):
            AssistantAsk(message="", expected_slots=["area"])


# ===========================================================================
# Citation
# ===========================================================================


class TestCitation:
    """Citation 모델 검증."""

    def _valid_citation(self, **overrides) -> dict:
        base = {
            "chunk_id": "abc-123",
            "insurer": "한화손해보험",
            "product": "개인용자동차보험",
            "version": "2026-01-01_present",
            "doc_type": "terms",
            "clause": "제3조",
            "sub_no": None,
            "text": "보험금 지급 기준에 의거하여",
            "page": 5,
        }
        base.update(overrides)
        return base

    def test_valid_citation(self):
        cite = Citation(**self._valid_citation())
        assert cite.chunk_id == "abc-123"
        assert cite.page == 5

    def test_text_too_short_raises_validation_error(self):
        # text 최소 5자
        with pytest.raises(ValidationError):
            Citation(**self._valid_citation(text="짧"))

    def test_page_zero_raises_validation_error(self):
        # page 최소 1
        with pytest.raises(ValidationError):
            Citation(**self._valid_citation(page=0))

    def test_page_one_is_valid(self):
        # page = 1 → 유효
        cite = Citation(**self._valid_citation(page=1))
        assert cite.page == 1

    def test_invalid_doc_type_raises_validation_error(self):
        # doc_type 허용: summary / business / terms
        with pytest.raises(ValidationError):
            Citation(**self._valid_citation(doc_type="unknown"))

    def test_sub_no_none_is_valid(self):
        # sub_no = None → 유효
        cite = Citation(**self._valid_citation(sub_no=None))
        assert cite.sub_no is None

    def test_sub_no_string_is_valid(self):
        # sub_no = "①" → 유효
        cite = Citation(**self._valid_citation(sub_no="①"))
        assert cite.sub_no == "①"


# ===========================================================================
# AssistantAssessment
# ===========================================================================


class TestAssistantAssessment:
    """AssistantAssessment 모델 검증."""

    def _valid_citation_dict(self) -> dict:
        return {
            "chunk_id": "c1",
            "insurer": "한화",
            "product": "자동차보험",
            "version": "2026",
            "doc_type": "terms",
            "clause": "제3조",
            "sub_no": None,
            "text": "보험금 지급 조건 관련 조항",
            "page": 10,
        }

    def test_valid_assessment(self):
        assessment = AssistantAssessment(
            likelihood="높음",
            summary="자동차 사고로 인한 보험금 청구 가능성이 높습니다.",
            satisfied=["사고 유형 확인"],
            unsatisfied=[],
            citations=[Citation(**self._valid_citation_dict())],
            next_steps=["청구 서류 준비"],
        )
        assert assessment.type == "assessment"
        assert assessment.likelihood == "높음"
        assert len(assessment.citations) == 1

    def test_default_disclaimer_set(self):
        # disclaimer 기본값 확인
        assessment = AssistantAssessment(
            likelihood="낮음",
            summary="청구 가능성이 낮은 것으로 판단됩니다.",
            citations=[Citation(**self._valid_citation_dict())],
        )
        assert "참고용" in assessment.disclaimer

    def test_empty_citations_raises_validation_error(self):
        # citations 최소 1건
        with pytest.raises(ValidationError):
            AssistantAssessment(
                likelihood="중간",
                summary="가능성 중간으로 판단됩니다.",
                citations=[],
            )

    def test_summary_too_short_raises_validation_error(self):
        # summary 최소 10자
        with pytest.raises(ValidationError):
            AssistantAssessment(
                likelihood="높음",
                summary="짧은요약",
                citations=[Citation(**self._valid_citation_dict())],
            )

    def test_invalid_likelihood_raises_validation_error(self):
        # likelihood 허용: 높음 / 중간 / 낮음
        with pytest.raises(ValidationError):
            AssistantAssessment(
                likelihood="보통",
                summary="가능성 평가 결과입니다.",
                citations=[Citation(**self._valid_citation_dict())],
            )


# ===========================================================================
# SessionResponse discriminator
# ===========================================================================


class TestSessionResponseDiscriminator:
    """SessionResponse 의 type discriminator 분기 검증."""

    def _make_slots(self) -> SlotState:
        return SlotState()

    def test_ask_type_parsed_as_assistant_ask(self):
        # type='ask' → assistant 가 AssistantAsk 로 역직렬화
        resp = SessionResponse(
            session_id="sid-1",
            turn=1,
            assistant={"type": "ask", "message": "보험사가 어디인가요?", "expected_slots": ["insurer"], "options": []},
            slots=self._make_slots(),
            status="gathering",
        )
        assert isinstance(resp.assistant, AssistantAsk)

    def test_assessment_type_parsed_as_assistant_assessment(self):
        # type='assessment' → assistant 가 AssistantAssessment 로 역직렬화
        cite = {
            "chunk_id": "c1", "insurer": "한화", "product": "자동차보험",
            "version": "2026", "doc_type": "terms", "clause": "제3조",
            "sub_no": None, "text": "보험금 지급 기준 조항 내용", "page": 5,
        }
        resp = SessionResponse(
            session_id="sid-1",
            turn=2,
            assistant={
                "type": "assessment",
                "likelihood": "높음",
                "summary": "자동차 사고로 인한 보험금 청구 가능성이 높습니다.",
                "citations": [cite],
            },
            slots=self._make_slots(),
            status="answered",
        )
        assert isinstance(resp.assistant, AssistantAssessment)

    def test_turn_must_be_at_least_one(self):
        # turn >= 1 제약
        with pytest.raises(ValidationError):
            SessionResponse(
                session_id="sid-1",
                turn=0,
                assistant={"type": "ask", "message": "질문입니다", "expected_slots": ["area"], "options": []},
                slots=self._make_slots(),
                status="gathering",
            )


# ===========================================================================
# Sprint 6 — SlotState.unknown_slots
# ===========================================================================


class TestSlotStateUnknownSlots:
    """Sprint 6 — SlotState.unknown_slots 필드 검증."""

    def test_unknown_slots_default_empty_list(self):
        # unknown_slots 기본값은 빈 리스트
        slot = SlotState()
        assert slot.unknown_slots == []

    def test_unknown_slots_accepts_valid_slot_names(self):
        # 유효한 슬롯명 리스트 허용
        slot = SlotState(unknown_slots=["insurer", "product"])
        assert slot.unknown_slots == ["insurer", "product"]

    def test_unknown_slots_single_item(self):
        # 단일 항목 허용
        slot = SlotState(unknown_slots=["area"])
        assert slot.unknown_slots == ["area"]

    def test_unknown_slots_coerce_date_validator_still_works(self):
        # unknown_slots 추가 후 기존 _coerce_date validator 회귀 없음
        slot = SlotState(unknown_slots=["product"], incident_date="2026-03-15")
        assert slot.unknown_slots == ["product"]
        assert slot.incident_date == date(2026, 3, 15)

    def test_unknown_slots_and_area_literal_validator_still_works(self):
        # area Literal 검증 회귀 없음
        with pytest.raises(ValidationError):
            SlotState(unknown_slots=["insurer"], area="invalid_area")

    def test_unknown_slots_does_not_affect_other_fields(self):
        # unknown_slots 가 있어도 다른 필드 정상 동작
        slot = SlotState(
            area="auto",
            insurer="한화손해보험",
            unknown_slots=["product"],
        )
        assert slot.area == "auto"
        assert slot.insurer == "한화손해보험"
        assert slot.unknown_slots == ["product"]

    def test_unknown_slots_model_dump_includes_field(self):
        # model_dump 에 unknown_slots 포함됨 (직렬화 검증)
        slot = SlotState(unknown_slots=["diagnosis"])
        dumped = slot.model_dump()
        assert "unknown_slots" in dumped
        assert dumped["unknown_slots"] == ["diagnosis"]

    def test_unknown_slots_model_validate_roundtrip(self):
        # model_validate(model_dump()) 왕복 변환 정상
        slot = SlotState(unknown_slots=["insurer", "incident_date"])
        slot2 = SlotState.model_validate(slot.model_dump())
        assert slot2.unknown_slots == ["insurer", "incident_date"]


# ===========================================================================
# Sprint 6 — AssistantAssessment.confidence
# ===========================================================================


class TestAssistantAssessmentConfidence:
    """Sprint 6 — AssistantAssessment.confidence 필드 검증."""

    def _valid_citation_dict(self) -> dict:
        return {
            "chunk_id": "c1",
            "insurer": "한화",
            "product": "자동차보험",
            "version": "2026",
            "doc_type": "terms",
            "clause": "제3조",
            "sub_no": None,
            "text": "보험금 지급 기준 관련 조항",
            "page": 10,
        }

    def test_confidence_defaults_to_full(self):
        # confidence 기본값 = 'full' (backward-compat)
        assessment = AssistantAssessment(
            likelihood="높음",
            summary="자동차 사고로 인한 보험금 청구 가능성이 높습니다.",
            citations=[Citation(**self._valid_citation_dict())],
        )
        assert assessment.confidence == "full"

    def test_confidence_partial_accepted(self):
        # confidence='partial' 허용
        assessment = AssistantAssessment(
            likelihood="중간",
            summary="제공된 정보가 일부 부족하여 추정 기반 답변입니다.",
            citations=[Citation(**self._valid_citation_dict())],
            confidence="partial",
        )
        assert assessment.confidence == "partial"

    def test_confidence_full_explicit(self):
        # confidence='full' 명시 허용
        assessment = AssistantAssessment(
            likelihood="낮음",
            summary="자동차 사고로 인한 보험금 청구 가능성이 낮습니다.",
            citations=[Citation(**self._valid_citation_dict())],
            confidence="full",
        )
        assert assessment.confidence == "full"

    def test_confidence_invalid_value_raises_validation_error(self):
        # 허용되지 않는 confidence 값 → ValidationError
        with pytest.raises(ValidationError):
            AssistantAssessment(
                likelihood="높음",
                summary="자동차 사고로 인한 보험금 청구 가능성이 높습니다.",
                citations=[Citation(**self._valid_citation_dict())],
                confidence="unknown",
            )

    def test_confidence_in_model_dump(self):
        # model_dump 에 confidence 포함 (직렬화 검증)
        assessment = AssistantAssessment(
            likelihood="높음",
            summary="자동차 사고로 인한 보험금 청구 가능성이 높습니다.",
            citations=[Citation(**self._valid_citation_dict())],
            confidence="partial",
        )
        dumped = assessment.model_dump()
        assert "confidence" in dumped
        assert dumped["confidence"] == "partial"

    def test_session_response_assessment_with_confidence_partial(self):
        # SessionResponse 안에서 confidence='partial' 직렬화 왕복
        cite = {
            "chunk_id": "c1",
            "insurer": "한화",
            "product": "자동차보험",
            "version": "2026",
            "doc_type": "terms",
            "clause": "제3조",
            "sub_no": None,
            "text": "보험금 지급 기준 조항 내용",
            "page": 5,
        }
        resp = SessionResponse(
            session_id="sid-x",
            turn=1,
            assistant={
                "type": "assessment",
                "likelihood": "중간",
                "summary": "제공된 정보가 일부 부족하여 추정 기반 답변입니다.",
                "citations": [cite],
                "confidence": "partial",
            },
            slots=SlotState(),
            status="answered",
        )
        assert isinstance(resp.assistant, AssistantAssessment)
        assert resp.assistant.confidence == "partial"
