"""app.domains.auth.deps

FastAPI dependency — get_current_user_optional.

Sprint 14 비로그인 호환 (REQ-10): 인증 헤더/쿠키 없으면 None 반환.
sessions API 등 비로그인 endpoint 도 본 dependency 로 user_id 기록 옵셔널화.
"""

from __future__ import annotations

from fastapi import Cookie, Depends, Header
from sqlalchemy.orm import Session

from app.domains.auth.jwt import decode_access_token
from app.domains.users import service as users_service
from app.domains.users.models import User
from app.infrastructure.core.database import get_db_session

COOKIE_NAME = "access_token"
BEARER_PREFIX = "Bearer "


def get_current_user_optional(
    access_token_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_db_session),  # noqa: B008  # FastAPI DI 패턴
) -> User | None:
    """인증 옵셔널 — 토큰 없음/위변조/만료 시 None.

    토큰 우선순위: cookie (HttpOnly) > Authorization Bearer.
    """
    token: str | None = access_token_cookie
    if not token and authorization and authorization.startswith(BEARER_PREFIX):
        token = authorization[len(BEARER_PREFIX) :]

    if not token:
        return None

    user_id = decode_access_token(token)
    if user_id is None:
        return None

    return users_service.get_by_id(session, user_id)
