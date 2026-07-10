"""app.domains.sessions.router

파일 경로: app/sessions/router.py
목적: 멀티턴 대화 HTTP API. service 만 호출한다 (store/llm 직접 참조 금지).

엔드포인트 (docs/design/api-spec.md § Sprint 2 와 동기화):
    - POST   /sessions                       — 새 세션 생성 (initial_message 옵션)
    - POST   /sessions/{session_id}/messages — 멀티턴 핵심
    - GET    /sessions/{session_id}          — 디버그용 상태 조회
    - DELETE /sessions/{session_id}          — 명시적 폐기

에러 표준 (api-spec.md § 에러 응답 표준):
    {"error": {"code": "SESSION_NOT_FOUND", "message": "..."}}
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.domains.auth.deps import get_current_user_optional
from app.domains.claims import service as claims_service
from app.domains.claims.schemas import ClaimChecklist, ClaimReceipt, ClaimSummary
from app.domains.sessions import service
from app.domains.sessions.schemas import (
    Citation,
    Message,
    MessageRequest,
    SessionCreate,
    SessionResponse,
    SessionStatus,
    SlotSeedRequest,
    SlotSeedResponse,
    SlotState,
)
from app.domains.sessions.service import SessionNotFoundError
from app.domains.users.models import User
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.exceptions import LLMError, SchemaViolationError
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# 라우터-전용 응답 모델
# ---------------------------------------------------------------------------


class SessionCreateResponse(BaseModel):
    """POST /sessions 응답.

    `initial_message` 있는 경우 `first_response` 동봉. 없으면 None.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    created_at: datetime
    ttl_seconds: int
    first_response: SessionResponse | None = None


class SessionStateResponse(BaseModel):
    """GET /sessions/{id} 응답 (디버그). 전체 history + 현재 슬롯 노출."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    created_at: datetime
    last_activity_at: datetime
    status: SessionStatus
    slots: SlotState
    history: list[Message] = Field(default_factory=list)
    # Sprint 35 — 세션 메모(비슬롯 사실) 디버그 노출
    notes: list[str] = Field(default_factory=list)


class HelpRequest(BaseModel):
    """POST /sessions/help 요청 — 도움 챗봇 일반 질문."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)


class HelpResponse(BaseModel):
    """POST /sessions/help 응답 — RAG 근거 일반 QA(사용법 질문이면 citations 빈 배열)."""

    model_config = ConfigDict(extra="forbid")

    message: str
    citations: list[Citation] = Field(default_factory=list)
    related_questions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 내부 헬퍼 — 표준 에러 응답
# ---------------------------------------------------------------------------


def _error(code: str, message: str, *, http: int) -> HTTPException:
    """api-spec.md § 에러 응답 표준 형태를 FastAPI 가 직렬화하도록 HTTPException 생성."""
    return HTTPException(status_code=http, detail={"error": {"code": code, "message": message}})


# 클라이언트 노출 메시지는 고정 문구로 통일 (W-1 보정).
# 내부 상세(함수명, 슬롯 흐름, 세션 id 등) 는 로그로만 남기고 응답에 흘리지 않는다.
_MSG_SESSION_NOT_FOUND = "세션이 만료되었거나 존재하지 않습니다."
_MSG_LLM_UNAVAILABLE = "LLM 서비스가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해주세요."


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------


@router.post("/help", response_model=HelpResponse)
def help_answer(payload: HelpRequest) -> HelpResponse:
    """도움 챗봇('무엇이든 물어보세요') 전용 — 세션·인용·판정 없는 일반 도움말.

    메인 상담(POST /sessions/{id}/messages)과 역할이 분리된다. 여기서는 서비스 사용법과
    보험 기본 개념만 쉬운 말로 답하고, 약관 인용·청구 가능성 판정은 하지 않는다.
    """
    try:
        answer = service.answer_help(payload.text)
    except LLMError as exc:
        logger.error("help_answer LLM 오류: %s", exc)
        raise _error("LLM_UNAVAILABLE", _MSG_LLM_UNAVAILABLE, http=503) from exc
    return HelpResponse(
        message=answer.message,
        citations=answer.citations,
        related_questions=answer.related_questions,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SessionCreateResponse)
def create_session(
    payload: SessionCreate | None = None,
    current_user: User | None = Depends(get_current_user_optional),  # noqa: B008
) -> SessionCreateResponse:
    """새 대화 세션을 생성한다.

    `initial_message` 가 있으면 즉시 첫 턴을 처리해 `first_response` 동봉.
    실패 시 service 에서 raise → 본 라우터에서 표준 에러로 매핑.

    Sprint 14.1 (REQ-10): 인증 헤더 옵셔널. 로그인 시 user_id 기록 (audit_log.user_id),
    비로그인 시 None (기존 동작과 동일).
    """
    payload = payload or SessionCreate()
    user_id = current_user.id if current_user else None
    try:
        session, first = service.create_session(payload.initial_message, user_id=user_id)
    except SchemaViolationError as exc:
        logger.error("create_session schema 위반: %s", exc)
        raise _error("LLM_UNAVAILABLE", _MSG_LLM_UNAVAILABLE, http=503) from exc
    except LLMError as exc:
        logger.error("create_session LLM 실패: %s", exc)
        raise _error("LLM_UNAVAILABLE", _MSG_LLM_UNAVAILABLE, http=503) from exc

    settings = get_settings()
    return SessionCreateResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        ttl_seconds=settings.session_ttl_seconds,
        first_response=first,
    )


@router.post("/{session_id}/messages", response_model=SessionResponse)
def post_message(
    session_id: str,
    payload: MessageRequest,
    current_user: User | None = Depends(get_current_user_optional),  # noqa: B008
) -> SessionResponse:
    """멀티턴 핵심 — 사용자 메시지 1건 → 어시스턴트 응답 (ask 또는 assessment).

    Sprint 8 — Limiter 인프라 (app.state.limiter) 설치 완료. endpoint level 데코레이터 적용은
    Sprint 9 외부 API tool 추가 시 함께 (rate limit 한도 정책을 외부 API 호출과 묶어 설계).

    Sprint 14.1 (REQ-10): 인증 헤더 옵셔널. 로그인 시 audit_log.user_id 기록.
    """
    user_id = current_user.id if current_user else None
    try:
        return service.post_message(session_id, payload.text, user_id=user_id)
    except SessionNotFoundError as exc:
        logger.info("post_message: 세션 미존재/만료 id=%s", session_id)
        raise _error("SESSION_NOT_FOUND", _MSG_SESSION_NOT_FOUND, http=404) from exc
    except SchemaViolationError as exc:
        logger.error("post_message schema 위반: %s", exc)
        raise _error("LLM_UNAVAILABLE", _MSG_LLM_UNAVAILABLE, http=503) from exc
    except LLMError as exc:
        logger.error("post_message LLM 실패: %s", exc)
        raise _error("LLM_UNAVAILABLE", _MSG_LLM_UNAVAILABLE, http=503) from exc


@router.post("/{session_id}/messages/stream")
def stream_message(
    session_id: str,
    payload: MessageRequest,
    current_user: User | None = Depends(get_current_user_optional),  # noqa: B008
) -> StreamingResponse:
    """SSE 스트리밍 — 답변 텍스트를 생성되는 대로 delta 로 흘리고, 완료 시 full 응답을 final 로.

    threaded-queue 브리지: post_message(기존 로직·감사·저장 그대로)를 워커 스레드에서 돌리고,
    generate_* 의 on_delta 콜백이 summary/message 증가분을 큐로 밀어 SSE 로 전달한다.
    이벤트: `delta`(텍스트 조각) / `final`(SessionResponse JSON) / `error`.
    """
    import json as _json
    from queue import Queue
    from threading import Thread

    user_id = current_user.id if current_user else None

    def event_stream() -> Iterator[str]:
        q: Queue = Queue()

        def on_delta(text: str) -> None:
            q.put(("delta", {"text": text}))

        def run() -> None:
            try:
                resp = service.post_message(
                    session_id, payload.text, user_id=user_id, on_delta=on_delta
                )
                q.put(("final", resp.model_dump(mode="json")))
            except SessionNotFoundError:
                q.put(("error", {"code": "SESSION_NOT_FOUND", "message": _MSG_SESSION_NOT_FOUND}))
            except (LLMError, SchemaViolationError) as exc:
                logger.error("stream_message LLM 실패: %s", exc)
                q.put(("error", {"code": "LLM_UNAVAILABLE", "message": _MSG_LLM_UNAVAILABLE}))
            except Exception as exc:  # noqa: BLE001
                logger.error("stream_message 예외: %s", exc)
                q.put(("error", {"code": "INTERNAL", "message": "일시적인 오류가 발생했습니다."}))
            finally:
                q.put(None)

        Thread(target=run, daemon=True).start()
        while True:
            item = q.get()
            if item is None:
                break
            event, data = item
            yield f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{session_id}/slots", response_model=SlotSeedResponse)
def seed_slots(
    session_id: str,
    payload: SlotSeedRequest,
) -> SlotSeedResponse:
    """구조화 슬롯 결정론 seed (PM-33 Track A).

    마이데이터/건강보험/OCR 의 구조화 데이터(insurer_id·policy_no·진료내역)를 자연어
    왕복 없이 직접 세션 슬롯에 병합한다. LLM 미거침 — 코드 유실·재질문·추출 변동성 제거.
    비로그인 흐름에도 영향 없음(호출 안 하면 기존 동작).
    """
    try:
        return service.seed_slots(session_id, payload.model_dump(exclude_none=True))
    except SessionNotFoundError as exc:
        raise _error("SESSION_NOT_FOUND", _MSG_SESSION_NOT_FOUND, http=404) from exc


@router.get("/{session_id}", response_model=SessionStateResponse)
def get_session_state(session_id: str) -> SessionStateResponse:
    """디버그용 — 세션 현재 상태(슬롯 + history) 조회."""
    try:
        session = service.get_session(session_id)
    except SessionNotFoundError as exc:
        logger.info("get_session_state: 세션 미존재/만료 id=%s", session_id)
        raise _error("SESSION_NOT_FOUND", _MSG_SESSION_NOT_FOUND, http=404) from exc

    return SessionStateResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        last_activity_at=session.last_activity_at,
        status=session.status,
        slots=session.slots,
        history=session.history,
        notes=session.notes,
    )


@router.get("/{session_id}/checklist", response_model=ClaimChecklist)
def get_checklist(session_id: str) -> ClaimChecklist:
    """Sprint 22 — 필요 서류 체크리스트 (area + 슬롯 기반 규칙)."""
    try:
        session = service.get_session(session_id)
    except SessionNotFoundError as exc:
        logger.info("get_checklist: 세션 미존재/만료 id=%s", session_id)
        raise _error("SESSION_NOT_FOUND", _MSG_SESSION_NOT_FOUND, http=404) from exc
    return claims_service.build_checklist(session.slots)


@router.get("/{session_id}/summary", response_model=ClaimSummary)
def get_summary(session_id: str) -> ClaimSummary:
    """Sprint 22 — 청구 준비 요약 (슬롯 + 마지막 assessment + 체크리스트)."""
    try:
        session = service.get_session(session_id)
    except SessionNotFoundError as exc:
        logger.info("get_summary: 세션 미존재/만료 id=%s", session_id)
        raise _error("SESSION_NOT_FOUND", _MSG_SESSION_NOT_FOUND, http=404) from exc
    return claims_service.build_summary(session)


@router.post("/{session_id}/submit", response_model=ClaimReceipt)
def submit_claim(session_id: str) -> ClaimReceipt:
    """Sprint 22 — 청구 접수(가정). 실제 전송 없이 더미 접수 결과 반환."""
    try:
        session = service.get_session(session_id)
    except SessionNotFoundError as exc:
        logger.info("submit_claim: 세션 미존재/만료 id=%s", session_id)
        raise _error("SESSION_NOT_FOUND", _MSG_SESSION_NOT_FOUND, http=404) from exc
    return claims_service.submit_claim(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=JSONResponse)
def delete_session(session_id: str) -> JSONResponse:
    """명시적 세션 폐기. 존재 여부와 무관하게 204 반환 (멱등)."""
    service.close_session(session_id)
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
