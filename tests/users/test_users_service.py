"""tests.users.test_users_service

app/users/service.py 단위 테스트.

테스트 대상:
    - hash_password / verify_password — bcrypt round trip
    - create_user — 신규 + 중복 email 거부
    - get_by_email / get_by_id — 존재/미존재
    - authenticate — 정상/잘못된 비밀번호/미존재 email
"""

from __future__ import annotations

import pytest
from app.domains.users import service as users_service
from app.domains.users.schemas import UserCreate
from app.infrastructure.core.exceptions import DomainError
from sqlalchemy.orm import Session


@pytest.fixture
def user_session(tmp_settings) -> Session:
    """tmp_settings fixture (conftest) 기반 새 DB 세션."""
    # 모든 모델 등록 보장
    import app  # noqa: F401
    from app.domains.users.models import User as _  # noqa: F401  # models 등록 보장
    from app.infrastructure.core.database import get_engine, get_sessionmaker

    engine = get_engine()
    # 테이블 생성 (alembic 대신 metadata create_all — 테스트 격리)
    from app.infrastructure.core.database import Base

    Base.metadata.create_all(engine)

    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


class TestPasswordHashing:
    def test_hash_returns_different_for_same_password(self):
        h1 = users_service.hash_password("secret123")
        h2 = users_service.hash_password("secret123")
        assert h1 != h2  # salt 무작위

    def test_verify_matches_correct_password(self):
        hashed = users_service.hash_password("mySecret!")
        assert users_service.verify_password("mySecret!", hashed) is True

    def test_verify_rejects_wrong_password(self):
        hashed = users_service.hash_password("mySecret!")
        assert users_service.verify_password("wrong", hashed) is False


class TestCreateUser:
    def test_creates_user_with_hashed_password(self, user_session):
        payload = UserCreate(email="alice@example.com", password="password123")
        user = users_service.create_user(user_session, payload)
        assert user.id is not None
        assert user.email == "alice@example.com"
        assert user.password_hash != "password123"

    def test_duplicate_email_raises(self, user_session):
        payload = UserCreate(email="dup@example.com", password="password123")
        users_service.create_user(user_session, payload)
        user_session.flush()
        with pytest.raises(DomainError, match="이미 등록"):
            users_service.create_user(user_session, payload)


class TestGetByEmail:
    def test_returns_user_when_exists(self, user_session):
        users_service.create_user(
            user_session,
            UserCreate(email="found@example.com", password="password123"),
        )
        user_session.flush()
        result = users_service.get_by_email(user_session, "found@example.com")
        assert result is not None
        assert result.email == "found@example.com"

    def test_returns_none_when_missing(self, user_session):
        result = users_service.get_by_email(user_session, "missing@example.com")
        assert result is None


class TestAuthenticate:
    def test_returns_user_on_valid_credentials(self, user_session):
        users_service.create_user(
            user_session,
            UserCreate(email="auth@example.com", password="correct123"),
        )
        user_session.flush()
        user = users_service.authenticate(user_session, "auth@example.com", "correct123")
        assert user is not None
        assert user.email == "auth@example.com"

    def test_returns_none_on_wrong_password(self, user_session):
        users_service.create_user(
            user_session,
            UserCreate(email="auth2@example.com", password="correct123"),
        )
        user_session.flush()
        user = users_service.authenticate(user_session, "auth2@example.com", "wrong")
        assert user is None

    def test_returns_none_for_unknown_email(self, user_session):
        user = users_service.authenticate(user_session, "nobody@example.com", "anything")
        assert user is None
