"""app.domains.sessions.store

파일 경로: app/sessions/store.py
목적: 인메모리 세션 저장소. dict + lazy TTL 만료 처리.

설계 결정 (data-model.md § 세션 모델 / tech-decisions.md § 4):
    - 단일 프로세스 가정 (PoC). 여러 프로세스 또는 분산 환경은 Sprint 5+ 에 외부 store 로 교체
    - lazy expiration: 매 조회 시 만료 검사 → 별도 background cleanup 스레드 불필요
    - race condition: PoC 단일 사용자 가정으로 lock 없음 (Sprint 5+ asyncio.Lock)
    - TTL: settings.session_ttl_seconds (기본 1800 = 30분)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import lru_cache

from app.domains.sessions.schemas import Session, SessionStatus, SlotState
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TTL_SECONDS = 1800
"""세션 TTL 기본값. settings.session_ttl_seconds 로 override 가능."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SessionStore:
    """세션 인메모리 저장소.

    인스턴스는 `get_session_store()` 로 얻는다 (싱글톤). 직접 생성 X.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._sessions: dict[str, Session] = {}
        self._ttl_seconds = ttl_seconds

    # ---------- CRUD ----------

    def create(self) -> Session:
        """새 세션을 생성하고 저장한다."""
        now = _utcnow()
        session = Session(
            session_id=str(uuid.uuid4()),
            created_at=now,
            last_activity_at=now,
            status="gathering",
            slots=SlotState(),
            history=[],
        )
        self._sessions[session.session_id] = session
        logger.info("세션 생성: ...%s (TTL=%ds)", session.session_id[-8:], self._ttl_seconds)
        return session

    def get(self, session_id: str) -> Session | None:
        """세션 조회. 만료된 경우 자동 삭제 후 None.

        Returns:
            Session 또는 None (만료/없음).
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired(_utcnow(), self._ttl_seconds):
            del self._sessions[session_id]
            logger.info("세션 만료 자동 삭제: ...%s", session_id[-8:])
            return None
        return session

    def touch(self, session: Session, *, status: SessionStatus | None = None) -> None:
        """세션의 `last_activity_at` 을 현재 시각으로 갱신한다.

        Args:
            session: 갱신할 세션 (in-place 변경, dict 가 같은 객체 참조)
            status: 새 상태 (None 이면 유지)

        Note:
            slots/history 변경은 in-place 수정만으로 store 에 반영된다 — 별도 save 불필요.
        """
        session.last_activity_at = _utcnow()
        if status is not None:
            session.status = status

    def delete(self, session_id: str) -> bool:
        """명시적 세션 폐기."""
        existed = session_id in self._sessions
        self._sessions.pop(session_id, None)
        if existed:
            logger.info("세션 명시적 삭제: ...%s", session_id[-8:])
        return existed

    # ---------- 운영 헬퍼 ----------

    def count(self) -> int:
        """현재 보관 중인 세션 수 (만료 검사 없이)."""
        return len(self._sessions)

    def purge_expired(self) -> int:
        """만료된 모든 세션을 일괄 제거. 운영 디버깅용.

        Returns:
            제거된 세션 수.
        """
        now = _utcnow()
        expired_ids = [
            sid for sid, s in self._sessions.items() if s.is_expired(now, self._ttl_seconds)
        ]
        for sid in expired_ids:
            del self._sessions[sid]
        if expired_ids:
            logger.info("만료 세션 일괄 제거: %d", len(expired_ids))
        return len(expired_ids)


@lru_cache(maxsize=1)
def get_session_store() -> SessionStore:
    """프로세스 단일 SessionStore 인스턴스를 반환한다."""
    settings = get_settings()
    return SessionStore(ttl_seconds=settings.session_ttl_seconds)
