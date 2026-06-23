"""tests.sessions.test_sessions_router_auth

Sprint 14.1 (REQ-10) — sessions API 인증 옵셔널 + audit user_id 흐름 회귀.

테스트 대상:
    - 인증 헤더 없는 기존 요청 (비로그인) 회귀 0 — service.create_session(user_id=None)
    - 유효한 access_token cookie 시 service.create_session(user_id=int)
    - 만료/위변조 cookie 시 user_id=None 폴백
    - post_message 도 동일 패턴
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from app.domains.sessions.schemas import (
    AssistantAsk,
    Session,
    SessionResponse,
    SlotState,
)
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-min-32-chars-1234567890")
    from app.infrastructure.core.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    return TestClient(app)


def _make_session() -> Session:
    now = datetime.now(UTC)
    return Session(
        session_id="test-session",
        created_at=now,
        last_activity_at=now,
        status="gathering",
        slots=SlotState(),
        history=[],
    )


def _make_ask_response(session_id: str = "test-session") -> SessionResponse:
    return SessionResponse(
        session_id=session_id,
        turn=1,
        assistant=AssistantAsk(
            type="ask",
            message="질문",
            expected_slots=["area"],
            options=[],
        ),
        slots=SlotState(),
        status="gathering",
    )


class TestCreateSessionAuth:
    def test_unauthenticated_passes_user_id_none(self, client, monkeypatch):
        """인증 헤더 없음 → service.create_session(user_id=None)."""
        captured: dict = {}

        def fake_create(initial_message=None, *, user_id=None):
            captured["user_id"] = user_id
            return _make_session(), None

        monkeypatch.setattr("app.domains.sessions.router.service.create_session", fake_create)
        monkeypatch.setattr(
            "app.domains.sessions.router.get_settings",
            lambda: MagicMock(session_ttl_seconds=1800),
        )

        response = client.post("/api/v1/sessions", json={})
        assert response.status_code == 201
        assert captured["user_id"] is None

    def test_invalid_cookie_passes_user_id_none(self, client, monkeypatch):
        """위변조 cookie → decode_access_token None → user_id=None."""
        captured: dict = {}

        def fake_create(initial_message=None, *, user_id=None):
            captured["user_id"] = user_id
            return _make_session(), None

        monkeypatch.setattr("app.domains.sessions.router.service.create_session", fake_create)
        monkeypatch.setattr(
            "app.domains.sessions.router.get_settings",
            lambda: MagicMock(session_ttl_seconds=1800),
        )

        client.cookies.set("access_token", "garbage-not-a-jwt")
        response = client.post("/api/v1/sessions", json={})
        assert response.status_code == 201
        assert captured["user_id"] is None


class TestPostMessageAuth:
    def test_unauthenticated_passes_user_id_none(self, client, monkeypatch):
        captured: dict = {}

        def fake_post(session_id, text, *, user_id=None):
            captured["user_id"] = user_id
            return _make_ask_response()

        monkeypatch.setattr("app.domains.sessions.router.service.post_message", fake_post)

        response = client.post(
            "/api/v1/sessions/test-session/messages",
            json={"text": "안녕하세요"},
        )
        assert response.status_code == 200
        assert captured["user_id"] is None

    def test_invalid_cookie_passes_user_id_none(self, client, monkeypatch):
        captured: dict = {}

        def fake_post(session_id, text, *, user_id=None):
            captured["user_id"] = user_id
            return _make_ask_response()

        monkeypatch.setattr("app.domains.sessions.router.service.post_message", fake_post)

        client.cookies.set("access_token", "not-a-valid-jwt")
        response = client.post(
            "/api/v1/sessions/test-session/messages",
            json={"text": "테스트"},
        )
        assert response.status_code == 200
        assert captured["user_id"] is None


class TestAuditContextUserId:
    def test_audit_begin_user_id_optional_default_none(self):
        from app.shared.audit.service import begin

        ctx = begin(session_id="s1", turn=1, raw_user_input="hi")
        assert ctx.user_id is None

    def test_audit_begin_user_id_passed_through(self):
        from app.shared.audit.service import begin

        ctx = begin(session_id="s1", turn=1, raw_user_input="hi", user_id=42)
        assert ctx.user_id == 42
