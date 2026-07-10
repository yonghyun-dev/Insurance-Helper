"""tests.auth.test_demo_personas

Sprint 26 — 데모 페르소나(이름+전화 매핑) 레지스트리 + demo-personas 엔드포인트.
demo-login 의 DB 라운드트립은 라이브 검증으로 커버.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from app.domains.auth import personas
from app.main import app
from fastapi.testclient import TestClient


class TestResolvePersona:
    def test_match_exact(self):
        rec = personas.resolve_persona("김민서", "010-1234-5678")
        assert rec is not None
        assert rec["external_id"] == "p01"

    def test_phone_normalization(self):
        """하이픈 유무 무관하게 매칭."""
        rec = personas.resolve_persona("김민서", "01012345678")
        assert rec is not None and rec["external_id"] == "p01"

    def test_name_whitespace_normalized(self):
        rec = personas.resolve_persona("  김민서 ", "010-1234-5678")
        assert rec is not None and rec["external_id"] == "p01"

    def test_no_match_returns_none(self):
        assert personas.resolve_persona("없는사람", "010-0000-0000") is None

    def test_empty_returns_none(self):
        assert personas.resolve_persona("", "") is None


class TestListPersonas:
    def test_eleven_personas(self):
        items = personas.list_personas()
        assert len(items) == 11
        assert all({"external_id", "name", "phone", "dob", "label"} <= set(p) for p in items)


class TestSeedAndFind:
    def test_seed_creates_all_then_idempotent(self, session):
        from app.domains.users.models import User

        created = personas.seed_demo_users(session)
        assert created == 11
        rows = session.query(User).all()
        ext_ids = {u.mydata_external_id for u in rows}
        assert ext_ids == {f"p{n:02d}" for n in range(1, 12)}

        # 재실행 멱등 — 신규 0
        assert personas.seed_demo_users(session) == 0

    def test_find_demo_user_match(self, session):
        user = personas.find_demo_user(session, "김민서", "010-1234-5678")
        assert user is not None
        assert user.mydata_external_id == "p01"
        assert user.email == "demo-p01@example.com"

    def test_find_demo_user_miss(self, session):
        assert personas.find_demo_user(session, "없는사람", "010-0000-0000") is None


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    yield TestClient(app)


class TestDemoPersonasEndpoint:
    def test_lists_personas_without_secrets(self, client: TestClient):
        r = client.get("/api/v1/auth/demo-personas")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 11
        first = items[0]
        assert set(first) == {"name", "phone", "dob", "label"}
        # external_id 같은 내부 키는 노출하지 않음
        assert "external_id" not in first
