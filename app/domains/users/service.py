"""app.domains.users.service

User CRUD + bcrypt 해시.
"""

from __future__ import annotations

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.users.models import User
from app.domains.users.schemas import UserCreate
from app.infrastructure.core.exceptions import DomainError

# bcrypt 12 rounds — 표준 PoC
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """bcrypt 해시 (12 rounds)."""
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """bcrypt 검증."""
    return _pwd_context.verify(plain, hashed)


def create_user(session: Session, payload: UserCreate) -> User:
    """신규 사용자 생성. 중복 email 은 DomainError.

    Raises:
        DomainError: email 중복
    """
    if get_by_email(session, str(payload.email)) is not None:
        raise DomainError(f"이미 등록된 이메일: {payload.email}")

    user = User(email=str(payload.email), password_hash=hash_password(payload.password))
    session.add(user)
    session.flush()  # id 부여
    return user


def get_by_email(session: Session, email: str) -> User | None:
    """email 로 사용자 조회. 미존재 시 None."""
    return session.execute(select(User).where(User.email == email)).scalar_one_or_none()


def get_by_id(session: Session, user_id: int) -> User | None:
    """id 로 사용자 조회. 미존재 시 None."""
    return session.get(User, user_id)


def authenticate(session: Session, email: str, password: str) -> User | None:
    """email + password 검증. 성공 시 User, 실패 시 None."""
    user = get_by_email(session, email)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
