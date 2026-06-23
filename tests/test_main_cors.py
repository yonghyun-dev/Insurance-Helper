"""CORS 미들웨어 동작 회귀 테스트.

Sprint 3 진입 시 브라우저 UI 가 `app/main.py` 의 CORSMiddleware 를 통해 호출 가능한지
확인한다. 화이트리스트 origin 만 허용되고, 그 외는 헤더 미부착이어야 한다.
"""

from __future__ import annotations

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_preflight_allows_whitelisted_origin() -> None:
    response = client.options(
        "/api/v1/sessions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    )
    allowed_methods = response.headers.get("access-control-allow-methods", "")
    assert "POST" in allowed_methods


def test_preflight_rejects_non_whitelisted_origin() -> None:
    response = client.options(
        "/api/v1/sessions",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    # 헤더 미부착 = 브라우저가 차단. status 자체는 200/400 어느 쪽이든 무관.
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_actual_get_attaches_cors_header_for_whitelisted_origin() -> None:
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_preflight_reflects_request_headers_in_allow_headers() -> None:
    """preflight 요청의 Access-Control-Request-Headers 가
    응답 Access-Control-Allow-Headers 에 반영되는지 검증한다.

    브라우저가 content-type 과 커스텀 헤더를 요청했을 때 허용 헤더로 돌아와야
    실제 본 요청이 차단되지 않는다.
    """
    response = client.options(
        "/api/v1/sessions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type, x-custom-header",
        },
    )

    assert response.status_code == 200
    allow_headers = response.headers.get("access-control-allow-headers", "")
    # allow_headers=* 또는 요청된 헤더가 명시적으로 포함돼야 브라우저가 허용한다
    assert allow_headers == "*" or (
        "content-type" in allow_headers.lower()
        and "x-custom-header" in allow_headers.lower()
    )
