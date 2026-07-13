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

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from app.domains.rag import service as rag_service

# Backward-compat — Sprint 4 마이그레이션. 일부 테스트가
# `app.domains.sessions.service.search_service.similarity_search` 를 monkeypatch 하므로
# attribute path 를 보존한다. 실제 호출은 rag_service 가 VectorRetriever 를 거쳐 처리.
from app.domains.search import service as search_service  # noqa: F401
from app.domains.sessions import llm
from app.domains.sessions.schemas import (
    AssistantAnswer,
    AssistantAsk,
    AssistantAssessment,
    AssistantComparison,
    DeductibleView,
    Message,
    PolicyAssessment,
    PolicyRef,
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

_COMMON_REQUIRED: tuple[str, ...] = ("area",)
"""판정을 **차단(blocking)** 하는 공통 필수 슬롯.

Sprint 34 — insurer/product/incident_date 를 차단 필수에서 제외했다. 이들이 없으면
판정을 막고 되묻는 대신 **일반 실손 표준약관 기준(insurer 미상 → 교차검색)** 으로 진행한다
(익명·개인정보 미공유 사용자도 바로 답을 받게 함). area 는 실손 플로우가 항상 seed 하므로
사실상 비지 않는다. 정밀 판정이 필요한 경우 insurer 는 마이데이터 seed 로 이미 채워진다.
"""

_AREA_REQUIRED: dict[str, tuple[str, ...]] = {
    # 실손 전용(PM-33). auto/fire 폐기. 진단명만 개별 필수.
    "accident_disease": ("diagnosis",),
}

# 입원일수·외래횟수는 OR 그룹 — 하나라도 채워지면 나머지는 0 으로 간주한다.
# (통원만 한 사람은 입원일수가 영원히 안 채워지는 무한 재질문 버그 방지 — 청구는 입원 또는 통원)
_VOLUME_GROUP: tuple[str, ...] = ("hospitalization_days", "outpatient_visits")


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

    # accident_disease: 치료량(입원일수/외래횟수) OR 그룹 — 하나라도 있으면 충족.
    if slots.area == "accident_disease":
        vol_filled = any(not _is_empty(getattr(slots, f, None)) for f in _VOLUME_GROUP)
        vol_all_unknown = all(f in unknown for f in _VOLUME_GROUP)
        if not vol_filled and not vol_all_unknown:
            missing.append("outpatient_visits")  # 대표(입원/통원 여부 질문 트리거)

    return missing


# Sprint 6/34 — partial assessment 진입 조건. Sprint 34: 되묻기 1회로 완화(답변-우선).
# 노인/간단 사용자 표현을 키워드에 보강(대충 물어도 바로 답).
_PARTIAL_KEYWORDS: tuple[str, ...] = (
    "그냥", "됐어", "알려줘", "그만", "다 모름", "몰라", "모르", "잘 몰라", "없어", "그런 거",
)
_PARTIAL_ASK_THRESHOLD: int = 1
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
    on_delta: Callable[[str], None] | None = None,
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

        # 1.6) 의도 분류 (PM-34) — 일반 지식 질문/도메인 이탈은 슬롯 깔때기 대신 별도 처리.
        # 수집 중에는 classify_intent 프리필터가 진단으로 확정하지만, **판정 완료 후에는
        # 우회**해 후속 질문(설명 요청)이 재판정으로 반복되지 않게 한다 (Sprint 35 멀티턴).
        answered = session.status == "answered"
        last_assistant = next(
            (m.content for m in reversed(session.history[:-1]) if m.role == "assistant"),
            None,
        )
        intent = llm.classify_intent(
            text, session.slots, answered=answered, last_assistant=last_assistant
        )
        if intent == "general_qa":
            return _answer_general_qa(session, text, audit_ctx, on_delta=on_delta)
        if intent == "out_of_domain":
            ask = _build_out_of_domain_ask()
            _append_assistant(session, ask.message, response_type="ask")
            store.touch(session, status="gathering")
            audit.complete(
                audit_ctx, assistant_response_type="ask", assistant_message=ask.message
            )
            return _build_response(session, ask)

        # 2) LLM 슬롯 추출 + merge (validator 거치기 위해 model_validate)
        updates = llm.extract_slots(session.history[:-1], text, session.slots)
        # Sprint 35 — 세션 메모(비슬롯 사실) 분리 누적: dedupe + 최근 10개 유지.
        new_notes = updates.pop("_notes", None) if isinstance(updates, dict) else None
        if new_notes:
            session.notes = list(dict.fromkeys([*session.notes, *new_notes]))[-10:]
        # Sprint 36 — 보험사 변경 시 insurer_id 재동기화 (실관측 버그): 대화로 보험사를
        # 바꾸면 이름(insurer)만 갱신되고 옛 insurer_id 가 남아, 필터가 id 우선이라
        # 검색·인용·페이지 이미지가 이전 보험사로 고정된 채 라벨만 새 보험사로 갈라짐.
        if updates.get("insurer"):
            from app.domains.rag._slots import insurer_to_code

            new_code = insurer_to_code(updates["insurer"])
            if new_code != session.slots.insurer_id:
                # 인덱스 내 보험사면 코드 교체, 미지 보험사면 무효화(표준약관 모드로)
                updates["insurer_id"] = new_code
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

        # Sprint 33 — 다중 실손: 보험별로 각각 판정해 비교. 성공 2건 이상이면 비교 응답,
        # 아니면 아래 단일 경로로 폴백(하위호환).
        if len(session.policies) > 1:
            comparison_resp = _build_comparison(session, audit_ctx)
            if comparison_resp is not None:
                return comparison_resp

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

        # PM-35 — 심볼릭 보장 판정(결정론)을 먼저 산정해 LLM 에 grounding 으로 주입.
        # LLM 은 이 판정을 뒤집지 못하고 자연어로 설명만 한다(뉴로심볼릭: 심볼릭이 판단, 뉴럴이 설명).
        from app.domains.coverage import build_facts_from_slots
        from app.domains.coverage import evaluate as evaluate_coverage

        coverage_result = evaluate_coverage(build_facts_from_slots(session.slots))
        assessment = llm.generate_assessment(
            session.slots, chunks,
            coverage=coverage_result.model_dump(mode="json"),
            notes=session.notes, on_delta=on_delta,
        )
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

    # Sprint 33 — 다중 실손: policies 는 SlotState 가 아니라 Session.policies 에 저장.
    # 대표 1건(policies[0])의 보험 식별 필드는 slots 에도 반영(상황 수집 질문 표시용).
    policies = updates.pop("policies", None)
    if policies:
        session.policies = [PolicyRef.model_validate(p) for p in policies]
        rep = session.policies[0]
        updates = {
            "insurer_id": rep.insurer_id, "insurer": rep.insurer,
            "product": rep.product, "policy_no": rep.policy_no,
            "generation": rep.generation, **updates,  # 명시 updates 가 우선
        }

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


def _build_comparison(session: Session, audit_ctx: Any) -> SessionResponse | None:
    """Sprint 33 — 보유 실손 각각을 판정해 비교(비례분담 포함) 응답 생성.

    각 policy 를 공유 상황 슬롯(session.slots)에 얹어 임시 slots 를 만들고, 기존
    _search_chunks(insurer 필터)·evaluate·generate_assessment 를 그대로 N회 재사용한다
    (비스트리밍 — N개 요약 동시 스트리밍은 UX 이득이 없다는 설계 결정).

    판정 성공이 2건 미만이면 None 을 반환해 호출자가 단일 경로로 폴백한다.
    """
    from app.domains.coverage import build_facts_from_slots
    from app.domains.coverage import evaluate as evaluate_coverage
    from app.domains.coverage.proration import compute as compute_proration
    from app.shared import audit

    store = get_session_store()
    assessed: list[tuple[PolicyRef, AssistantAssessment]] = []
    proration_items = []
    for policy in session.policies:
        pslots = session.slots.model_copy(
            update={
                "insurer_id": policy.insurer_id, "insurer": policy.insurer,
                "product": policy.product, "policy_no": policy.policy_no,
                "generation": policy.generation,
            }
        )
        chunks = _search_chunks(pslots)
        if not chunks:
            logger.warning("비교: %s 검색 0건 — 이 보험 스킵", policy.insurer)
            continue
        coverage_result = evaluate_coverage(build_facts_from_slots(pslots))
        try:
            assessment = llm.generate_assessment(
                pslots, chunks, coverage=coverage_result.model_dump(mode="json"),
                notes=session.notes,
            )
        except Exception as exc:  # noqa: BLE001 — 한 보험 실패는 비교 자체를 막지 않음
            logger.warning("비교: %s 판정 실패 — 스킵: %s", policy.insurer, exc)
            continue
        assessed.append((policy, assessment))
        proration_items.append((policy.policy_no, policy.generation, coverage_result))

    if len(assessed) < 2:
        logger.info("비교 대상 %d건(<2) — 단일 판정으로 폴백", len(assessed))
        return None

    pror = compute_proration(proration_items)
    policies_out = []
    all_chunk_ids: list[str] = []
    for policy, assessment in assessed:
        pp = pror.per_policy[policy.policy_no]
        policies_out.append(
            PolicyAssessment(
                insurer_id=policy.insurer_id, insurer=policy.insurer,
                product=policy.product, policy_no=policy.policy_no,
                assessment=assessment,
                deductible=DeductibleView(
                    generation=pp.generation, covered_rate=pp.covered_rate,
                    non_covered_rate=pp.non_covered_rate,
                    outpatient_min_copay=pp.outpatient_min_copay,
                    payable_estimate=pp.payable_estimate, prorated_share=pp.prorated_share,
                ),
            )
        )
        all_chunk_ids += [c.chunk_id for c in assessment.citations]

    comparison = AssistantComparison(
        policies=policies_out, summary=pror.summary,
        recommended_policy_no=pror.recommended_policy_no,
    )
    session.last_comparison = comparison
    session.last_assessment = policies_out[0].assessment  # 청구 요약/체크리스트 하위호환
    audit_ctx.retrieved_chunk_ids = all_chunk_ids
    _append_assistant(session, comparison.summary, response_type="comparison")
    store.touch(session, status="answered")
    audit.complete(
        audit_ctx, assistant_response_type="comparison",
        assistant_message=comparison.summary,
    )
    return _build_response(session, comparison)


def _append_assistant(
    session: Session,
    content: str,
    *,
    response_type: Literal["ask", "assessment", "answer", "comparison"],
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


def _build_out_of_domain_ask() -> AssistantAsk:
    """실손·보험과 무관한 입력에 대한 정중한 도메인 안내(PM-34)."""
    return AssistantAsk(
        type="ask",
        message=(
            "저는 실손의료보험 청구를 도와드리는 어시스턴트예요. "
            "실손 보장·청구가 궁금하시거나 어떤 청구 상황인지 말씀해 주시면 "
            "약관을 근거로 안내드릴게요."
        ),
        expected_slots=["area"],
        options=[],
    )


def _answer_general_qa(
    session: Session,
    text: str,
    audit_ctx: Any,
    *,
    on_delta: Callable[[str], None] | None = None,
) -> SessionResponse:
    """실손 일반 질문 → 슬롯 무관 광역 약관 RAG + 설명 응답(PM-34).

    가입 보험 필터 없이 실손 표준약관 전체에서 검색해 약관 근거로 설명한다.
    인용 강제(환각 차단)는 generate_explanation 이 담당. 검색 0건이면 정직한 재질문.
    """
    from app.shared import audit

    store = get_session_store()
    # Sprint 35 멀티턴 — 짧은 지시형 후속 질문('그게 무슨 뜻이에요?')은 그 자체로는 검색이
    # 안 되므로, 직전 어시스턴트 안내의 앞부분을 검색 질의에 보강한다(LLM 에는 history 전달).
    query = text
    if len(text.strip()) < 20:
        last_assistant = next(
            (m.content for m in reversed(session.history[:-1]) if m.role == "assistant"),
            "",
        )
        if last_assistant:
            query = f"{text} — 직전 안내: {last_assistant[:120]}"
    # Sprint 32 T2 — 뉴로심볼릭 단일 경로 (점수컷·심볼릭 확장 포함).
    # Sprint 35 — 가입 보험사가 확인된 세션은 그 보험사 약관으로 스코프해
    # '메리츠화재 약관 기준으로는…' 식 타 보험사 오귀속 답변을 막는다. 미상이면 교차검색.
    chunks = rag_service.retrieve_freeform(
        query, top_k=8, insurer_id=session.slots.insurer_id
    )
    if not chunks and session.slots.insurer_id:
        chunks = rag_service.retrieve_freeform(query, top_k=8)  # 스코프 0건 → 교차 폴백
    if not chunks:
        ask = AssistantAsk(
            type="ask",
            message=(
                "말씀하신 내용을 실손 약관에서 바로 확인하기 어렵네요. 조금 더 구체적으로 "
                "여쭤봐 주시겠어요? (예: 도수치료 보장 여부, 비급여 자기부담률, 입원 보장 한도 등)"
            ),
            expected_slots=["diagnosis"],
            options=[],
        )
        _append_assistant(session, ask.message, response_type="ask")
        store.touch(session, status="gathering")
        audit.complete(audit_ctx, assistant_response_type="ask", assistant_message=ask.message)
        return _build_response(session, ask)

    answer = llm.generate_explanation(
        text, chunks, history=session.history[:-1], notes=session.notes, on_delta=on_delta
    )
    audit_ctx.retrieved_chunk_ids = [c.chunk_id for c in answer.citations]
    _append_assistant(session, answer.message, response_type="answer")
    store.touch(session, status="answered")
    audit.complete(
        audit_ctx, assistant_response_type="answer", assistant_message=answer.message
    )
    return _build_response(session, answer)


def answer_help(text: str) -> AssistantAnswer:
    """도움 챗봇('무엇이든 물어보세요') 전용 — RAG 근거 일반 QA + 사용법 안내.

    메인 상담(post_message)과 역할을 분리한다:
      - 메인: 가입 약관 필터 + 청구 가능성 '높음/중간/낮음' 판정.
      - 도움: 실손 표준약관 전체에서 RAG 검색 → 일반 QA(근거 인용). **판정은 하지 않음.**

    사용법 질문/무관 질문은 인용 없이 답하고, 본인 사례 판단은 메인 흐름으로 안내한다.
    """
    try:
        chunks = rag_service.retrieve_freeform(text, top_k=6)
    except Exception as exc:  # noqa: BLE001 — 검색 실패해도 사용법 답변은 가능
        logger.warning("answer_help RAG 검색 실패, 무근거 답변으로 진행: %s", exc)
        chunks = []
    return llm.generate_help_answer(text, chunks)


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
    session: Session,
    assistant: AssistantAsk | AssistantAssessment | AssistantAnswer | AssistantComparison,
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
