"""tests.rag.test_slots

app/rag/_slots.py 단위 테스트.

테스트 대상:
    - slots_to_query: area 별 쿼리 생성 (accident_disease / 빈 슬롯)
    - slots_to_filters: area 유무에 따른 필터 반환
    - slots_to_question: 자연어 질문 생성 (area 별 + 옵션 필드 포함/미포함)
"""

from __future__ import annotations

from app.domains.rag._slots import slots_to_filters, slots_to_query, slots_to_question
from app.domains.sessions.schemas import SlotState

from tests.rag.conftest import (
    make_accident_disease_slot,
    make_empty_slot,
)

# ===========================================================================
# slots_to_query
# ===========================================================================


class TestSlotsToQuery:
    """slots_to_query — area 별 쿼리 문자열 변환."""

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
        for slots in [make_accident_disease_slot(), make_empty_slot()]:
            assert isinstance(slots_to_query(slots), str)
            assert len(slots_to_query(slots)) > 0


# ===========================================================================
# slots_to_filters
# ===========================================================================


class TestSlotsToFilters:
    """slots_to_filters — Chroma where 필터 딕셔너리 반환."""

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

    def test_insurer_mapped_to_code_in_filter(self):
        """한글 보험사명은 insurer_id 코드로 매핑되어 필터에 포함된다 (타 보험사 약관 인용 차단)."""
        slots = SlotState(area="accident_disease", insurer="한화손해보험")
        filters = slots_to_filters(slots)
        assert filters is not None
        assert filters["insurer_id"] == "hanwha"

    def test_returns_area_and_insurer_id(self):
        """area + insurer_id(코드) 를 함께 필터링."""
        slots = make_accident_disease_slot()  # insurer="현대해상"
        filters = slots_to_filters(slots)
        assert filters == {"area": "accident_disease", "insurer_id": "hyundai"}

    def test_unmapped_insurer_omits_insurer_id(self):
        """매핑 안 되는 보험사명이면 insurer_id 미포함 (area 만)."""
        slots = SlotState(area="accident_disease", insurer="알수없는보험")
        filters = slots_to_filters(slots)
        assert filters == {"area": "accident_disease"}


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

    def test_accident_disease_area_mentions_insurance_type(self):
        slots = make_accident_disease_slot()
        question = slots_to_question(slots)
        assert "실손의료보험" in question

    def test_accident_disease_with_diagnosis_included(self):
        slots = make_accident_disease_slot(diagnosis="골절")
        question = slots_to_question(slots)
        assert "골절" in question

    def test_product_name_included_when_set(self):
        slots = SlotState(area="accident_disease", product="실손의료비보험")
        question = slots_to_question(slots)
        assert "실손의료비보험" in question

    def test_question_ends_with_payment_clause(self):
        slots = make_accident_disease_slot()
        question = slots_to_question(slots)
        assert "보험금 지급 사유" in question
        assert "면책 조항" in question
