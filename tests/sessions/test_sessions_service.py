"""tests.sessions.test_sessions_service

app/sessions/service.py 단위 테스트.

테스트 대상:
    - _is_empty: None / 빈 문자열 / 빈 리스트 / 0 / 정상값
    - _compute_missing: 공통 슬롯 누락 / 영역별 슬롯 / area 없는 경우
    - [Sprint 6] _compute_missing: unknown_slots 에 있는 슬롯 missing 에서 제외
    - _merge_slots: validator 재실행 (incident_date 문자열 → date)
    - _slots_to_query: area 별 쿼리 생성
    - _slots_to_filters: 채워진 슬롯만 포함 / area None 시 None 반환
    - _build_no_match_ask: 메시지 포함 필드 확인
    - create_session: 세션 생성 / initial_message 유무
    - close_session: 존재 / 없는 세션
    - get_session: 정상 / SessionNotFoundError
    - post_message: ask 경로 / assessment 경로 / 세션 없음 / RAG 0건 → ask 재유도
    - [Sprint 6] _should_partial: 3 트리거 각각 / 미충족 시 False
    - [Sprint 6] _count_ask_turns: 카운트 검증
    - [Sprint 6] post_message: partial 모드 진입 → LLM next_question 안 부르고 assessment 경로

mock 정책:
    - app.domains.sessions.llm 의 3 함수 (extract_slots / next_question / generate_assessment) → monkeypatch
    - app.domains.sessions.service.rag_service.retrieve → monkeypatch (Sprint 6 partial 분기 테스트)
    - app.domains.search.service.similarity_search → monkeypatch (기존 회귀 보호)
    - app.domains.sessions.store.get_session_store → 독립 SessionStore 주입
"""

from __future__ import annotations

from datetime import date

import pytest
from app.domains.sessions.schemas import (
    AssistantAsk,
    AssistantAssessment,
    Citation,
    SlotState,
)
from app.domains.sessions.service import (
    SessionNotFoundError,
    _build_no_match_ask,
    _compute_missing,
    _count_ask_turns,
    _is_empty,
    _merge_slots,
    _should_partial,
    _slots_to_filters,
    _slots_to_query,
    close_session,
    create_session,
    get_session,
    post_message,
)
from app.domains.sessions.store import SessionStore
from app.infrastructure.core.exceptions import LLMError

# ---------------------------------------------------------------------------
# 픽스처 헬퍼 — 독립 SessionStore 주입
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_store(monkeypatch) -> SessionStore:
    """각 테스트마다 독립 SessionStore 를 get_session_store 에 주입한다.

    lru_cache 우회를 위해 monkeypatch 로 함수 자체를 교체한다.
    """
    store = SessionStore(ttl_seconds=1800)
    monkeypatch.setattr("app.domains.sessions.service.get_session_store", lambda: store)
    monkeypatch.setattr("app.domains.sessions.store.get_session_store", lambda: store)
    return store


def _make_ask() -> AssistantAsk:
    return AssistantAsk(
        message="보험사 이름을 알려주세요.",
        expected_slots=["insurer"],
        options=[],
    )


def _make_assessment() -> AssistantAssessment:
    cite = Citation(
        chunk_id="c1",
        insurer="한화손해보험",
        product="개인용자동차보험",
        version="2026",
        doc_type="terms",
        clause="제3조",
        sub_no=None,
        text="보험금 지급 기준 관련 약관 조항입니다.",
        page=5,
    )
    return AssistantAssessment(
        likelihood="높음",
        summary="자동차 사고로 인한 보험금 청구 가능성이 높습니다.",
        citations=[cite],
    )


def _make_chunks() -> list[dict]:
    return [
        {
            "id": "c1",
            "text": "보험금 지급 기준 관련 약관 조항입니다.",
            "score": 0.9,
            "metadata": {
                "insurer_name": "한화손해보험",
                "insurer_id": "hanwha",
                "product_name": "개인용자동차보험",
                "product_id": "hanwha_auto",
                "version_label": "2026",
                "doc_type": "terms",
                "clause_no": "제3조",
                "sub_no": None,
                "page_start": 5,
            },
        }
    ]


def _full_accident_disease_slots() -> SlotState:
    """accident_disease 영역 필수 슬롯 모두 채운 SlotState."""
    return SlotState(
        area="accident_disease",
        insurer="한화손해보험",
        product="실손의료보험",
        incident_date=date(2026, 3, 15),
        diagnosis="골절",
        hospitalization_days=5,
        outpatient_visits=2,
    )


# ===========================================================================
# _is_empty
# ===========================================================================


class TestIsEmpty:
    """_is_empty 경계값 검증."""

    def test_none_is_empty(self):
        assert _is_empty(None) is True

    def test_empty_string_is_empty(self):
        assert _is_empty("") is True

    def test_whitespace_only_string_is_empty(self):
        assert _is_empty("   ") is True

    def test_empty_list_is_empty(self):
        assert _is_empty([]) is True

    def test_zero_is_not_empty(self):
        # 0 은 유효한 값 (0% 과실비율, 0일 입원)
        assert _is_empty(0) is False

    def test_nonempty_string_is_not_empty(self):
        assert _is_empty("한화") is False

    def test_nonempty_list_is_not_empty(self):
        assert _is_empty(["증거1"]) is False

    def test_integer_nonzero_is_not_empty(self):
        assert _is_empty(30) is False

    def test_date_is_not_empty(self):
        assert _is_empty(date(2026, 1, 1)) is False


# ===========================================================================
# _compute_missing
# ===========================================================================


class TestComputeMissing:
    """_compute_missing 우선순위 순서 + 영역별 슬롯 검증."""

    def test_all_empty_returns_common_required_first(self):
        # Sprint 34 — insurer/product/incident_date 는 차단 필수 제외(없으면 표준약관 모드).
        # 모든 슬롯 비어있으면 area 만 차단 필수.
        missing = _compute_missing(SlotState())
        assert "area" in missing
        assert "insurer" not in missing
        assert "product" not in missing
        assert "incident_date" not in missing
        assert missing[0] == "area"

    def test_all_slots_filled_returns_empty(self):
        # 전체 충족 → 빈 리스트
        missing = _compute_missing(_full_accident_disease_slots())
        assert missing == []

    def test_accident_disease_area_specific_slots_required(self):
        # area=accident_disease + 공통 채움 → 진단명 + 치료량(입원/통원) 질문 필요
        slots = SlotState(
            area="accident_disease",
            insurer="한화생명",
            product="상해보험",
            incident_date=date(2026, 3, 1),
        )
        missing = _compute_missing(slots)
        assert "diagnosis" in missing
        # 입원일수/외래횟수는 OR 그룹 — 대표 하나(outpatient_visits)만 물어봄(둘 다 필수 아님).
        assert "outpatient_visits" in missing
        assert "hospitalization_days" not in missing

    def test_accident_disease_volume_group_or_satisfied(self):
        # 통원만 채워도(입원일수 None) 치료량 그룹 충족 → 무한 재질문 방지
        slots = SlotState(
            area="accident_disease",
            insurer="한화생명",
            product="상해보험",
            incident_date=date(2026, 3, 1),
            diagnosis="손목터널증후군",
            outpatient_visits=3,  # 통원만, 입원일수는 None
        )
        assert _compute_missing(slots) == []

    def test_zero_value_slots_not_in_missing(self):
        # 0 값은 채워진 것으로 처리 → missing 에 포함 안 됨
        slots = SlotState(
            area="accident_disease",
            insurer="한화생명",
            product="상해보험",
            incident_date=date(2026, 3, 1),
            diagnosis="골절",
            hospitalization_days=0,  # 0일 입원 = 유효
            outpatient_visits=0,     # 0회 통원 = 유효
        )
        missing = _compute_missing(slots)
        assert missing == []

    def test_unknown_area_no_area_specific_slots(self):
        # area 가 None 이면 영역별 슬롯 체크 안 함
        slots = SlotState(
            insurer="한화",
            product="실손의료보험",
            incident_date=date(2026, 1, 1),
        )
        missing = _compute_missing(slots)
        assert "diagnosis" not in missing  # accident_disease 전용 — area 없으면 체크 안 함


# ===========================================================================
# _merge_slots
# ===========================================================================


class TestMergeSlots:
    """_merge_slots validator 재실행 + 덮어쓰기 검증."""

    def test_merge_updates_field(self):
        # 기존 슬롯에 새 insurer 머지
        current = SlotState(area="accident_disease")
        updates = {"insurer": "한화손해보험"}
        merged = _merge_slots(current, updates)
        assert merged.insurer == "한화손해보험"
        assert merged.area == "accident_disease"  # 기존 값 유지

    def test_merge_runs_validator_on_date_string(self):
        # updates 에 문자열 날짜 → validator 거쳐 date 로 변환
        current = SlotState()
        updates = {"incident_date": "2026-03-15"}
        merged = _merge_slots(current, updates)
        assert merged.incident_date == date(2026, 3, 15)

    def test_merge_invalid_date_string_becomes_none(self):
        # 모호 표현 → None
        current = SlotState()
        updates = {"incident_date": "지난주"}
        merged = _merge_slots(current, updates)
        assert merged.incident_date is None

    def test_merge_list_field_overwritten(self):
        # 리스트 필드는 덮어쓰기
        current = SlotState(evidence=["기존증거"])
        updates = {"evidence": ["새증거1", "새증거2"]}
        merged = _merge_slots(current, updates)
        assert merged.evidence == ["새증거1", "새증거2"]

    def test_merge_empty_updates_returns_unchanged_slots(self):
        # 빈 updates → 기존 슬롯 그대로
        current = SlotState(area="accident_disease", insurer="한화")
        merged = _merge_slots(current, {})
        assert merged.area == "accident_disease"
        assert merged.insurer == "한화"


# ===========================================================================
# _slots_to_query
# ===========================================================================


class TestSlotsToQuery:
    """_slots_to_query area 별 쿼리 생성 검증."""

    def test_accident_disease_query_contains_disease_keywords(self):
        slots = SlotState(area="accident_disease", diagnosis="골절")
        query = _slots_to_query(slots)
        assert "상해" in query
        assert "골절" in query

    def test_query_always_contains_common_suffix(self):
        # 공통 suffix '보험금 지급 사유' 포함
        for slots in (SlotState(area="accident_disease"), SlotState()):
            query = _slots_to_query(slots)
            assert "보험금" in query


# ===========================================================================
# _slots_to_filters
# ===========================================================================


class TestSlotsToFilters:
    """_slots_to_filters Chroma 필터 생성 검증."""

    def test_area_set_returns_area_filter(self):
        slots = SlotState(area="accident_disease")
        filters = _slots_to_filters(slots)
        assert filters == {"area": "accident_disease"}

    def test_no_area_returns_none(self):
        # area 없음 → None
        slots = SlotState()
        assert _slots_to_filters(slots) is None


# ===========================================================================
# _build_no_match_ask
# ===========================================================================


class TestBuildNoMatchAsk:
    """_build_no_match_ask 검증.

    Sprint 7 추가:
        - 신규 톤 문구 포함 검증
        - 구 톤 문구(책임 떠넘기기) 부재 검증
        - 예시 멘트 포함 검증
    """

    def test_returns_assistant_ask(self):
        slots = SlotState(insurer="한화", product="자동차보험")
        ask = _build_no_match_ask(slots)
        assert isinstance(ask, AssistantAsk)
        assert ask.type == "ask"

    def test_expected_slots_contains_insurer_product(self):
        slots = SlotState()
        ask = _build_no_match_ask(slots)
        assert "insurer" in ask.expected_slots
        assert "product" in ask.expected_slots

    def test_message_includes_current_values(self):
        slots = SlotState(insurer="한화", product="개인용자동차보험")
        ask = _build_no_match_ask(slots)
        assert "한화" in ask.message
        assert "개인용자동차보험" in ask.message

    def test_message_shows_unset_placeholder(self):
        # insurer/product 미설정 시 '미입력' 표시
        slots = SlotState()
        ask = _build_no_match_ask(slots)
        assert "미입력" in ask.message

    # ------------------------------------------------------------------
    # Sprint 7 — 신규 톤 문구 포함 검증
    # ------------------------------------------------------------------

    def test_message_contains_accurate_claim_possibility_phrase(self):
        # Sprint 7 톤: "정확한 청구 가능성" 포함
        slots = SlotState()
        ask = _build_no_match_ask(slots)
        assert "정확한 청구 가능성" in ask.message

    def test_message_contains_guidance_polite_phrase(self):
        # Sprint 7 톤: "안내드리겠습니다" 포함 (능동적 안내 톤)
        slots = SlotState()
        ask = _build_no_match_ask(slots)
        assert "안내드리겠습니다" in ask.message

    def test_message_contains_example_samsung_silson(self):
        # 실손 전용 피벗(Sprint 27): 예시 멘트 "삼성화재 실손의료보험" 포함
        slots = SlotState()
        ask = _build_no_match_ask(slots)
        assert "삼성화재 실손의료보험" in ask.message

    def test_message_contains_example_hyundai_silson(self):
        # 실손 전용 피벗(Sprint 27): 예시 멘트 "현대해상 실손의료보험" 포함
        slots = SlotState()
        ask = _build_no_match_ask(slots)
        assert "현대해상 실손의료보험" in ask.message

    def test_message_does_not_contain_old_reconfirm_phrase(self):
        # Sprint 7 톤: 구 책임 떠넘기기 문구 "다시 한 번 정확히 확인" 부재
        slots = SlotState()
        ask = _build_no_match_ask(slots)
        assert "다시 한 번 정확히 확인" not in ask.message

    def test_message_does_not_contain_not_found_phrase(self):
        # Sprint 7 톤: "찾지 못했습니다" 같은 시스템 오류 표현 부재
        slots = SlotState()
        ask = _build_no_match_ask(slots)
        assert "찾지 못했습니다" not in ask.message


# ===========================================================================
# create_session / close_session / get_session
# ===========================================================================


class TestCreateCloseGetSession:
    """세션 생명주기 기본 동작 검증."""

    def test_create_session_returns_session_and_none(self, isolated_store):
        # initial_message 없음 → (session, None)
        session, first_response = create_session()
        assert session is not None
        assert first_response is None

    def test_create_session_with_initial_message_calls_post_message(
        self, isolated_store, monkeypatch
    ):
        # initial_message 있음 → post_message 호출 → first_response 있음
        ask = _make_ask()

        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr("app.domains.sessions.service.llm.next_question", lambda *a, **kw: ask)

        session, first_response = create_session("자동차 사고가 났어요")
        assert first_response is not None
        assert first_response.assistant.type == "ask"

    def test_create_session_whitespace_message_treated_as_no_message(self, isolated_store):
        # 공백 메시지 → post_message 호출 안 함
        session, first_response = create_session("   ")
        assert first_response is None

    def test_close_existing_session_returns_true(self, isolated_store):
        session = isolated_store.create()
        result = close_session(session.session_id)
        assert result is True

    def test_close_nonexistent_session_returns_false(self, isolated_store):
        result = close_session("nonexistent-id")
        assert result is False

    def test_get_session_returns_session(self, isolated_store):
        session = isolated_store.create()
        retrieved = get_session(session.session_id)
        assert retrieved.session_id == session.session_id

    def test_get_nonexistent_session_raises_not_found(self, isolated_store):
        with pytest.raises(SessionNotFoundError):
            get_session("nonexistent-id")


# ===========================================================================
# post_message — ask 경로
# ===========================================================================


class TestPostMessageAskPath:
    """post_message → missing 있음 → ask 응답 경로 검증."""

    def test_post_message_nonexistent_session_raises_not_found(self, isolated_store):
        with pytest.raises(SessionNotFoundError):
            post_message("nonexistent-id", "안녕하세요")

    def test_post_message_missing_slots_returns_ask(self, isolated_store, monkeypatch):
        # 슬롯 부족 → ask 응답
        ask = _make_ask()
        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr("app.domains.sessions.service.llm.next_question", lambda *a, **kw: ask)

        session = isolated_store.create()
        response = post_message(session.session_id, "안녕하세요")

        assert response.assistant.type == "ask"
        assert response.status == "gathering"

    def test_post_message_appends_user_message_to_history(self, isolated_store, monkeypatch):
        ask = _make_ask()
        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr("app.domains.sessions.service.llm.next_question", lambda *a, **kw: ask)

        session = isolated_store.create()
        post_message(session.session_id, "안녕하세요")

        # history 에 user 메시지 + assistant 메시지 포함
        user_msgs = [m for m in session.history if m.role == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "안녕하세요"

    def test_post_message_appends_assistant_message_to_history(self, isolated_store, monkeypatch):
        ask = _make_ask()
        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr("app.domains.sessions.service.llm.next_question", lambda *a, **kw: ask)

        session = isolated_store.create()
        post_message(session.session_id, "안녕하세요")

        assistant_msgs = [m for m in session.history if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0].response_type == "ask"

    def test_post_message_turn_increments_with_each_user_message(
        self, isolated_store, monkeypatch
    ):
        ask = _make_ask()
        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr("app.domains.sessions.service.llm.next_question", lambda *a, **kw: ask)

        session = isolated_store.create()
        r1 = post_message(session.session_id, "첫 메시지")
        r2 = post_message(session.session_id, "두 번째 메시지")

        assert r1.turn == 1
        assert r2.turn == 2

    def test_post_message_merges_extracted_slots(self, isolated_store, monkeypatch):
        # extract_slots 가 area 반환 → slots 에 반영
        ask = _make_ask()
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.extract_slots",
            lambda *a, **kw: {"area": "accident_disease"},
        )
        monkeypatch.setattr("app.domains.sessions.service.llm.next_question", lambda *a, **kw: ask)

        session = isolated_store.create()
        response = post_message(session.session_id, "다쳐서 병원에 갔어요")

        assert response.slots.area == "accident_disease"

    def test_post_message_status_gathering_when_missing(self, isolated_store, monkeypatch):
        ask = _make_ask()
        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr("app.domains.sessions.service.llm.next_question", lambda *a, **kw: ask)

        session = isolated_store.create()
        response = post_message(session.session_id, "안녕하세요")

        assert response.status == "gathering"


# ===========================================================================
# post_message — assessment 경로
# ===========================================================================


class TestPostMessageAssessmentPath:
    """post_message → missing 없음 → assessment 응답 경로 검증."""

    def test_post_message_all_slots_filled_returns_assessment(
        self, isolated_store, monkeypatch
    ):
        # 모든 슬롯 채워짐 + RAG 청크 있음 → assessment 응답
        assessment = _make_assessment()
        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr(
            "app.domains.sessions.service.search_service.similarity_search",
            lambda *a, **kw: _make_chunks(),
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment",
            lambda *a, **kw: assessment,
        )

        session = isolated_store.create()
        session.slots = _full_accident_disease_slots()

        response = post_message(session.session_id, "청구하고 싶어요")

        assert response.assistant.type == "assessment"
        assert response.status == "answered"

    def test_post_message_assessment_turn_counted_correctly(
        self, isolated_store, monkeypatch
    ):
        assessment = _make_assessment()
        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr(
            "app.domains.sessions.service.search_service.similarity_search",
            lambda *a, **kw: _make_chunks(),
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment",
            lambda *a, **kw: assessment,
        )

        session = isolated_store.create()
        session.slots = _full_accident_disease_slots()

        response = post_message(session.session_id, "청구하고 싶어요")
        assert response.turn == 1

    def test_post_message_rag_empty_returns_ask_reconfirm(
        self, isolated_store, monkeypatch
    ):
        # RAG 0건 → ask 재질문 유도 (503 아님)
        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr(
            "app.domains.sessions.service.rag_service.retrieve",
            lambda *a, **kw: [],  # 빈 결과
        )

        session = isolated_store.create()
        session.slots = _full_accident_disease_slots()

        response = post_message(session.session_id, "청구하고 싶어요")

        assert response.assistant.type == "ask"
        assert response.status == "gathering"

    def test_post_message_llm_error_propagates(self, isolated_store, monkeypatch):
        # LLM 오류 → LLMError 전파
        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr(
            "app.domains.sessions.service.search_service.similarity_search",
            lambda *a, **kw: _make_chunks(),
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment",
            lambda *a, **kw: (_ for _ in ()).throw(LLMError("LLM 호출 실패")),
        )

        session = isolated_store.create()
        session.slots = _full_accident_disease_slots()

        with pytest.raises(LLMError):
            post_message(session.session_id, "청구하고 싶어요")


# ===========================================================================
# Sprint 6 — _compute_missing + unknown_slots 제외
# ===========================================================================


class TestComputeMissingUnknownSlots:
    """Sprint 6 — unknown_slots 에 든 슬롯을 missing 리스트에서 제외."""

    def test_single_unknown_slot_excluded_from_missing(self):
        # unknown_slots=['product'] → 'product' 은 missing 에 없음
        slots = SlotState(
            area="accident_disease",
            insurer="한화손해보험",
            incident_date=date(2026, 3, 15),
            unknown_slots=["product"],
        )
        missing = _compute_missing(slots)
        assert "product" not in missing

    def test_multiple_unknown_slots_all_excluded(self):
        # unknown_slots=['product', 'policy_start_date'] 모두 제외
        # (policy_start_date 는 필수 슬롯 아니라 effect 없음 — insurer 도 테스트)
        slots = SlotState(
            area="accident_disease",
            incident_date=date(2026, 3, 15),
            unknown_slots=["product", "insurer"],
        )
        missing = _compute_missing(slots)
        assert "product" not in missing
        assert "insurer" not in missing

    def test_empty_unknown_slots_preserves_original_behavior(self):
        # unknown_slots=[] 이면 기존 동작 유지 (회귀)
        slots = SlotState(
            area="accident_disease",
            insurer="한화손해보험",
            product="실손의료보험",
            incident_date=date(2026, 3, 15),
        )
        missing = _compute_missing(slots)
        # accident_disease 전용: 진단명 + 치료량 대표(outpatient_visits) missing
        assert "diagnosis" in missing
        assert "outpatient_visits" in missing
        assert "hospitalization_days" not in missing  # OR 그룹 — 대표만 물음

    def test_unknown_area_specific_slot_excluded(self):
        # area=accident_disease + diagnosis 가 unknown → diagnosis missing 에서 제외
        slots = SlotState(
            area="accident_disease",
            insurer="한화손해보험",
            product="실손의료보험",
            incident_date=date(2026, 3, 15),
            hospitalization_days=5,
            outpatient_visits=2,
            unknown_slots=["diagnosis"],
        )
        missing = _compute_missing(slots)
        assert "diagnosis" not in missing
        assert missing == []  # 나머지 슬롯 모두 채워짐

    def test_unknown_common_slot_excluded(self):
        # area=accident_disease + incident_date 가 unknown → incident_date missing 에서 제외
        slots = SlotState(
            area="accident_disease",
            insurer="삼성화재",
            product="실손의료보험",
            diagnosis="골절",
            hospitalization_days=5,
            outpatient_visits=2,
            unknown_slots=["incident_date"],
        )
        missing = _compute_missing(slots)
        assert "incident_date" not in missing


# ===========================================================================
# Sprint 6 — _should_partial
# ===========================================================================


class TestShouldPartial:
    """Sprint 6 — _should_partial 3가지 트리거 각각 검증."""

    def _base_slots(self) -> SlotState:
        """unknown_slots 없는 기본 SlotState."""
        return SlotState(area="accident_disease", insurer="한화", product="자동차보험")

    def test_trigger_unknown_threshold_true(self):
        # unknown_slots 수 ≥ 2 → True
        slots = SlotState(unknown_slots=["insurer", "product"])
        result = _should_partial(slots, missing=["insurer", "product"], ask_count=0, user_text="")
        assert result is True

    def test_trigger_unknown_exactly_two_true(self):
        # unknown_slots = 2 (경계값) → True
        slots = SlotState(unknown_slots=["area", "product"])
        result = _should_partial(slots, missing=["area", "product"], ask_count=0, user_text="")
        assert result is True

    def test_trigger_unknown_one_false(self):
        # unknown_slots = 1 < 2 → unknown 트리거 미충족 (다른 트리거도 없으면 False)
        slots = SlotState(unknown_slots=["insurer"])
        result = _should_partial(slots, missing=["insurer"], ask_count=0, user_text="")
        assert result is False

    def test_trigger_ask_count_threshold_true(self):
        # ask 횟수 ≥ 3 → True
        slots = self._base_slots()
        result = _should_partial(slots, missing=["incident_date"], ask_count=3, user_text="")
        assert result is True

    def test_trigger_ask_count_exactly_three_true(self):
        # ask_count = 3 (경계값) → True
        slots = self._base_slots()
        result = _should_partial(slots, missing=["incident_date"], ask_count=3, user_text="")
        assert result is True

    def test_trigger_ask_count_zero_false(self):
        # Sprint 34 — 임계 1. ask_count = 0 → 아직 미충족(다른 트리거 없으면 False)
        slots = self._base_slots()
        result = _should_partial(slots, missing=["incident_date"], ask_count=0, user_text="")
        assert result is False

    def test_trigger_ask_count_one_true(self):
        # Sprint 34 — 되묻기 1회 후 바로 판정(답변-우선)
        slots = self._base_slots()
        result = _should_partial(slots, missing=["incident_date"], ask_count=1, user_text="")
        assert result is True

    def test_trigger_keyword_geunyang_true(self):
        # "그냥" 키워드 → True
        slots = self._base_slots()
        result = _should_partial(slots, missing=["incident_date"], ask_count=0, user_text="그냥 알려줘")
        assert result is True

    def test_trigger_keyword_daesseo_true(self):
        # "됐어" 키워드 → True
        slots = self._base_slots()
        result = _should_partial(slots, missing=["incident_date"], ask_count=0, user_text="됐어 됐어")
        assert result is True

    def test_trigger_keyword_allyeojwo_true(self):
        # "알려줘" 키워드 → True
        slots = self._base_slots()
        result = _should_partial(slots, missing=["incident_date"], ask_count=0, user_text="그냥 알려줘")
        assert result is True

    def test_trigger_keyword_geuman_true(self):
        # "그만" 키워드 → True
        slots = self._base_slots()
        result = _should_partial(slots, missing=["incident_date"], ask_count=0, user_text="그만 해")
        assert result is True

    def test_all_triggers_false_returns_false(self):
        # unknown < 2, ask < 1(=0), 키워드 없음 → False
        slots = self._base_slots()
        result = _should_partial(
            slots, missing=["incident_date"], ask_count=0, user_text="사고 났어요"
        )
        assert result is False

    def test_no_missing_slots_still_partial_if_keyword(self):
        # missing 없어도 partial 조건 충족이면 True 반환 (호출자가 missing 체크 후 호출)
        slots = self._base_slots()
        result = _should_partial(slots, missing=[], ask_count=0, user_text="그냥 알려줘")
        assert result is True

    def test_keyword_da_morum_true(self):
        # "다 모름" 키워드 → True
        slots = self._base_slots()
        result = _should_partial(slots, missing=["incident_date"], ask_count=0, user_text="다 모름")
        assert result is True


# ===========================================================================
# Sprint 6 — _count_ask_turns
# ===========================================================================


class TestCountAskTurns:
    """Sprint 6 — _count_ask_turns 검증."""

    def _make_session_with_history(self, history_specs: list[tuple[str, str | None]]):
        """(role, response_type) 튜플 리스트로 세션 history 생성."""
        from datetime import UTC, datetime

        from app.domains.sessions.schemas import Message, Session

        now = datetime.now(UTC)
        history = [
            Message(role=role, content="내용", created_at=now, response_type=rt)
            for role, rt in history_specs
        ]
        session = Session(
            session_id="test-session",
            created_at=now,
            last_activity_at=now,
            history=history,
        )
        return session

    def test_no_messages_returns_zero(self):
        session = self._make_session_with_history([])
        assert _count_ask_turns(session) == 0

    def test_one_ask_returns_one(self):
        session = self._make_session_with_history([
            ("user", None),
            ("assistant", "ask"),
        ])
        assert _count_ask_turns(session) == 1

    def test_three_asks_returns_three(self):
        session = self._make_session_with_history([
            ("user", None),
            ("assistant", "ask"),
            ("user", None),
            ("assistant", "ask"),
            ("user", None),
            ("assistant", "ask"),
        ])
        assert _count_ask_turns(session) == 3

    def test_assessment_not_counted(self):
        # response_type='assessment' 는 카운트 안 함
        session = self._make_session_with_history([
            ("user", None),
            ("assistant", "assessment"),
        ])
        assert _count_ask_turns(session) == 0

    def test_mixed_ask_and_assessment_counts_only_ask(self):
        session = self._make_session_with_history([
            ("user", None),
            ("assistant", "ask"),
            ("user", None),
            ("assistant", "assessment"),
            ("user", None),
            ("assistant", "ask"),
        ])
        assert _count_ask_turns(session) == 2

    def test_user_messages_not_counted(self):
        # user 메시지는 카운트 안 함
        session = self._make_session_with_history([
            ("user", None),
            ("user", None),
            ("user", None),
        ])
        assert _count_ask_turns(session) == 0


# ===========================================================================
# Sprint 6 — post_message partial 모드 분기
# ===========================================================================


class TestPostMessagePartialMode:
    """Sprint 6 — partial 모드 진입 시 next_question 호출 없이 assessment 경로 검증."""

    def test_partial_mode_via_keyword_skips_next_question(self, isolated_store, monkeypatch):
        # "그냥 알려줘" 키워드 + missing 있음 → partial 모드 → next_question 안 부름
        assessment = _make_assessment()
        assessment_partial = AssistantAssessment(
            likelihood=assessment.likelihood,
            summary=assessment.summary,
            citations=assessment.citations,
            confidence="partial",
        )
        next_question_called = []

        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.next_question",
            lambda *a, **kw: next_question_called.append(True) or _make_ask(),
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.rag_service.retrieve",
            lambda *a, **kw: _make_chunks(),
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment",
            lambda *a, **kw: assessment_partial,
        )

        session = isolated_store.create()
        # area 만 채워서 missing 이 있는 상태
        session.slots = SlotState(area="accident_disease")

        response = post_message(session.session_id, "그냥 알려줘")

        # partial 모드 → next_question 호출 안 됨
        assert next_question_called == []
        # assessment 응답 반환
        assert response.assistant.type == "assessment"

    def test_partial_mode_via_ask_count_returns_assessment(self, isolated_store, monkeypatch):
        # ask 횟수 ≥ 3 → partial 모드 → assessment 응답
        assessment = _make_assessment()

        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr(
            "app.domains.sessions.service.rag_service.retrieve",
            lambda *a, **kw: _make_chunks(),
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment",
            lambda *a, **kw: assessment,
        )

        session = isolated_store.create()
        session.slots = SlotState(area="accident_disease")

        # history 에 ask 메시지 3개 추가
        from datetime import UTC, datetime

        from app.domains.sessions.schemas import Message

        now = datetime.now(UTC)
        for _ in range(3):
            session.history.append(
                Message(role="user", content="질문", created_at=now)
            )
            session.history.append(
                Message(role="assistant", content="답변", created_at=now, response_type="ask")
            )

        response = post_message(session.session_id, "일반 메시지")
        assert response.assistant.type == "assessment"

    def test_partial_mode_via_unknown_threshold_returns_assessment(
        self, isolated_store, monkeypatch
    ):
        # unknown_slots ≥ 2 → partial 모드 → assessment 응답
        assessment = _make_assessment()

        monkeypatch.setattr(
            "app.domains.sessions.service.llm.extract_slots",
            lambda *a, **kw: {},
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.rag_service.retrieve",
            lambda *a, **kw: _make_chunks(),
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment",
            lambda *a, **kw: assessment,
        )

        session = isolated_store.create()
        # unknown_slots 2개, missing 있는 상태
        session.slots = SlotState(
            area="accident_disease",
            unknown_slots=["insurer", "product"],
        )

        response = post_message(session.session_id, "모르겠어요")
        assert response.assistant.type == "assessment"

    def test_no_partial_trigger_with_missing_goes_to_ask(self, isolated_store, monkeypatch):
        # partial 조건 미충족 + missing 있음 → 기존 ask 경로
        ask = _make_ask()

        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr("app.domains.sessions.service.llm.next_question", lambda *a, **kw: ask)

        session = isolated_store.create()
        session.slots = SlotState(area="accident_disease")  # missing 있음, partial 조건 없음

        response = post_message(session.session_id, "사고 났어요")
        assert response.assistant.type == "ask"
        assert response.status == "gathering"

    def test_partial_mode_with_rag_empty_falls_back_to_no_match_ask(
        self, isolated_store, monkeypatch
    ):
        # partial 모드 → RAG 0건 → ask 재질문 유도 (기존 동작 유지)
        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr(
            "app.domains.sessions.service.rag_service.retrieve",
            lambda *a, **kw: [],
        )

        session = isolated_store.create()
        session.slots = SlotState(area="accident_disease")

        response = post_message(session.session_id, "그냥 알려줘")
        assert response.assistant.type == "ask"
        assert response.status == "gathering"


# ===========================================================================
# Sprint 11 — post_message rag_react=true 분기
# ===========================================================================


class TestPostMessageRagReact:
    """Sprint 11 — rag_react=True 시 run_agent 호출 + audit_ctx.tool_calls 기록."""

    def _setup_rag_react_env(self, monkeypatch):
        """rag_react=True 환경 설정 헬퍼."""
        import app.infrastructure.core.config as _cfg

        _cfg.get_settings.cache_clear()
        monkeypatch.setenv("RAG_REACT", "true")
        _cfg.get_settings.cache_clear()

    def _teardown_rag_react_env(self, monkeypatch):
        import app.infrastructure.core.config as _cfg

        _cfg.get_settings.cache_clear()

    def test_rag_react_true_calls_run_agent(self, isolated_store, monkeypatch):
        """rag_react=True → run_agent 호출 확인."""
        from app.domains.rag.agent import AgentResult

        self._setup_rag_react_env(monkeypatch)

        assessment = _make_assessment()
        run_agent_called = []

        def fake_run_agent(slots, text):
            run_agent_called.append(True)
            return AgentResult(
                chunks=_make_chunks(),
                tool_results=[{"tool": "finish", "args": {}, "result": {"finished": True}}],
                iterations=1,
                finish_reason="finish",
            )

        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr("app.domains.rag.service.run_agent", fake_run_agent)
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment",
            lambda *a, **kw: assessment,
        )

        session = isolated_store.create()
        session.slots = _full_accident_disease_slots()

        response = post_message(session.session_id, "청구하고 싶어요")

        assert run_agent_called == [True]
        assert response.assistant.type == "assessment"

    def test_rag_react_true_uses_agent_chunks(self, isolated_store, monkeypatch):
        """run_agent 반환 chunks 가 generate_assessment 에 전달된다."""
        from app.domains.rag.agent import AgentResult

        self._setup_rag_react_env(monkeypatch)

        assessment = _make_assessment()
        captured_chunks = {}

        def fake_generate_assessment(slots, chunks, coverage=None, notes=None, on_delta=None):
            captured_chunks["chunks"] = chunks
            return assessment

        agent_chunks = _make_chunks()

        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr(
            "app.domains.rag.service.run_agent",
            lambda s, t: AgentResult(
                chunks=agent_chunks,
                tool_results=[],
                iterations=1,
                finish_reason="finish",
            ),
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment",
            fake_generate_assessment,
        )

        session = isolated_store.create()
        session.slots = _full_accident_disease_slots()

        post_message(session.session_id, "청구하고 싶어요")

        # generate_assessment 에 agent chunks 전달 확인
        assert captured_chunks["chunks"] == agent_chunks

    def test_rag_react_true_records_tool_calls_in_audit(self, isolated_store, monkeypatch):
        """run_agent 결과 tool_results 가 audit_ctx.tool_calls 에 기록된다."""
        from app.domains.rag.agent import AgentResult

        self._setup_rag_react_env(monkeypatch)

        assessment = _make_assessment()
        tool_results = [
            {"tool": "search_terms", "args": {"query": "추돌"}, "result": {"chunks": [], "count": 0}},
            {"tool": "finish", "args": {}, "result": {"finished": True}},
        ]

        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr(
            "app.domains.rag.service.run_agent",
            lambda s, t: AgentResult(
                chunks=_make_chunks(),
                tool_results=tool_results,
                iterations=2,
                finish_reason="finish",
            ),
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment",
            lambda *a, **kw: assessment,
        )

        # audit_ctx 에 tool_calls 기록됐는지 확인하기 위해 audit 모듈의 begin 캡처
        # audit 는 sessions.service 에서 `from app import audit` 로 가져오므로
        # app.shared.audit.begin 을 monkeypatch 한다.
        captured_audit_ctx = {}

        import app.shared.audit as _audit

        real_begin = _audit.begin

        def fake_begin(**kwargs):
            ctx = real_begin(**kwargs)
            captured_audit_ctx["ctx"] = ctx
            return ctx

        monkeypatch.setattr(_audit, "begin", fake_begin)

        session = isolated_store.create()
        session.slots = _full_accident_disease_slots()

        post_message(session.session_id, "청구하고 싶어요")

        # audit_ctx.tool_calls 에 agent tool_results 기록됨
        ctx = captured_audit_ctx.get("ctx")
        if ctx is not None:
            assert ctx.tool_calls == tool_results

    def test_rag_react_false_calls_search_chunks(self, isolated_store, monkeypatch):
        """rag_react=False → run_agent 미호출, _search_chunks 경로 사용."""
        import app.infrastructure.core.config as _cfg

        _cfg.get_settings.cache_clear()
        monkeypatch.setenv("RAG_REACT", "false")
        _cfg.get_settings.cache_clear()

        assessment = _make_assessment()
        run_agent_called = []

        def fake_run_agent(slots, text):
            run_agent_called.append(True)
            from app.domains.rag.agent import AgentResult
            return AgentResult(finish_reason="finish")

        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr("app.domains.rag.service.run_agent", fake_run_agent)
        monkeypatch.setattr(
            "app.domains.sessions.service.search_service.similarity_search",
            lambda *a, **kw: _make_chunks(),
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment",
            lambda *a, **kw: assessment,
        )

        session = isolated_store.create()
        session.slots = _full_accident_disease_slots()

        response = post_message(session.session_id, "청구하고 싶어요")

        # run_agent 미호출
        assert run_agent_called == []
        # 기존 경로 (assessment) 정상 반환
        assert response.assistant.type == "assessment"
        _cfg.get_settings.cache_clear()

    def test_rag_react_agent_failure_falls_back_to_search_chunks(
        self, isolated_store, monkeypatch
    ):
        """run_agent 예외 시 단순 RAG (_search_chunks → rag_service.retrieve) 폴백."""
        self._setup_rag_react_env(monkeypatch)

        assessment = _make_assessment()
        fallback_called = []

        def failing_run_agent(slots, text):
            raise RuntimeError("agent 오류")

        def fake_retrieve(*a, **kw):
            fallback_called.append(True)
            return _make_chunks()

        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr("app.domains.rag.service.run_agent", failing_run_agent)
        # _search_chunks 가 rag_service.retrieve 를 호출하므로 retrieve 를 monkeypatch
        monkeypatch.setattr("app.domains.sessions.service.rag_service.retrieve", fake_retrieve)
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment",
            lambda *a, **kw: assessment,
        )

        session = isolated_store.create()
        session.slots = _full_accident_disease_slots()

        response = post_message(session.session_id, "청구하고 싶어요")

        # 폴백 경로로 assessment 반환
        assert len(fallback_called) >= 1
        assert response.assistant.type == "assessment"

    def test_rag_react_agent_failure_rag_also_empty_returns_no_match_ask(
        self, isolated_store, monkeypatch
    ):
        """run_agent 실패 + 폴백 RAG 도 0건 → ask 재질문 유도."""
        self._setup_rag_react_env(monkeypatch)

        monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
        monkeypatch.setattr(
            "app.domains.rag.service.run_agent",
            lambda s, t: (_ for _ in ()).throw(RuntimeError("오류")),
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.search_service.similarity_search",
            lambda *a, **kw: [],  # 폴백도 빈 결과
        )
        # rag_service.retrieve 도 빈 결과 (폴백 경로)
        monkeypatch.setattr(
            "app.domains.sessions.service.rag_service.retrieve",
            lambda *a, **kw: [],
        )

        session = isolated_store.create()
        session.slots = _full_accident_disease_slots()

        response = post_message(session.session_id, "청구하고 싶어요")

        assert response.assistant.type == "ask"
        assert response.status == "gathering"



# ===========================================================================
# Sprint 35 — 세션 메모(2층 기억)
# ===========================================================================


class TestSessionNotes:
    """extract 의 `_notes` 가 Session.notes 로 누적되고 판정 입력에 전달되는지."""

    def _wire(self, monkeypatch, notes_from_extract):
        from app.domains.sessions.schemas import AssistantAssessment, Citation

        captured: dict = {}
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.classify_intent",
            lambda *a, **kw: "claim_diagnosis",
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.extract_slots",
            lambda *a, **kw: {
                "area": "accident_disease",
                "diagnosis": "발목 골절",
                "hospitalization_days": 3,
                "outpatient_visits": 0,
                "incident_date": "2026-07-01",
                **({"_notes": list(notes_from_extract)} if notes_from_extract else {}),
            },
        )
        monkeypatch.setattr(
            "app.domains.sessions.service._search_chunks",
            lambda *a, **kw: [{
                "id": "c1", "text": "제3조 보상합니다", "score": 0.9,
                "metadata": {"insurer_id": "samsung", "clause_no": "제3조"},
            }],
        )

        def fake_assessment(slots, chunks, coverage=None, notes=None, on_delta=None):
            captured["notes"] = notes
            return AssistantAssessment(
                type="assessment", likelihood="높음", confidence="full",
                summary="청구 가능성이 높은 편입니다.", satisfied=[], unsatisfied=[],
                citations=[Citation(chunk_id="c1", insurer="삼성화재", product="실손의료보험",
                                    clause="제3조", page=26, version="2024", doc_type="terms",
                                    text="제3조 보상하는 사항 본문")],
                next_steps=[], disclaimer="면책",
            )

        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_assessment", fake_assessment
        )
        return captured

    def test_notes_accumulate_and_reach_assessment(self, isolated_store, monkeypatch):
        captured = self._wire(monkeypatch, ["교통사고 — 가해 차량 있음", "산재 아님"])
        session = isolated_store.create()
        post_message(session.session_id, "차에 치여서 3일 입원했어요")
        assert session.notes == ["교통사고 — 가해 차량 있음", "산재 아님"]
        assert captured["notes"] == ["교통사고 — 가해 차량 있음", "산재 아님"]

    def test_notes_dedupe_and_cap_at_10(self, isolated_store, monkeypatch):
        self._wire(monkeypatch, [f"메모{i}" for i in range(12)] + ["메모11"])
        session = isolated_store.create()
        post_message(session.session_id, "상황 설명")
        assert len(session.notes) == 10  # cap
        assert session.notes[-1] == "메모11"
        assert len(set(session.notes)) == 10  # dedupe

    def test_no_notes_key_keeps_session_notes_empty(self, isolated_store, monkeypatch):
        captured = self._wire(monkeypatch, None)
        session = isolated_store.create()
        post_message(session.session_id, "발목 골절로 입원했어요")
        assert session.notes == []
        assert captured["notes"] == []


class TestInsurerChangeSync:
    """Sprint 36 — 대화로 보험사 변경 시 insurer_id 재동기화 (실관측: 라벨·이미지 분열)."""

    def _wire(self, monkeypatch, extracted_insurer):
        from app.domains.sessions.schemas import AssistantAsk

        monkeypatch.setattr(
            "app.domains.sessions.service.llm.classify_intent",
            lambda *a, **kw: "claim_diagnosis",
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.extract_slots",
            lambda *a, **kw: {"insurer": extracted_insurer},
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.next_question",
            lambda *a, **kw: AssistantAsk(type="ask", message="진단명을 알려주세요.",
                                          expected_slots=["diagnosis"], options=[]),
        )

    def test_insurer_change_resyncs_id(self, isolated_store, monkeypatch):
        self._wire(monkeypatch, "한화 손해보험")  # 띄어쓰기 발화 그대로
        session = isolated_store.create()
        session.slots = session.slots.model_copy(
            update={"area": "accident_disease", "insurer": "메리츠화재", "insurer_id": "meritz"}
        )
        post_message(session.session_id, "나는 한화 손해보험이야")
        assert session.slots.insurer_id == "hanwha"

    def test_unknown_insurer_clears_id(self, isolated_store, monkeypatch):
        self._wire(monkeypatch, "DB손해보험")  # 인덱스 밖 보험사
        session = isolated_store.create()
        session.slots = session.slots.model_copy(
            update={"area": "accident_disease", "insurer": "메리츠화재", "insurer_id": "meritz"}
        )
        post_message(session.session_id, "DB손해보험으로 바꿨어")
        assert session.slots.insurer_id is None  # 표준약관 모드로

    def test_same_insurer_keeps_id(self, isolated_store, monkeypatch):
        self._wire(monkeypatch, "메리츠화재")
        session = isolated_store.create()
        session.slots = session.slots.model_copy(
            update={"area": "accident_disease", "insurer": "메리츠화재", "insurer_id": "meritz"}
        )
        post_message(session.session_id, "메리츠화재 맞아요")
        assert session.slots.insurer_id == "meritz"


class TestHelpUncitedAnswer:
    """PM-43 T1.2 — 도움 챗봇 사용법 질문은 인용 0건으로 답해도 크래시 안 함.

    이전: generate_help_answer 가 메인 타입 AssistantAnswer(citations min 1)를 재사용해
    사용법 질문(인용 0)에서 ValidationError 크래시. HelpAnswer 로 분리해 복구.
    """

    def test_usage_question_returns_help_answer_without_citations(self, monkeypatch):
        from app.domains.sessions import llm
        from app.domains.sessions.schemas import HelpAnswer

        monkeypatch.setattr(llm, "_get_client", lambda: object())
        monkeypatch.setattr(
            llm, "_call_structured",
            lambda *a, **kw: {"message": "오른쪽 위 버튼으로 시작하세요.",
                              "citations": [], "related_questions": [], "needs_policy": False},
        )
        ans = llm.generate_help_answer("이거 어떻게 써요?", chunks=[])
        assert isinstance(ans, HelpAnswer)
        assert ans.citations == []
        assert ans.message

    def test_main_answer_still_enforces_citation(self):
        """메인 QA 타입(AssistantAnswer)의 인용 최소 1건 강제는 유지(환각 차단)."""
        import pytest
        from app.domains.sessions.schemas import AssistantAnswer
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AssistantAnswer(message="약관상 보상됩니다.", citations=[])
