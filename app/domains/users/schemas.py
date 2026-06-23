"""app.domains.users.schemas

User pydantic 입출력 모델.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """signup 요청."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128, description="평문 — bcrypt 해시 후 저장")


class UserRead(BaseModel):
    """공개 응답 (password_hash 제외)."""

    id: int
    email: EmailStr
    created_at: datetime

    model_config = {"from_attributes": True}
