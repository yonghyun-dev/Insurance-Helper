"""tests.sessions.test_sessions_router

app/sessions/router.py FastAPI TestClient 테스트.

테스트 대상:
    - POST /api/v1/sessions — 세션 생성 (initial_message 유무)
    - POST /api/v1/sessions/{id}/messages — 메시지 전송 (ask / assessment / 404 / 503)
    - GET  /api/v1/sessions/{id} — 상태 조회 (정상 / 404)
    - DELETE /api/v1/sessions/{id} — 삭제 (멱등 204)

mock 정책:
    - app.domains.sessions.service 함수 전체를 monkeypatch 로 교체
    - 실제 SessionStore / LLM / DB 호출 없음
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from app.domains.sessions.schemas import (
    AssistantAsk,
    AssistantAssessment,
    Citation,
    Message,
    SessionResponse,
    SlotState,
)
from app.domains.sessions.service import SessionNotFoundError
from app.infrastructure.core.exceptions import LLMError, SchemaViolationError
from app.main import app
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _make_session_stub(session_id: str = "test-session-id"):
    """service.create_session 이 반환하는 Session stub."""
    stub = MagicMock()
    stub.session_id = session_id
    stub.created_at = _utcnow()
    stub.last_activity_at = _utcnow()
    stub.status = "gathering"
    stub.slots = SlotState()
    stub.history = []
    return stub


def _make_ask_response(session_id: str = "test-session-id") -> SessionResponse:
    ask = AssistantAsk(
        message="보험사 이름을 알려주세요.",
        expected_slots=["insurer"],
        options=[],
    )
    return SessionResponse(
        session_id=session_id,
        turn=1,
        assistant=ask,
        slots=SlotState(),
        status="gathering",
    )


def _make_assessment_response(session_id: str = "test-session-id") -> SessionResponse:
    cite = Citation(
        chunk_id="c1",
        insurer="한화손해보험",
        product="개인용자동차보험",
        version="2026",
        doc_type="terms",
        clause="제3조",
        sub_no=None,
        text="보험금 지급 기준 관련 조항입니다.",
        page=5,
    )
    assessment = AssistantAssessment(
        likelihood="높음",
        summary="자동차 사고로 인한 보험금 청구 가능성이 높습니다.",
        citations=[cite],
    )
    return SessionResponse(
        session_id=session_id,
        turn=2,
        assistant=assessment,
        slots=SlotState(),
        status="answered",
    )


# ===========================================================================
# POST /api/v1/sessions — 세션 생성
# ===========================================================================


class TestCreateSessionEndpoint:
    """POST /api/v1/sessions 엔드포인트 검증."""

    def test_create_session_returns_201(self, client, monkeypatch):
        # 빈 요청 → 201 Created
        session = _make_session_stub()
        monkeypatch.setattr(
            "app.domains.sessions.router.service.create_session",
            lambda initial_message=None, **kw: (session, None),
        )
        monkeypatch.setattr(
            "app.domains.sessions.router.get_settings",
            lambda: MagicMock(session_ttl_seconds=1800),
        )

        response = client.post("/api/v1/sessions", json={})
        assert response.status_code == 201

    def test_create_session_response_contains_session_id(self, client, monkeypatch):
        session = _make_session_stub("my-session-id")
        monkeypatch.setattr(
            "app.domains.sessions.router.service.create_session",
            lambda initial_message=None, **kw: (session, None),
        )
        monkeypatch.setattr(
            "app.domains.sessions.router.get_settings",
            lambda: MagicMock(session_ttl_seconds=1800),
        )

        response = client.post("/api/v1/sessions", json={})
        data = response.json()
        assert data["session_id"] == "my-session-id"

    def test_create_session_without_body_is_valid(self, client, monkeypatch):
        # body 없이도 201
        session = _make_session_stub()
        monkeypatch.setattr(
            "app.domains.sessions.router.service.create_session",
            lambda initial_message=None, **kw: (session, None),
        )
        monkeypatch.setattr(
            "app.domains.sessions.router.get_settings",
            lambda: MagicMock(session_ttl_seconds=1800),
        )

        response = client.post("/api/v1/sessions")
        assert response.status_code == 201

    def test_create_session_with_initial_message_returns_first_response(
        self, client, monkeypatch
    ):
        # initial_message 있음 → first_response 포함
        session = _make_session_stub()
        first = _make_ask_response(session.session_id)
        monkeypatch.setattr(
            "app.domains.sessions.router.service.create_session",
            lambda initial_message=None, **kw: (session, first),
        )
        monkeypatch.setattr(
            "app.domains.sessions.router.get_settings",
            lambda: MagicMock(session_ttl_seconds=1800),
        )

        response = client.post("/api/v1/sessions", json={"initial_message": "안녕하세요"})
        data = response.json()
        assert data["first_response"] is not None
        assert data["first_response"]["assistant"]["type"] == "ask"

    def test_create_session_llm_error_returns_503(self, client, monkeypatch):
        # LLM 오류 → 503
        def _raise(*args, **kwargs):
            raise LLMError("LLM 호출 실패")

        monkeypatch.setattr("app.domains.sessions.router.service.create_session", _raise)

        response = client.post("/api/v1/sessions", json={"initial_message": "안녕"})
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["error"]["code"] == "LLM_UNAVAILABLE"

    def test_create_session_response_contains_ttl_seconds(self, client, monkeypatch):
        session = _make_session_stub()
        monkeypatch.setattr(
            "app.domains.sessions.router.service.create_session",
            lambda initial_message=None, **kw: (session, None),
        )
        monkeypatch.setattr(
            "app.domains.sessions.router.get_settings",
            lambda: MagicMock(session_ttl_seconds=3600),
        )

        response = client.post("/api/v1/sessions", json={})
        data = response.json()
        assert data["ttl_seconds"] == 3600


# ===========================================================================
# POST /api/v1/sessions/{id}/messages — 메시지 전송
# ===========================================================================


class TestPostMessageEndpoint:
    """POST /api/v1/sessions/{id}/messages 엔드포인트 검증."""

    def test_post_message_ask_response_returns_200(self, client, monkeypatch):
        response_data = _make_ask_response()
        monkeypatch.setattr(
            "app.domains.sessions.router.service.post_message",
            lambda session_id, text, **kw: response_data,
        )

        response = client.post(
            "/api/v1/sessions/test-session-id/messages",
            json={"text": "자동차 사고가 났어요"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["assistant"]["type"] == "ask"

    def test_post_message_assessment_response_returns_200(self, client, monkeypatch):
        response_data = _make_assessment_response()
        monkeypatch.setattr(
            "app.domains.sessions.router.service.post_message",
            lambda session_id, text, **kw: response_data,
        )

        response = client.post(
            "/api/v1/sessions/test-session-id/messages",
            json={"text": "청구하고 싶어요"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["assistant"]["type"] == "assessment"

    def test_post_message_session_not_found_returns_404(self, client, monkeypatch):
        def _raise(session_id, text, **kw):
            raise SessionNotFoundError("세션 없음")

        monkeypatch.setattr("app.domains.sessions.router.service.post_message", _raise)

        response = client.post(
            "/api/v1/sessions/nonexistent/messages",
            json={"text": "안녕하세요"},
        )
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"

    def test_post_message_llm_error_returns_503(self, client, monkeypatch):
        def _raise(session_id, text, **kw):
            raise LLMError("LLM 장애")

        monkeypatch.setattr("app.domains.sessions.router.service.post_message", _raise)

        response = client.post(
            "/api/v1/sessions/test-id/messages",
            json={"text": "안녕하세요"},
        )
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["error"]["code"] == "LLM_UNAVAILABLE"

    def test_post_message_schema_violation_returns_503(self, client, monkeypatch):
        def _raise(session_id, text, **kw):
            raise SchemaViolationError("스키마 위반")

        monkeypatch.setattr("app.domains.sessions.router.service.post_message", _raise)

        response = client.post(
            "/api/v1/sessions/test-id/messages",
            json={"text": "안녕하세요"},
        )
        assert response.status_code == 503

    def test_post_message_empty_text_returns_422(self, client):
        # text 최소 1자 → 빈 문자열 422
        response = client.post(
            "/api/v1/sessions/test-id/messages",
            json={"text": ""},
        )
        assert response.status_code == 422

    def test_post_message_missing_text_field_returns_422(self, client):
        # text 필드 자체 없음 → 422
        response = client.post(
            "/api/v1/sessions/test-id/messages",
            json={},
        )
        assert response.status_code == 422

    def test_post_message_response_contains_session_id(self, client, monkeypatch):
        response_data = _make_ask_response("target-session")
        monkeypatch.setattr(
            "app.domains.sessions.router.service.post_message",
            lambda session_id, text, **kw: response_data,
        )

        response = client.post(
            "/api/v1/sessions/target-session/messages",
            json={"text": "안녕하세요"},
        )
        data = response.json()
        assert data["session_id"] == "target-session"


# ===========================================================================
# GET /api/v1/sessions/{id} — 상태 조회
# ===========================================================================


class TestGetSessionStateEndpoint:
    """GET /api/v1/sessions/{id} 엔드포인트 검증."""

    def test_get_existing_session_returns_200(self, client, monkeypatch):
        session = _make_session_stub("sess-1")
        monkeypatch.setattr(
            "app.domains.sessions.router.service.get_session",
            lambda session_id: session,
        )

        response = client.get("/api/v1/sessions/sess-1")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "sess-1"

    def test_get_session_response_contains_slots(self, client, monkeypatch):
        session = _make_session_stub()
        session.slots = SlotState(area="accident_disease")
        monkeypatch.setattr(
            "app.domains.sessions.router.service.get_session",
            lambda session_id: session,
        )

        response = client.get("/api/v1/sessions/test-session-id")
        data = response.json()
        assert data["slots"]["area"] == "accident_disease"

    def test_get_session_response_contains_history(self, client, monkeypatch):
        session = _make_session_stub()
        session.history = [
            Message(role="user", content="안녕하세요", created_at=_utcnow()),
        ]
        monkeypatch.setattr(
            "app.domains.sessions.router.service.get_session",
            lambda session_id: session,
        )

        response = client.get("/api/v1/sessions/test-session-id")
        data = response.json()
        assert len(data["history"]) == 1
        assert data["history"][0]["role"] == "user"

    def test_get_nonexistent_session_returns_404(self, client, monkeypatch):
        def _raise(session_id):
            raise SessionNotFoundError("세션 없음")

        monkeypatch.setattr("app.domains.sessions.router.service.get_session", _raise)

        response = client.get("/api/v1/sessions/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


# ===========================================================================
# DELETE /api/v1/sessions/{id} — 삭제 (멱등)
# ===========================================================================


class TestDeleteSessionEndpoint:
    """DELETE /api/v1/sessions/{id} 엔드포인트 검증."""

    def test_delete_existing_session_returns_204(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.domains.sessions.router.service.close_session",
            lambda session_id: True,
        )

        response = client.delete("/api/v1/sessions/test-session-id")
        assert response.status_code == 204

    def test_delete_nonexistent_session_returns_204(self, client, monkeypatch):
        # 없는 세션도 204 (멱등)
        monkeypatch.setattr(
            "app.domains.sessions.router.service.close_session",
            lambda session_id: False,
        )

        response = client.delete("/api/v1/sessions/nonexistent-id")
        assert response.status_code == 204

    def test_delete_twice_both_return_204(self, client, monkeypatch):
        # 두 번 삭제해도 모두 204
        call_count = [0]

        def _close(session_id):
            call_count[0] += 1
            return call_count[0] == 1  # 첫 번째만 True

        monkeypatch.setattr("app.domains.sessions.router.service.close_session", _close)

        r1 = client.delete("/api/v1/sessions/test-id")
        r2 = client.delete("/api/v1/sessions/test-id")
        assert r1.status_code == 204
        assert r2.status_code == 204
