"""tests.auth.test_auth_jwt

app/auth/jwt.py 단위 테스트.

테스트 대상:
    - create_access_token — secret 미설정 시 ConfigurationError
    - decode_access_token — 정상/만료/위변조/secret 미설정 시 None
"""

from __future__ import annotations

import pytest
from app.domains.auth.jwt import create_access_token, decode_access_token
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.exceptions import ConfigurationError


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    """모든 테스트에 JWT secret 주입."""
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-jwt-min-32-chars-1234")
    # Settings lru_cache 초기화
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestCreateAccessToken:
    def test_creates_token_with_user_id(self):
        token = create_access_token(42)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_round_trip_user_id(self):
        token = create_access_token(42)
        assert decode_access_token(token) == 42

    def test_raises_when_secret_missing(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", "")
        get_settings.cache_clear()
        with pytest.raises(ConfigurationError, match="JWT_SECRET_KEY"):
            create_access_token(1)


class TestDecodeAccessToken:
    def test_decode_valid_token(self):
        token = create_access_token(123)
        assert decode_access_token(token) == 123

    def test_returns_none_for_invalid_token(self):
        assert decode_access_token("not.a.valid.jwt") is None

    def test_returns_none_for_empty_string(self):
        assert decode_access_token("") is None

    def test_returns_none_for_garbage(self):
        assert decode_access_token("garbage") is None

    def test_returns_none_when_secret_missing(self, monkeypatch):
        token = create_access_token(1)
        monkeypatch.setenv("JWT_SECRET_KEY", "")
        get_settings.cache_clear()
        assert decode_access_token(token) is None

    def test_returns_none_for_tampered_token(self):
        token = create_access_token(99)
        tampered = token[:-5] + "XXXXX"
        assert decode_access_token(tampered) is None

    def test_expired_token_returns_none(self):
        token = create_access_token(1, expires_minutes=-1)
        assert decode_access_token(token) is None
