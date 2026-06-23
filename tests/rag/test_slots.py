"""tests.rag.test_slots

app/rag/_slots.py 단위 테스트.

테스트 대상:
    - slots_to_query: area 별 쿼리 생성 (auto / fire / accident_disease / 빈 슬롯)
    - slots_to_filters: area 유무에 따른 필터 반환
    - slots_to_question: 자연어 질문 생성 (area 별 + 옵션 필드 포함/미포함)
"""

from __future__ import annotations

from app.domains.rag._slots import slots_to_filters, slots_to_query, slots_to_question
from app.domains.sessions.schemas import SlotState

from tests.rag.conftest import (
    make_accident_disease_slot,
    make_auto_slot,
    make_empty_slot,
    make_fire_slot,
)

# ===========================================================================
# slots_to_query
# ===========================================================================


class TestSlotsToQuery:
    """slots_to_query — area 별 쿼리 문자열 변환."""

    def test_auto_area_includes_incident_type_and_damage_type(self):
        # Arrange
        slots = make_auto_slot(incident_type="추돌", damage_type="자차")

        # Act
        query = slots_to_query(slots)

        # Assert
        assert "자동차 사고" in query
        assert "추돌" in query
        assert "자차" in query

    def test_auto_area_always_contains_payment_reason(self):
        slots = make_auto_slot()
        query = slots_to_query(slots)
        assert "보험금 지급 사유" in query

    def test_auto_area_with_none_incident_type(self):
        """incident_type 이 None 이어도 예외 없이 쿼리 생성."""
        slots = SlotState(area="auto", insurer="한화")
        query = slots_to_query(slots)
        assert "자동차 사고" in query
        assert "보험금 지급 사유" in query

    def test_fire_area_includes_loss_type_and_cause(self):
        slots = make_fire_slot(loss_type="전소", cause="전기 합선")
        query = slots_to_query(slots)
        assert "화재" in query
        assert "전소" in query
        assert "전기 합선" in query

    def test_fire_area_includes_damaged_items(self):
        slots = make_fire_slot(damaged_items=["가전제품", "가구"])
        query = slots_to_query(slots)
        assert "가전제품" in query
        assert "가구" in query

    def test_fire_area_without_damaged_items_no_error(self):
        slots = SlotState(area="fire", loss_type="부분소실")
        query = slots_to_query(slots)
        assert "화재" in query

    def test_accident_disease_area_includes_diagnosis(self):
        slots = make_accident_disease_slot(diagnosis="골절")
        query = slots_to_query(slots)
        assert "상해" in query
        assert "골절" in query
        assert "입원" in query

    def test_accident_disease_without_diagnosis_no_error(self):
        slots = SlotState(area="accident_disease")
        query = slots_to_query(slots)
        assert "상해" in query

    def test_empty_slot_returns_payment_reason_only(self):
        """area 없으면 '보험금 지급 사유' 만 포함."""
        slots = make_empty_slot()
        query = slots_to_query(slots)
        assert "보험금 지급 사유" in query

    def test_query_is_non_empty_string(self):
        """반환값은 항상 비어 있지 않은 문자열."""
        for slots in [make_auto_slot(), make_fire_slot(), make_accident_disease_slot(), make_empty_slot()]:
            assert isinstance(slots_to_query(slots), str)
            assert len(slots_to_query(slots)) > 0


# ===========================================================================
# slots_to_filters
# ===========================================================================


class TestSlotsToFilters:
    """slots_to_filters — Chroma where 필터 딕셔너리 반환."""

    def test_auto_area_returns_area_filter(self):
        slots = make_auto_slot()
        filters = slots_to_filters(slots)
        assert filters is not None
        assert filters["area"] == "auto"

    def test_fire_area_returns_area_filter(self):
        slots = make_fire_slot()
        filters = slots_to_filters(slots)
        assert filters is not None
        assert filters["area"] == "fire"

    def test_accident_disease_area_returns_area_filter(self):
        slots = make_accident_disease_slot()
        filters = slots_to_filters(slots)
        assert filters is not None
        assert filters["area"] == "accident_disease"

    def test_empty_slot_returns_none(self):
        """area 없으면 None 반환."""
        slots = make_empty_slot()
        filters = slots_to_filters(slots)
        assert filters is None

    def test_insurer_not_included_in_filter(self):
        """insurer 는 코드/한글 불일치 — 필터에 포함되지 않음."""
        slots = make_auto_slot(insurer="한화손해보험")
        filters = slots_to_filters(slots)
        assert "insurer" not in (filters or {})
        assert "insurer_id" not in (filters or {})

    def test_returns_dict_with_only_area_key(self):
        """현재 구현은 area 만 필터링."""
        slots = make_auto_slot()
        filters = slots_to_filters(slots)
        assert filters == {"area": "auto"}


# ===========================================================================
# slots_to_question
# ===========================================================================


class TestSlotsToQuestion:
    """slots_to_question — GraphCypherQAChain 용 자연어 질문 생성."""

    def test_empty_slot_returns_generic_question(self):
        slots = make_empty_slot()
        question = slots_to_question(slots)
        assert "보험금 지급 사유" in question
        assert "약관" in question

    def test_auto_area_mentions_car_insurance(self):
        slots = make_auto_slot()
        question = slots_to_question(slots)
        assert "자동차보험" in question

    def test_auto_area_with_incident_type_included(self):
        slots = make_auto_slot(incident_type="추돌")
        question = slots_to_question(slots)
        assert "추돌" in question

    def test_fire_area_mentions_fire_insurance(self):
        slots = make_fire_slot()
        question = slots_to_question(slots)
        assert "주택화재보험" in question

    def test_fire_area_with_loss_type_included(self):
        slots = make_fire_slot(loss_type="전소")
        question = slots_to_question(slots)
        assert "전소" in question

    def test_accident_disease_area_mentions_insurance_type(self):
        slots = make_accident_disease_slot()
        question = slots_to_question(slots)
        assert "상해/질병보험" in question

    def test_accident_disease_with_diagnosis_included(self):
        slots = make_accident_disease_slot(diagnosis="골절")
        question = slots_to_question(slots)
        assert "골절" in question

    def test_product_name_included_when_set(self):
        slots = SlotState(area="auto", product="개인용자동차보험")
        question = slots_to_question(slots)
        assert "개인용자동차보험" in question

    def test_question_ends_with_payment_clause(self):
        slots = make_auto_slot()
        question = slots_to_question(slots)
        assert "보험금 지급 사유" in question
        assert "면책 조항" in question

    def test_unknown_area_uses_raw_area_code(self):
        """area 가 번역 맵에 없을 때 raw 코드 사용."""
        slots = SlotState(area="auto")  # 매핑은 정상 케이스
        question = slots_to_question(slots)
        assert "자동차보험" in question
