"""처리되지 않은 예외 → 표준 INTERNAL_ERROR 응답 변환 검증.

Sprint 3 부터 추가된 `app.main._unhandled_exception_handler` 가 사양서
(`docs/design/ui-states.md § 3`) 표준 형태로 응답하는지 확인한다.
"""

from __future__ import annotations

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture()
def client_raise_on_server_errors() -> TestClient:
    """예외를 자동 재발생하지 않는 TestClient (handler 응답을 받기 위함)."""
    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_exception_returns_standard_error_envelope(
    client_raise_on_server_errors: TestClient,
) -> None:
    @app.get("/__test_boom__", include_in_schema=False)
    def _boom() -> dict[str, str]:
        raise RuntimeError("intentional test failure")

    try:
        response = client_raise_on_server_errors.get("/__test_boom__")

        assert response.status_code == 500
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert isinstance(body["error"]["message"], str)
        assert "내부" not in body["error"]["message"]  # 내부 상세 노출 안 함
    finally:
        # 테스트 전용 라우트 정리
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/__test_boom__"]
