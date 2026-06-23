"""tests.llm.test_client

app/llm/client.py 단위 테스트 — Sprint 16 1a 추론 provider 중앙 팩토리.

검증 핵심:
    - provider=upstage: Upstage base_url + UPSTAGE_API_KEY + solar 모델 해석
    - provider=openai: SDK 기본 엔드포인트 + OPENAI_API_KEY + llm 모델
    - 키 누락 시 ConfigurationError (provider 별 키 env 명시)
    - **OpenAI 폴백 없음**: provider=upstage 인데 upstage 키만 비고 openai 키가 있어도
      절대 openai 로 넘어가지 않는다 (국내 모델 전용 정책의 핵심 회귀 가드)
"""

from __future__ import annotations

import app.infrastructure.core.config as _cfg
import app.infrastructure.llm.client as client_mod
import pytest
from app.infrastructure.core.exceptions import ConfigurationError


def _set_env(monkeypatch, **kw: str) -> None:
    """명시 인자로 Settings 를 구성하고 client_mod.get_settings 를 교체한다.

    `.env` 파일(실 UPSTAGE_API_KEY 등)의 간섭을 차단하기 위해 `_env_file=None` 으로
    구성한다 — 키 누락 분기를 결정적으로 검증하기 위함.
    """
    settings = _cfg.Settings(_env_file=None, **kw)
    monkeypatch.setattr(client_mod, "get_settings", lambda: settings)
    client_mod.clear_cache()


class TestGetChatModel:
    def test_upstage_resolves_solar_model(self, monkeypatch):
        _set_env(monkeypatch, llm_provider="upstage", upstage_api_key="up-key")
        assert client_mod.get_chat_model() == "solar-pro2"

    def test_upstage_respects_solar_model_override(self, monkeypatch):
        _set_env(
            monkeypatch,
            llm_provider="upstage",
            upstage_api_key="up-key",
            solar_model="solar-pro2-250101",
        )
        assert client_mod.get_chat_model() == "solar-pro2-250101"

    def test_openai_resolves_llm_model(self, monkeypatch):
        _set_env(
            monkeypatch,
            llm_provider="openai",
            openai_api_key="sk-key",
            llm_model="gpt-4o-mini",
        )
        assert client_mod.get_chat_model() == "gpt-4o-mini"


class TestGetChatClientUpstage:
    def test_builds_client_pointed_at_upstage(self, monkeypatch):
        _set_env(monkeypatch, llm_provider="upstage", upstage_api_key="up-key")
        client = client_mod.get_chat_client()
        assert "api.upstage.ai" in str(client.base_url)
        assert client.api_key == "up-key"

    def test_respects_base_url_override(self, monkeypatch):
        _set_env(
            monkeypatch,
            llm_provider="upstage",
            upstage_api_key="up-key",
            upstage_base_url="https://proxy.internal/v1",
        )
        client = client_mod.get_chat_client()
        assert "proxy.internal" in str(client.base_url)

    def test_missing_upstage_key_raises(self, monkeypatch):
        _set_env(monkeypatch, llm_provider="upstage", upstage_api_key="")
        with pytest.raises(ConfigurationError, match="UPSTAGE_API_KEY"):
            client_mod.get_chat_client()


class TestNoOpenAiFallback:
    """제품 정책 핵심 — provider=upstage 는 OpenAI 로 절대 폴백하지 않는다."""

    def test_upstage_key_missing_does_not_fall_back_to_openai(self, monkeypatch):
        # upstage 키는 비었지만 openai 키는 존재 → 폴백 유혹 상황.
        _set_env(
            monkeypatch,
            llm_provider="upstage",
            upstage_api_key="",
            openai_api_key="sk-should-not-be-used",
        )
        with pytest.raises(ConfigurationError, match="UPSTAGE_API_KEY"):
            client_mod.get_chat_client()


class TestGetChatClientOpenai:
    """provider=openai 는 오프라인 dev/eval 전용 탈출구 — 자동 선택되지 않음."""

    def test_builds_default_openai_client(self, monkeypatch):
        _set_env(monkeypatch, llm_provider="openai", openai_api_key="sk-key")
        client = client_mod.get_chat_client()
        assert "api.openai.com" in str(client.base_url)
        assert client.api_key == "sk-key"

    def test_missing_openai_key_raises(self, monkeypatch):
        _set_env(monkeypatch, llm_provider="openai", openai_api_key="")
        with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
            client_mod.get_chat_client()


class TestGetEmbeddingClient:
    """Sprint 16 1b — 임베딩 클라이언트 (Upstage 전용, 폴백 없음)."""

    def test_upstage_pointed_at_upstage(self, monkeypatch):
        _set_env(monkeypatch, embedding_provider="upstage", upstage_api_key="up-key")
        client = client_mod.get_embedding_client()
        assert "api.upstage.ai" in str(client.base_url)
        assert client.api_key == "up-key"

    def test_missing_key_no_openai_fallback(self, monkeypatch):
        _set_env(
            monkeypatch,
            embedding_provider="upstage",
            upstage_api_key="",
            openai_api_key="sk-should-not-be-used",
        )
        with pytest.raises(ConfigurationError, match="UPSTAGE_API_KEY"):
            client_mod.get_embedding_client()

    def test_openai_provider_default_endpoint(self, monkeypatch):
        _set_env(monkeypatch, embedding_provider="openai", openai_api_key="sk-key")
        client = client_mod.get_embedding_client()
        assert "api.openai.com" in str(client.base_url)
        assert client.api_key == "sk-key"
