"""tests.external.test_ocr_adapter

app/external/ocr/adapter.py 단위 테스트 (Upstage 전용 — OpenAI 제거됨).

테스트 대상:
    - UpstageAdapter.extract_text — Document OCR API mock 호출
    - UpstageAdapter.parse_document — Document Parse 응답 매핑
    - get_ocr_adapter 팩토리 — 항상 UpstageAdapter
"""

from __future__ import annotations

import pytest
from app.infrastructure.core.exceptions import ConfigurationError, LLMError
from app.infrastructure.external.ocr.adapter import (
    OcrNotConfiguredError,
    UpstageAdapter,
    clear_cache,
    get_ocr_adapter,
)


def _make_fake_httpx_client(payload: dict, *, raise_exc: Exception | None = None):
    """Upstage OCR HTTP mock — post() → raise_for_status()/json()."""

    class _Resp:
        def raise_for_status(self):
            if raise_exc is not None:
                raise raise_exc

        def json(self):
            return payload

    class _Client:
        def __init__(self):
            self.calls: list[dict] = []

        def post(self, url, headers=None, data=None, files=None):
            self.calls.append({"url": url, "headers": headers, "data": data, "files": files})
            return _Resp()

    return _Client()


class TestUpstageAdapter:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.setenv("UPSTAGE_API_KEY", "")
        from app.infrastructure.core.config import get_settings

        get_settings.cache_clear()
        adapter = UpstageAdapter()  # client 미주입 → 키 체크에서 raise (네트워크 호출 전)
        with pytest.raises(OcrNotConfiguredError, match="UPSTAGE_API_KEY"):
            adapter.extract_text(b"x", "image/png")

    def test_extracts_text_and_confidence(self, monkeypatch):
        monkeypatch.setenv("UPSTAGE_API_KEY", "test-key")
        from app.infrastructure.core.config import get_settings

        get_settings.cache_clear()
        fake = _make_fake_httpx_client(
            {
                "text": "진단명: 급성 충수염\n환자: 홍길동",
                "confidence": 0.97,
                "numBilledPages": 1,
                "pages": [{"id": 0, "confidence": 0.97}],
            }
        )
        adapter = UpstageAdapter(client=fake)
        result = adapter.extract_text(b"fake-jpg", "image/jpeg")
        assert "급성 충수염" in result["text"]
        assert result["confidence"] == 0.97
        assert result["page_count"] == 1
        # 요청 검증: 엔드포인트 + model=ocr + Bearer + mime 전달
        call = fake.calls[0]
        assert call["url"].endswith("/document-digitization")
        assert call["data"] == {"model": "ocr"}
        assert call["headers"]["Authorization"] == "Bearer test-key"
        assert call["files"]["document"][2] == "image/jpeg"

    def test_page_count_falls_back_to_pages_length(self, monkeypatch):
        monkeypatch.setenv("UPSTAGE_API_KEY", "test-key")
        from app.infrastructure.core.config import get_settings

        get_settings.cache_clear()
        fake = _make_fake_httpx_client(
            {"text": "multi", "confidence": 0.9, "pages": [{"id": 0}, {"id": 1}]}
        )
        adapter = UpstageAdapter(client=fake)
        result = adapter.extract_text(b"x", "application/pdf")
        assert result["page_count"] == 2
        # pdf 도 전달됨 (mime 게이트 없음 — Upstage 가 처리)
        assert fake.calls[0]["files"]["document"][0].endswith(".pdf")

    def test_http_error_wrapped_as_llm_error(self, monkeypatch):
        monkeypatch.setenv("UPSTAGE_API_KEY", "test-key")
        from app.infrastructure.core.config import get_settings

        get_settings.cache_clear()
        fake = _make_fake_httpx_client({}, raise_exc=RuntimeError("502 Bad Gateway"))
        adapter = UpstageAdapter(client=fake)
        with pytest.raises(LLMError, match="Upstage OCR 호출 실패"):
            adapter.extract_text(b"x", "image/png")


class TestGetOcrAdapterFactory:
    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    def test_returns_upstage_always(self):
        adapter = get_ocr_adapter()
        assert isinstance(adapter, UpstageAdapter)

    def test_factory_cached(self):
        a1 = get_ocr_adapter()
        a2 = get_ocr_adapter()
        assert a1 is a2


class TestOcrNotConfiguredErrorInheritsConfigurationError:
    def test_is_configuration_error(self):
        assert issubclass(OcrNotConfiguredError, ConfigurationError)


class TestUpstageParseDocument:
    """UpstageAdapter.parse_document — document-parse 응답 매핑 (Sprint 25)."""

    def _client(self, payload):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        class _Client:
            def post(self, *a, **kw):  # timeout kwarg 포함 허용
                return _Resp()

        return _Client()

    def test_maps_elements_and_page_count(self, monkeypatch):
        monkeypatch.setenv("UPSTAGE_API_KEY", "test-key")
        from app.infrastructure.core.config import get_settings

        get_settings.cache_clear()
        payload = {
            "elements": [
                {"category": "heading1", "page": 1, "content": {"text": "제1조", "html": "<h1>제1조</h1>"}},
                {"category": "table", "page": 2, "content": {"text": "", "html": "<table><tr><td>a</td></tr></table>"}},
            ],
            "usage": {"pages": 2},
        }
        adapter = UpstageAdapter(client=self._client(payload))
        parsed = adapter.parse_document(b"%PDF-1.4", "application/pdf")

        assert parsed["page_count"] == 2
        assert len(parsed["elements"]) == 2
        assert parsed["elements"][0]["category"] == "heading1"
        assert parsed["elements"][0]["text"] == "제1조"
        assert parsed["elements"][1]["category"] == "table"
        assert "<table>" in parsed["elements"][1]["html"]

    def test_page_count_falls_back_to_max_page(self, monkeypatch):
        monkeypatch.setenv("UPSTAGE_API_KEY", "test-key")
        from app.infrastructure.core.config import get_settings

        get_settings.cache_clear()
        payload = {
            "elements": [{"category": "paragraph", "page": 3, "content": {"text": "x", "html": ""}}],
        }
        adapter = UpstageAdapter(client=self._client(payload))
        parsed = adapter.parse_document(b"%PDF", "application/pdf")
        assert parsed["page_count"] == 3

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.setenv("UPSTAGE_API_KEY", "")
        from app.infrastructure.core.config import get_settings

        get_settings.cache_clear()
        with pytest.raises(OcrNotConfiguredError, match="UPSTAGE_API_KEY"):
            UpstageAdapter().parse_document(b"x", "application/pdf")
