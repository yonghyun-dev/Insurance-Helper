"""app.domains.sessions

파일 경로: app/sessions/__init__.py
목적: 멀티턴 대화 세션 도메인. HTTP API + CLI `ica chat` 양쪽이 본 도메인 service 를 공유한다.

원칙(domain-architecture):
    - router/CLI 는 본 도메인의 service 만 호출. crud/store 직접 참조 금지
    - 다른 도메인은 service 레벨에서만 import (chunks.service, search.service)
    - 본 도메인은 자체 SQLAlchemy 모델 없음 — Session 은 in-memory pydantic 모델

핵심 컴포넌트:
    - schemas.py — Session/SlotState/Message/AssistantResponse(Ask|Assessment) pydantic
    - store.py   — SessionStore (dict + lazy TTL 만료)
    - llm.py     — OpenAI Chat Completions + Function Calling 어댑터 (Sprint2-T2)
    - service.py — post_message 오케스트레이션 (Sprint2-T4)
    - router.py  — HTTP API endpoints (Sprint2-T5)
"""

from app.domains.sessions.schemas import (
    AssistantAsk,
    AssistantAssessment,
    Citation,
    Message,
    MessageRequest,
    Session,
    SessionCreate,
    SessionResponse,
    SessionStatus,
    SlotState,
)
from app.domains.sessions.store import DEFAULT_TTL_SECONDS, SessionStore, get_session_store

__all__ = [
    "AssistantAsk",
    "AssistantAssessment",
    "Citation",
    "DEFAULT_TTL_SECONDS",
    "Message",
    "MessageRequest",
    "Session",
    "SessionCreate",
    "SessionResponse",
    "SessionStatus",
    "SessionStore",
    "SlotState",
    "get_session_store",
]
