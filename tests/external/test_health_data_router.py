"""tests.external.test_health_data_router

Sprint 18 — GET /api/v1/me/health/history 엔드포인트.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from app.domains.auth.jwt import create_access_token
from app.infrastructure.core.config import get_settings
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """모든 테스트에 JWT secret 주입 (tests/auth/test_auth_jwt.py 와 동일)."""
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-jwt-min-32-chars-1234")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    yield TestClient(app)


def _login_token(user_id: int) -> str:
    return create_access_token(user_id)


class TestHealthHistoryEndpoint:
    def test_unauthorized_returns_401(self, client: TestClient):
        r = client.get("/api/v1/me/health/history")
        assert r.status_code == 401
        body = r.json()
        assert body["detail"]["code"] == "UNAUTHORIZED"

    def test_authorized_user1_single_treatment(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        from app.domains.users import service as users_service

        # 가짜 User row — 데모 페르소나 p01 연결
        class _U:
            id = 1
            email = "u1@test.local"
            mydata_external_id = "p01"

        monkeypatch.setattr(users_service, "get_by_id", lambda _s, _i: _U())

        token = _login_token(1)
        r = client.get(
            "/api/v1/me/health/history", cookies={"access_token": token}
        )
        assert r.status_code == 200
        body = r.json()
        assert "treatments" in body
        assert len(body["treatments"]) == 1
        t = body["treatments"][0]
        assert t["hospital_name"] == "서울정형외과의원"
        assert t["claim_amount"] == 820000
        assert t["slot_mapping"]["diagnosis"] == "발목 골절"
        assert t["slot_mapping"]["area"] == "accident_disease"

    def test_authorized_user2_multi_treatments(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        from app.domains.users import service as users_service

        class _U:
            id = 2
            email = "u2@test.local"
            mydata_external_id = "p02"

        monkeypatch.setattr(users_service, "get_by_id", lambda _s, _i: _U())
        token = _login_token(2)
        r = client.get(
            "/api/v1/me/health/history", cookies={"access_token": token}
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["treatments"]) == 3
        in_hospital = [t for t in body["treatments"] if t["is_hospitalization"]]
        assert len(in_hospital) == 1

    def test_unknown_user_returns_empty_list(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        from app.domains.users import service as users_service

        class _U:
            id = 9999
            email = "noone@test.local"
            mydata_external_id = "no-such-persona"

        monkeypatch.setattr(users_service, "get_by_id", lambda _s, _i: _U())
        token = _login_token(9999)
        r = client.get(
            "/api/v1/me/health/history", cookies={"access_token": token}
        )
        assert r.status_code == 200
        assert r.json() == {"treatments": []}

    def test_real_backend_returns_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        from app.domains.users import service as users_service
        from app.infrastructure.core import config
        from app.infrastructure.external.health_data import adapter as adapter_mod

        class _U:
            id = 1
            email = "u1@test.local"
            mydata_external_id = "p01"

        monkeypatch.setattr(users_service, "get_by_id", lambda _s, _i: _U())
        monkeypatch.setenv("HEALTH_DATA_BACKEND", "real")
        config.get_settings.cache_clear()
        adapter_mod.clear_cache()
        try:
            token = _login_token(1)
            r = client.get(
                "/api/v1/me/health/history", cookies={"access_token": token}
            )
            assert r.status_code == 503
            assert r.json()["detail"]["code"] == "HEALTH_DATA_NOT_CONFIGURED"
        finally:
            adapter_mod.clear_cache()
            config.get_settings.cache_clear()
