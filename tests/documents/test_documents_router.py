"""tests.documents.test_documents_router

app/documents/router.py 의 read-only 엔드포인트 통합 테스트.

`get_db_session` Depends 를 in-memory 엔진(thread-safe StaticPool) 기반 세션 팩토리로
교체해, TestClient 의 worker thread 가 router 를 호출해도 동일 connection 을 본다.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.domains.documents.service import register_document
from app.infrastructure.core.database import Base, get_db_session
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def shared_engine():
    """thread-safe in-memory SQLite — StaticPool 로 단일 connection 공유."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
        echo=False,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def seed_session(shared_engine):
    """테스트 setup 용 세션. seed 후 commit 한다."""
    factory = sessionmaker(bind=shared_engine, expire_on_commit=False, future=True)
    sess = factory()
    try:
        yield sess
    finally:
        sess.rollback()
        sess.close()


@pytest.fixture()
def client(shared_engine):
    """router 가 호출될 때마다 새 세션을 발급하는 TestClient."""
    factory = sessionmaker(bind=shared_engine, expire_on_commit=False, future=True)

    def _override_get_db():
        sess = factory()
        try:
            yield sess
        finally:
            sess.close()

    app.dependency_overrides[get_db_session] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed(session, **overrides) -> None:
    """register_document 호출용 기본 파라미터를 채워 한 건 적재 후 commit."""
    params = dict(
        insurer_id="hanwha",
        insurer_name="한화손해보험",
        area="auto",
        product_id="hanwha_auto",
        product_name="한화 자동차",
        valid_from=date(2026, 1, 1),
        valid_to=None,
        version_label="2026-01-01_present",
        doc_type="terms",
        file_path="/tmp/hanwha_auto.pdf",
        file_sha256="a" * 64,
        page_count=10,
        parser_version="0.1.0",
    )
    params.update(overrides)
    register_document(session, **params)
    session.commit()


# ===========================================================================
# GET /documents/insurers
# ===========================================================================


def test_list_insurers_empty_returns_empty_array(client) -> None:
    response = client.get("/api/v1/documents/insurers")

    assert response.status_code == 200
    assert response.json() == []


def test_list_insurers_returns_registered_insurers(client, seed_session) -> None:
    _seed(seed_session)
    _seed(
        seed_session,
        insurer_id="samsung",
        insurer_name="삼성화재",
        product_id="samsung_fire",
        area="fire",
        file_sha256="b" * 64,
    )

    response = client.get("/api/v1/documents/insurers")
    body = response.json()

    assert response.status_code == 200
    assert {i["id"] for i in body} == {"hanwha", "samsung"}
    hanwha = next(i for i in body if i["id"] == "hanwha")
    assert hanwha["name"] == "한화손해보험"


# ===========================================================================
# GET /documents/products
# ===========================================================================


def test_list_products_returns_all_when_no_filter(client, seed_session) -> None:
    _seed(seed_session)
    _seed(
        seed_session,
        insurer_id="samsung",
        insurer_name="삼성화재",
        product_id="samsung_fire",
        area="fire",
        file_sha256="b" * 64,
    )

    response = client.get("/api/v1/documents/products")
    body = response.json()

    assert response.status_code == 200
    assert {p["id"] for p in body} == {"hanwha_auto", "samsung_fire"}


def test_list_products_filter_by_insurer(client, seed_session) -> None:
    _seed(seed_session)
    _seed(
        seed_session,
        insurer_id="samsung",
        insurer_name="삼성화재",
        product_id="samsung_fire",
        area="fire",
        file_sha256="b" * 64,
    )

    response = client.get("/api/v1/documents/products?insurer=hanwha")
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 1
    assert body[0]["id"] == "hanwha_auto"


def test_list_products_filter_by_area(client, seed_session) -> None:
    _seed(seed_session)
    _seed(
        seed_session,
        insurer_id="samsung",
        insurer_name="삼성화재",
        product_id="samsung_fire",
        area="fire",
        file_sha256="b" * 64,
    )

    response = client.get("/api/v1/documents/products?area=fire")
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 1
    assert body[0]["area"] == "fire"


def test_list_products_unknown_insurer_returns_empty(client, seed_session) -> None:
    _seed(seed_session)

    response = client.get("/api/v1/documents/products?insurer=nonexistent")

    assert response.status_code == 200
    assert response.json() == []


def test_list_products_filter_by_insurer_and_area_combined(
    client, seed_session
) -> None:
    """insurer + area 동시 필터 — 두 조건 모두 만족하는 상품만 반환되어야 한다.

    데이터:
        hanwha / auto  → hanwha_auto
        hanwha / fire  → hanwha_fire
        samsung / auto → samsung_auto

    insurer=hanwha & area=fire 로 조회하면 hanwha_fire 1건만 반환.
    """
    # hanwha auto
    _seed(seed_session)
    # hanwha fire
    _seed(
        seed_session,
        product_id="hanwha_fire",
        area="fire",
        file_sha256="b" * 64,
    )
    # samsung auto
    _seed(
        seed_session,
        insurer_id="samsung",
        insurer_name="삼성화재",
        product_id="samsung_auto",
        area="auto",
        file_sha256="c" * 64,
    )

    response = client.get("/api/v1/documents/products?insurer=hanwha&area=fire")
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 1
    assert body[0]["id"] == "hanwha_fire"
    assert body[0]["area"] == "fire"
