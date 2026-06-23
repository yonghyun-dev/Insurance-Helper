"""app.domains.auth.schemas

로그인/회원가입 입출력 모델.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.domains.users.schemas import UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """access_token 응답 (또는 cookie 만 사용 시 body 는 user)."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="유효기간 초")
    user: UserRead


class DemoLoginRequest(BaseModel):
    """데모 페르소나 로그인 — 이름+전화로 매핑."""

    name: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=1)


class DemoPersona(BaseModel):
    """데모 페르소나 picker 항목 (시크릿 없음)."""

    name: str
    phone: str
    dob: str
    label: str
