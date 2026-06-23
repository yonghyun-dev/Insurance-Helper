"""tests.test_main_metrics

app/main.py 의 /metrics 엔드포인트 단위 테스트.

테스트 대상:
    - prometheus_enabled=True → 200 + text/plain 응답 + prometheus 포맷 포함
    - prometheus_enabled=False → 404

mock 정책:
    - FastAPI TestClient 사용 (기존 main.py TestClient 패턴 동일)
    - prometheus_enabled 분기는 _settings 재패치 방식 사용 (main 모듈 레벨 변수)
    - slowapi 는 rate_limit_enabled=False 환경으로 통과 (기본 동작)

참고:
    - app/main.py 는 모듈 로드 시점에 _settings = get_settings() 를 캐싱한다.
      따라서 monkeypatch 로 app.main._settings 를 직접 교체하는 방식 사용.
"""

from __future__ import annotations

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


# ===========================================================================
# /metrics — prometheus_enabled=True (기본값)
# ===========================================================================


class TestMetricsEnabled:
    """/metrics 엔드포인트가 prometheus_enabled=True 일 때 올바르게 동작한다."""

    def test_metrics_returns_200(self, monkeypatch):
        """prometheus_enabled=True 면 HTTP 200 응답."""
        # Arrange
        import app.main as main_mod

        class FakeSettings:
            prometheus_enabled = True
            rate_limit_enabled = False
            cors_allow_origins = ["http://localhost:5173"]

        monkeypatch.setattr(main_mod, "_settings", FakeSettings())
        # Act
        response = client.get("/metrics")
        # Assert
        assert response.status_code == 200

    def test_metrics_content_type_is_text_plain(self, monkeypatch):
        """prometheus_enabled=True 면 Content-Type 이 text/plain 계열."""
        import app.main as main_mod

        class FakeSettings:
            prometheus_enabled = True
            rate_limit_enabled = False
            cors_allow_origins = ["http://localhost:5173"]

        monkeypatch.setattr(main_mod, "_settings", FakeSettings())
        response = client.get("/metrics")
        assert "text/plain" in response.headers.get("content-type", "")

    def test_metrics_response_contains_prometheus_format(self, monkeypatch):
        """prometheus 포맷 (# HELP 또는 # TYPE) 이 응답에 포함된다."""
        import app.main as main_mod

        class FakeSettings:
            prometheus_enabled = True
            rate_limit_enabled = False
            cors_allow_origins = ["http://localhost:5173"]

        monkeypatch.setattr(main_mod, "_settings", FakeSettings())
        response = client.get("/metrics")
        body = response.text
        # prometheus exposition 포맷 — # HELP 또는 # TYPE 줄 포함
        assert "# HELP" in body or "# TYPE" in body

    def test_metrics_default_settings_returns_200(self):
        """기본 설정(prometheus_enabled=True) 에서 /metrics 는 200 반환."""
        # app.main 의 _settings 기본값은 prometheus_enabled=True
        response = client.get("/metrics")
        assert response.status_code == 200


# ===========================================================================
# /metrics — prometheus_enabled=False
# ===========================================================================


class TestMetricsDisabled:
    """/metrics 엔드포인트가 prometheus_enabled=False 일 때 404 반환."""

    def test_metrics_returns_404_when_disabled(self, monkeypatch):
        """prometheus_enabled=False 면 HTTP 404 응답."""
        import app.main as main_mod

        class FakeSettings:
            prometheus_enabled = False
            rate_limit_enabled = False
            cors_allow_origins = ["http://localhost:5173"]

        monkeypatch.setattr(main_mod, "_settings", FakeSettings())
        response = client.get("/metrics")
        assert response.status_code == 404

    def test_metrics_404_body_indicates_disabled(self, monkeypatch):
        """prometheus_enabled=False 의 404 응답 body 에 'disabled' 문구 포함."""
        import app.main as main_mod

        class FakeSettings:
            prometheus_enabled = False
            rate_limit_enabled = False
            cors_allow_origins = ["http://localhost:5173"]

        monkeypatch.setattr(main_mod, "_settings", FakeSettings())
        response = client.get("/metrics")
        assert "disabled" in response.text


# ===========================================================================
# /metrics — 기타 검증
# ===========================================================================


class TestMetricsMisc:
    """추가 검증 — endpoint 기본 동작."""

    def test_metrics_not_in_openapi_schema(self):
        """/metrics 는 OpenAPI schema 에서 제외된다 (include_in_schema=False)."""
        response = client.get("/openapi.json")
        schema = response.json()
        paths = schema.get("paths", {})
        assert "/metrics" not in paths

    def test_metrics_get_method_only(self):
        """POST 메서드는 허용되지 않는다."""
        response = client.post("/metrics")
        assert response.status_code == 405
