"""app.domains.auth.router

Sprint 14 인증 endpoint:
    - POST /api/v1/auth/signup — 회원가입
    - POST /api/v1/auth/login — 로그인 → access_token + cookie
    - GET  /api/v1/auth/me — 현재 사용자 (인증 필수)
    - GET  /api/v1/auth/me/insurances — 마이데이터 가입 보험 조회
    - POST /api/v1/auth/logout — cookie 폐기

cookie 정책 (tech-decisions § Sprint 14 결정 2):
    - HttpOnly + Secure + SameSite=Lax
    - 만료 동일 (jwt_exp_minutes)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.domains.auth.deps import COOKIE_NAME, get_current_user_optional
from app.domains.auth.jwt import create_access_token
from app.domains.auth.schemas import LoginRequest, TokenResponse
from app.domains.users import service as users_service
from app.domains.users.models import User
from app.domains.users.schemas import UserCreate, UserRead
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.database import session_scope
from app.infrastructure.core.exceptions import DomainError

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_token_cookie(response: Response, token: str, exp_minutes: int) -> None:
    """HttpOnly cookie 세팅."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=exp_minutes * 60,
        httponly=True,
        secure=False,  # 운영에서는 True (HTTPS), dev SQLite/localhost 환경 False
        samesite="lax",
    )


@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate) -> UserRead:
    """신규 사용자 등록."""
    with session_scope() as session:
        try:
            user = users_service.create_user(session, payload)
        except DomainError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "EMAIL_ALREADY_REGISTERED", "message": str(exc)},
            ) from exc
        return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response) -> TokenResponse:
    """email + password 검증 → access_token + HttpOnly cookie."""
    settings = get_settings()
    with session_scope() as session:
        user = users_service.authenticate(session, str(payload.email), payload.password)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_CREDENTIALS", "message": "이메일 또는 비밀번호가 올바르지 않습니다"},
            )
        token = create_access_token(user.id)
        _set_token_cookie(response, token, settings.jwt_exp_minutes)
        return TokenResponse(
            access_token=token,
            expires_in=settings.jwt_exp_minutes * 60,
            user=UserRead.model_validate(user),
        )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def logout() -> Response:
    """cookie 폐기 — 토큰 자체는 만료될 때까지 유효 (refresh 없음)."""
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    resp.delete_cookie(key=COOKIE_NAME)
    return resp


@router.get("/me", response_model=UserRead)
def me(
    current_user: User | None = Depends(get_current_user_optional),  # noqa: B008
) -> UserRead:
    """현재 사용자. 비로그인 시 401."""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "로그인 필요"},
        )
    return UserRead.model_validate(current_user)


@router.get("/me/insurances")
def me_insurances(
    current_user: User | None = Depends(get_current_user_optional),  # noqa: B008
) -> dict[str, Any]:
    """마이데이터 어댑터를 통한 가입 보험 조회. 비로그인 시 401.

    Sprint 14 — DummyAdapter 가 기본 (mydata_backend=dummy).
    실 API 활성 (mydata_backend=real) 은 사업자 인증 발급 후.
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "로그인 필요"},
        )

    from app.infrastructure.external.mydata.adapter import get_mydata_adapter

    adapter = get_mydata_adapter()
    insurances = adapter.fetch_insurances(str(current_user.id))
    return {"insurances": insurances}
