"""app.domains.auth.jwt

JWT 발급/검증. HS256 + access token only (60분 만료, refresh 없음).

설계 (tech-decisions § Sprint 14 결정 2):
    - PoC 단순화 — refresh token 후속 검토
    - sub claim 에 user_id (str)
    - 만료/위변조/시그니처 불일치 시 None 반환 (예외 raise 안 함)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.infrastructure.core.config import get_settings
from app.infrastructure.core.exceptions import ConfigurationError


def create_access_token(user_id: int, *, expires_minutes: int | None = None) -> str:
    """user_id 에 대한 access token 생성.

    Args:
        user_id: User.id
        expires_minutes: 만료 분 (기본 Settings.jwt_exp_minutes)

    Raises:
        ConfigurationError: JWT_SECRET_KEY 미설정
    """
    settings = get_settings()
    if not settings.jwt_secret_key:
        raise ConfigurationError("JWT_SECRET_KEY 미설정 — 운영 환경에서 인증 endpoint 사용 불가")

    exp_minutes = expires_minutes if expires_minutes is not None else settings.jwt_exp_minutes
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) + timedelta(minutes=exp_minutes),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_alg)


def decode_access_token(token: str) -> int | None:
    """token → user_id. 위변조/만료/시크릿 미설정 시 None.

    Returns:
        user_id (int) 또는 None
    """
    settings = get_settings()
    if not settings.jwt_secret_key:
        return None

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_alg])
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        return int(user_id_str)
    except (JWTError, ValueError, TypeError):
        return None
