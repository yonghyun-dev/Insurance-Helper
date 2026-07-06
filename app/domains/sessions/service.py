"""app.domains.sessions.service

파일 경로: app/sessions/service.py
목적: 대화 오케스트레이션 진입점. HTTP API (router) 와 CLI (`ica chat`) 양쪽이 공유.

호출 흐름 (post_message):
    1. store.get(session_id) → 없으면 SESSION_NOT_FOUND
    2. user 메시지를 history 에 append
    3. extract_slots(history, text, slots) → updates dict
    4. SlotState.model_validate(merged) — validator 거쳐 incident_date 등 정규화
    5. 영역별 필수 슬롯 검사 → missing 계산 (LLM 책임 아님)
    6. 분기:
       - missing 있음 → status=gathering → next_question → AssistantAsk
       - missing 없음 → status=analyzing → search.similarity_search → generate_assessment → AssistantAssessment → status=answered
    7. assistant 응답을 history 에 append
    8. SessionResponse 반환

원칙(domain-architecture):
    - router/CLI 는 본 service 만 호출
    - 다른 도메인은 service 레벨에서만 import (search.service)
    - missing 슬롯 계산은 본 service 책임, LLM 호출 X
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from app.domains.rag import service as rag_service

# Backward-compat — Sprint 4 마이그레이션. 일부 테스트가
# `app.domains.sessions.service.search_service.similarity_search` 를 monkeypatch 하므로
# attribute path 를 보존한다. 실제 호출은 rag_service 가 VectorRetriever 를 거쳐 처리.
from app.domains.search import service as search_service  # noqa: F401
from app.domains.sessions import llm
from app.domains.sessions.schemas import (
    AssistantAsk,
    AssistantAssessment,
    Message,
    Session,
    SessionResponse,
    SlotSeedResponse,
    SlotState,
)
from app.domains.sessions.store import get_session_store
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)


class SessionNotFoundError(Exception):
    """세션 만료 또는 오타. router 가 404 로 매핑."""


# 외부 공공 API 어댑터에 연결된 tool — audit.external_api_calls trace 분류용.
# 실손 전용: HIRA 진단코드만 유지 (law/kidi/fss auto tool 은 PM-33/34 제거).
_EXTERNAL_API_TOOLS: frozenset[str] = frozenset({"get_disease_code"})


# ---------------------------------------------------------------------------
# 영역별 필수 슬롯 정의 (data-model.md § 영역별 필수 슬롯 표 + tech-decisions §4-1)
# ---------------------------------------------------------------------------

_COMMON_REQUIRED: tuple[str, ...] = ("area", "insurer", "product", "incident_date")
"""모든 영역 공통 필수 슬롯.

순서 자체가 `next_question` 의 우선순위를 결정한다 (tech-decisions §4-1).
앞쪽일수록 먼저 물어본다 — 항목 추가/순서 변경 시 의도적인지 확인할 것.
version 은 누락 시 active 자동 선택이라 필수 아님.
"""

_AREA_REQUIRED: dict[str, tuple[str, ...]] = {
    # 실손 전용(PM-33). auto/fire 폐기.
    # outpatient_visits 는 data-model 표 상 O 지만 _is_empty 가 0 을 유효로 보므로
    # 0 회 통원 환자도 충족 처리됨. 명시 누락 시 LLM 이 안 물어볼 위험이 있어 포함.
    "accident_disease": ("diagnosis", "hospitalization_days", "outpatient_visits"),
}


def _compute_missing(slots: SlotState) -> list[str]:
    """미충족 필수 슬롯을 우선순위 순으로 반환.

    우선순위 (tech-decisions §4-1):
        1. area (다른 슬롯 의미 결정)
        2. insurer + product (RAG 필터 직결)
        3. 공통(incident_date)
        4. 영역별 추가 필수 슬롯
    evidence 는 권장이지만 필수 아님 (마지막에 next_question 이 다룸).

    Sprint 6 — `slots.unknown_slots` 에 명시된 슬롯은 missing 에서 제외 (사용자가 "모름" 표시).
    """
    unknown = set(slots.unknown_slots)
    missing: list[str] = []
    for field in _COMMON_REQUIRED:
        if field not in unknown and _is_empty(getattr(slots, field, None)):
            missing.append(field)

    if slots.area in _AREA_REQUIRED:
        for field in _AREA_REQUIRED[slots.area]:
            if field not in unknown and _is_empty(getattr(slots, field, None)):
                missing.append(field)

    return missing


# Sprint 6 — partial assessment 진입 조건
_PARTIAL_KEYWORDS: tuple[str, ...] = ("그냥", "됐어", "알려줘", "그만", "다 모름")
_PARTIAL_ASK_THRESHOLD: int = 3
_PARTIAL_UNKNOWN_THRESHOLD: int = 2


def _should_partial(
    slots: SlotState, missing: list[str], ask_count: int, user_text: str
) -> bool:
    """partial assessment 진입 조건 3가지 중 하나라도 충족하면 True.

    조건:
        1. unknown_slots 수 ≥ 2 — 사용자가 명시적으로 "모름" 표시한 슬롯 다수
        2. ask 횟수 ≥ 3 — 무한 질문 루프 방지
        3. 사용자 입력에 "그냥"/"됐어"/"알려줘"/"그만" 키워드 — 명시 의사
    """
    if len(slots.unknown_slots) >= _PARTIAL_UNKNOWN_THRESHOLD:
        return True
    if ask_count >= _PARTIAL_ASK_THRESHOLD:
        return True
    return any(kw in user_text for kw in _PARTIAL_KEYWORDS)


def _count_ask_turns(session: Session) -> int:
    """history 에서 assistant role + response_type='ask' 개수."""
    return sum(
        1 for m in session.history
        if m.role == "assistant" and m.response_type == "ask"
    )


def _is_empty(value: Any) -> bool:
    """None / 빈 문자열 / 빈 리스트만 비어있다고 본다 (0 은 유효한 값)."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return isinstance(value, list) and not value


# ---------------------------------------------------------------------------
# create / close
# ---------------------------------------------------------------------------


def create_session(
    initial_message: str | None = None,
    *,
    user_id: int | None = None,
) -> tuple[Session, SessionResponse | None]:
    """새 세션 생성. initial_message 가 있으면 즉시 post_message 호출.

    Args:
        initial_message: 첫 사용자 메시지 (없으면 빈 세션만 생성)
        user_id: Sprint 14.1 — 로그인 사용자 추적용. 비로그인 시 None.

    Returns:
        (session, first_response 또는 None)
    """
    store = get_session_store()
    session = store.create()
    first_response: SessionResponse | None = None
    if initial_message and initial_message.strip():
        first_response = post_message(session.session_id, initial_message, user_id=user_id)
    return session, first_response


def close_session(session_id: str) -> bool:
    """명시적 세션 폐기. 폐기 성공 시 True."""
    return get_session_store().delete(session_id)


def get_session(session_id: str) -> Session:
    """세션 조회 (디버그용). 없으면 SessionNotFoundError."""
    session = get_session_store().get(session_id)
    if session is None:
        raise SessionNotFoundError(f"세션 없음 또는 만료: {session_id}")
    return session


# ---------------------------------------------------------------------------
# post_message (핵심 오케스트레이션)
# ---------------------------------------------------------------------------


def post_message(
    session_id: str,
    text: str,
    *,
    user_id: int | None = None,
) -> SessionResponse:
    """사용자 메시지를 받아 어시스턴트 응답 (ask 또는 assessment) 을 반환한다.

    Args:
        session_id: 기존 세션 id
        text: 사용자 자연어 입력
        user_id: Sprint 14.1 — 로그인 사용자 추적용 (audit_log.user_id). 비로그인 시 None.

    Returns:
        SessionResponse (assistant.type = ask 또는 assessment)

    Raises:
        SessionNotFoundError: 세션 없음/만료
        LLMError / SchemaViolationError: LLM 호출 실패 (router 가 503/422 로 매핑)

    Sprint 8 reviewer C-1 보정: audit 통합 — begin/complete/fail try 구조.
    audit.begin 이 mask_pii 직접 호출 (W-1) 하므로 호출자는 원문 그대로 전달.
    """
    from app.shared import audit

    store = get_session_store()
    session = store.get(session_id)
    if session is None:
        # 세션 없음은 router 에서 404 로 처리. audit 미기록 (응답 없음)
        raise SessionNotFoundError(f"세션 없음 또는 만료: {session_id}")

    turn_no = len([m for m in session.history if m.role == "user"]) + 1
    audit_ctx = audit.begin(
        session_id=session_id, turn=turn_no, raw_user_input=text, user_id=user_id
    )

    try:
        # 1) user 메시지를 history 에 append
        now = _utcnow()
        user_msg = Message(role="user", content=text, created_at=now)
        session.history.append(user_msg)

        # 1.5) Small talk 가드 (PM-18) — 인사/잡담 + slots 빈 상태면 LLM 호출 없이 환영 응답.
        # extract_slots 호출도 건너뛰어 토큰/latency 절약.
        from app.domains.sessions import _smalltalk

        if _smalltalk.should_apply(session.slots, text):
            ask = _smalltalk.make_smalltalk_ask()
            _append_assistant(session, ask.message, response_type="ask")
            store.touch(session, status="gathering")
            audit.complete(
                audit_ctx, assistant_response_type="ask", assistant_message=ask.message
            )
            return _build_response(session, ask)

        # 2) LLM 슬롯 추출 + merge (validator 거치기 위해 model_validate)
        updates = llm.extract_slots(session.history[:-1], text, session.slots)
        if updates:
            session.slots = _merge_slots(session.slots, updates)

        # 3) missing 계산 (서비스 책임)
        missing = _compute_missing(session.slots)
        ask_count = _count_ask_turns(session)
        logger.info(
            "post_message: missing=%s area=%s unknown=%s ask_count=%d",
            missing, session.slots.area, session.slots.unknown_slots, ask_count,
        )

        # Sprint 6 — partial 진입 조건 체크 (missing 있더라도 일정 조건 충족 시 assessment 강제)
        partial_mode = bool(missing) and _should_partial(session.slots, missing, ask_count, text)

        # 4) 분기
        if missing and not partial_mode:
            ask = llm.next_question(session.slots, missing)
            _append_assistant(session, ask.message, response_type="ask")
            store.touch(session, status="gathering")
            audit.complete(
                audit_ctx, assistant_response_type="ask", assistant_message=ask.message
            )
            return _build_response(session, ask)

        if partial_mode:
            logger.info(
                "post_message: partial 모드 진입 (unknown=%d ask=%d) — chunks 있으면 assessment 강제",
                len(session.slots.unknown_slots), ask_count,
            )

        # 충족 또는 partial → RAG + assessment
        store.touch(session, status="analyzing")
        # rag_react=true 면 agent (tool 다발 자가 라우팅, 단일 LangGraph 경로), false 면 단순 RAG.
        if get_settings().rag_react:
            from app.domains.rag.service import run_agent

            try:
                agent_result = run_agent(session.slots, text)
                chunks = agent_result.chunks
                # audit 기록 (분쟁 시 재현). PII 마스킹은 audit.complete 가 trace 전체에 적용.
                audit_ctx.tool_calls = agent_result.tool_results
                audit_ctx.llm_calls = agent_result.llm_calls
                audit_ctx.external_api_calls = [
                    tr for tr in agent_result.tool_results if tr["tool"] in _EXTERNAL_API_TOOLS
                ]
                total_tokens = sum(
                    (c.get("total_tokens") or 0) for c in agent_result.llm_calls
                )
                logger.info(
                    "agent: iterations=%d finish_reason=%s chunks=%d tool_calls=%d "
                    "llm_calls=%d total_tokens=%d",
                    agent_result.iterations,
                    agent_result.finish_reason,
                    len(agent_result.chunks),
                    len(agent_result.tool_results),
                    len(agent_result.llm_calls),
                    total_tokens,
                )
            except Exception as exc:
                logger.error("agent 실패 → 단순 RAG 폴백: %s", exc)
                chunks = _search_chunks(session.slots)
        else:
            chunks = _search_chunks(session.slots)
        if not chunks:
            # 검색 결과 없음은 시스템 오류가 아니라 입력 슬롯이 인덱스와 어긋난 경우.
            # 사용자에게 503 을 던지는 대신 ask 응답으로 슬롯 재확인을 유도한다.
            logger.warning("RAG 검색 결과 0건 — ask 로 재질문 유도")
            ask = _build_no_match_ask(session.slots)
            _append_assistant(session, ask.message, response_type="ask")
            store.touch(session, status="gathering")
            audit.complete(
                audit_ctx, assistant_response_type="ask", assistant_message=ask.message
            )
            return _build_response(session, ask)

        assessment = llm.generate_assessment(session.slots, chunks)
        # audit 에 인용한 chunk_id + confidence 기록 (분쟁 시 재현)
        audit_ctx.retrieved_chunk_ids = [c.chunk_id for c in assessment.citations]
        # Sprint 22 — 청구 요약/체크리스트 집계용으로 전체 assessment 보관
        session.last_assessment = assessment
        _append_assistant(session, assessment.summary, response_type="assessment")
        store.touch(session, status="answered")
        audit.complete(
            audit_ctx,
            assistant_response_type="assessment",
            assistant_message=assessment.summary,
            confidence=assessment.confidence,
        )
        return _build_response(session, assessment)
    except Exception as exc:
        # PII 마스킹 후 error 메시지 기록 (사용자 입력이 exception 메시지에 흘러올 가능성 대비)
        from app.shared.security.pii import mask_pii

        audit.fail(audit_ctx, error=mask_pii(str(exc)))
        raise


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


def seed_slots(session_id: str, updates: dict[str, Any]) -> SlotSeedResponse:
    """구조화 슬롯을 결정론적으로 세션에 병합한다 (LLM 미거침).

    마이데이터/건강보험/OCR 처럼 이미 구조화된 데이터(insurer_id·policy_no·진료내역)를
    자연어로 flatten → LLM 재추출 하지 않고 직접 슬롯에 세팅한다. 이로써 코드 유실·
    재질문·추출 변동성을 근본 제거한다 (PM-33 Track A).

    Args:
        session_id: 기존 세션 id
        updates: SlotState 필드명→값. 알 수 없는 키/빈 값은 무시(기존 값 보존).

    Returns:
        SlotSeedResponse — 병합 후 슬롯 + 아직 부족한 필수 슬롯

    Raises:
        SessionNotFoundError: 세션 없음/만료
    """
    store = get_session_store()
    session = store.get(session_id)
    if session is None:
        raise SessionNotFoundError(f"세션 없음 또는 만료: {session_id}")

    valid_fields = set(SlotState.model_fields)
    clean = {
        k: v
        for k, v in updates.items()
        if k in valid_fields and v not in (None, "", [])
    }
    if clean:
        session.slots = _merge_slots(session.slots, clean)
        logger.info("seed_slots: %d 필드 결정론 병합 (session=%s)", len(clean), session_id)
    store.touch(session, status="gathering")
    return SlotSeedResponse(slots=session.slots, missing=_compute_missing(session.slots))


def _merge_slots(current: SlotState, updates: dict[str, Any]) -> SlotState:
    """현재 슬롯 + LLM 추출 dict 를 머지하고 SlotState 로 재검증.

    - dict 머지로 validator 우회 회피 (model_copy 는 validator 안 거침)
    - list 필드(evidence/damaged_items): LLM 이 보낸 값으로 덮어쓰기 (PoC 단순화 — 사용자가
      이전 입력을 다시 언급하면 LLM 이 합쳐서 보낸다고 가정)
    """
    merged = current.model_dump()
    merged.update(updates)
    return SlotState.model_validate(merged)


def _append_assistant(
    session: Session, content: str, *, response_type: Literal["ask", "assessment"]
) -> None:
    """assistant 메시지를 history 에 append."""
    session.history.append(
        Message(
            role="assistant",
            content=content,
            created_at=_utcnow(),
            response_type=response_type,
        )
    )


def _build_no_match_ask(slots: SlotState) -> AssistantAsk:
    """RAG 0건 시 사용자에게 슬롯 재확인을 유도하는 ask 응답.

    Sprint 7 톤 가이드: 사용자에게 책임 떠넘기지 않고, 시스템이 능동적으로 안내.
    "정확한 안내에는 어떤 정보가 필요한지" 알려주고, 정보가 있다면 알려달라는 부탁.
    """
    insurer_label = slots.insurer or "미입력"
    product_label = slots.product or "미입력"
    return AssistantAsk(
        type="ask",
        message=(
            "정확한 청구 가능성 판단에는 가입하신 보험사·상품 정보가 필요합니다. "
            "알고 계신 정보가 있다면 알려주시면 정확하게 안내드리겠습니다. "
            "(예: 삼성화재 실손의료보험, 현대해상 실손의료보험 등) "
            f"— 현재 보유한 정보: 보험사 {insurer_label} · 상품 {product_label}"
        ),
        expected_slots=["insurer", "product"],
        options=[],
    )


def _search_chunks(slots: SlotState, top_k: int = 8) -> list[dict[str, Any]]:
    """RAG 검색 thin wrapper (단순 retrieve 경로).

    app.domains.rag.service.retrieve 가 mode 라우팅 (vector/graph/hybrid) + graceful
    fallback 을 캡슐화. 본 함수는 sessions.service 내부의 기존 호출자 인터페이스 유지용 wrapper.

    슬롯 → 검색 query/filter 변환 로직은 `app/rag/_slots.py` 로 이전됨.
    에이전트(tool 자가 라우팅) 경로는 본 함수가 아니라 run_agent(LangGraph)가 담당한다.
    """
    return rag_service.retrieve(slots, top_k=top_k)


# ---------------------------------------------------------------------------
# Sprint 4 backward-compat — 기존 테스트가 import 하던 슬롯 변환 함수.
# 새 코드는 app/rag/_slots.py 를 직접 import 한다.
# ---------------------------------------------------------------------------

from app.domains.rag._slots import slots_to_filters as _slots_to_filters  # noqa: E402, F401
from app.domains.rag._slots import slots_to_query as _slots_to_query  # noqa: E402, F401


def _build_response(
    session: Session, assistant: AssistantAsk | AssistantAssessment
) -> SessionResponse:
    """SessionResponse 생성. turn = 유저 메시지 개수."""
    turn = sum(1 for m in session.history if m.role == "user")
    return SessionResponse(
        session_id=session.session_id,
        turn=turn,
        assistant=assistant,
        slots=session.slots,
        status=session.status,
    )
