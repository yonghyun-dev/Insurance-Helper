"""tests.claims.test_claims_router

세션 스코프 청구 엔드포인트(GET checklist/summary, POST submit) TestClient 테스트.
service.get_session 을 monkeypatch 로 교체해 store 의존 없이 검증.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.domains.sessions.schemas import Session, SlotState
from app.domains.sessions.service import SessionNotFoundError
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _session() -> Session:
    return Session(
        session_id="rt1",
        created_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
        slots=SlotState(
            area="accident_disease",
            insurer="한화손해보험",
            product="실손보험",
            hospitalization_days=2,
        ),
    )


def _patch_session(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.domains.sessions.router.service.get_session", lambda _sid: _session()
    )


def _patch_not_found(monkeypatch) -> None:
    def _raise(_sid):
        raise SessionNotFoundError("x")

    monkeypatch.setattr("app.domains.sessions.router.service.get_session", _raise)


class TestChecklistEndpoint:
    def test_ok(self, client, monkeypatch):
        _patch_session(monkeypatch)
        r = client.get("/api/v1/sessions/rt1/checklist")
        assert r.status_code == 200
        d = r.json()
        assert d["area"] == "accident_disease"
        ids = {i["id"] for i in d["items"]}
        assert {"claim_form", "diagnosis", "admission_cert"} <= ids

    def test_404(self, client, monkeypatch):
        _patch_not_found(monkeypatch)
        assert client.get("/api/v1/sessions/none/checklist").status_code == 404


class TestSummaryEndpoint:
    def test_ok(self, client, monkeypatch):
        _patch_session(monkeypatch)
        d = client.get("/api/v1/sessions/rt1/summary").json()
        assert d["insurer"] == "한화손해보험"
        assert d["product"] == "실손보험"
        assert len(d["checklist"]) >= 3

    def test_404(self, client, monkeypatch):
        _patch_not_found(monkeypatch)
        assert client.get("/api/v1/sessions/none/summary").status_code == 404


class TestSubmitEndpoint:
    def test_ok(self, client, monkeypatch):
        _patch_session(monkeypatch)
        d = client.post("/api/v1/sessions/rt1/submit").json()
        assert d["receipt_no"].startswith("CLM-")
        assert d["status"] == "접수완료"
        assert d["insurer"] == "한화손해보험"

    def test_404(self, client, monkeypatch):
        _patch_not_found(monkeypatch)
        assert client.post("/api/v1/sessions/none/submit").status_code == 404
