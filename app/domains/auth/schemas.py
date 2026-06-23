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
