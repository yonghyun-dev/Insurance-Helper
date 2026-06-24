"""tests.core.test_config

app/core/config.py 단위 테스트.

테스트 대상:
    - Settings.log_level: 소문자 입력 → 대문자 정규화
    - Settings.log_level: 잘못된 값 → ValidationError
    - Settings 기본값 확인
    - get_settings 캐시 동작 (monkeypatch 기반)
"""

from __future__ import annotations

import pytest
from app.infrastructure.core.config import Settings
from pydantic import ValidationError

# ===========================================================================
# log_level 정규화
# ===========================================================================


class TestLogLevelNormalization:
    """log_level 대소문자 정규화 검증."""

    def test_lowercase_debug_normalized_to_uppercase(self):
        # "debug" → "DEBUG"
        s = Settings(log_level="debug")  # type: ignore
        assert s.log_level == "DEBUG"

    def test_lowercase_info_normalized(self):
        s = Settings(log_level="info")  # type: ignore
        assert s.log_level == "INFO"

    def test_lowercase_warning_normalized(self):
        s = Settings(log_level="warning")  # type: ignore
        assert s.log_level == "WARNING"

    def test_lowercase_error_normalized(self):
        s = Settings(log_level="error")  # type: ignore
        assert s.log_level == "ERROR"

    def test_lowercase_critical_normalized(self):
        s = Settings(log_level="critical")  # type: ignore
        assert s.log_level == "CRITICAL"

    def test_mixed_case_normalized(self):
        # "Warning" → "WARNING"
        s = Settings(log_level="Warning")  # type: ignore
        assert s.log_level == "WARNING"

    def test_already_uppercase_accepted(self):
        s = Settings(log_level="INFO")
        assert s.log_level == "INFO"


# ===========================================================================
# log_level 유효성 검증
# ===========================================================================


class TestLogLevelValidation:
    """잘못된 log_level 값 → ValidationError 검증."""

    def test_invalid_log_level_raises_validation_error(self):
        # 알 수 없는 레벨 → ValidationError
        with pytest.raises(ValidationError):
            Settings(log_level="VERBOSE")  # type: ignore

    def test_empty_log_level_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Settings(log_level="")  # type: ignore

    def test_numeric_string_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Settings(log_level="5")  # type: ignore


# ===========================================================================
# Settings 기본값
# ===========================================================================


class TestSettingsDefaults:
    """Settings 기본값 확인."""

    def test_default_log_level_is_info(self):
        s = Settings()
        assert s.log_level == "INFO"

    def test_default_session_ttl(self):
        s = Settings()
        assert s.session_ttl_seconds == 1800

    def test_session_ttl_minimum_boundary(self):
        # 최소값 60 허용
        s = Settings(session_ttl_seconds=60)
        assert s.session_ttl_seconds == 60

    def test_session_ttl_below_minimum_raises_error(self):
        # 60 미만 → ValidationError
        with pytest.raises(ValidationError):
            Settings(session_ttl_seconds=59)


# ===========================================================================
# Sprint 16 1a — 추론 provider (Upstage Solar) 필드
# ===========================================================================


class TestLlmProvider:
    """llm_provider + effective_llm_* computed 필드 검증 (명시 인자로 .env 무관 결정)."""

    def test_default_provider_is_upstage(self):
        # [하드 제약] 제품 추론 기본 = 국내 모델(Upstage). 코드 기본값 검증(.env 무관).
        s = Settings(_env_file=None)
        assert s.llm_provider == "upstage"

    def test_default_solar_model(self):
        s = Settings(_env_file=None)
        assert s.solar_model == "solar-pro2"

    def test_upstage_effective_fields(self):
        s = Settings(
            llm_provider="upstage",
            upstage_api_key="up-key",
            upstage_base_url="https://api.upstage.ai/v1",
            solar_model="solar-pro2",
        )
        assert s.effective_llm_api_key == "up-key"
        assert s.effective_llm_base_url == "https://api.upstage.ai/v1"
        assert s.effective_llm_model == "solar-pro2"

    def test_invalid_provider_raises(self):
        # 국내 전용 — openai 포함 모든 비-upstage 값은 거부.
        with pytest.raises(ValidationError):
            Settings(llm_provider="openai")


class TestEmbeddingProvider:
    """Sprint 16 1b — 임베딩 provider + effective_embedding_* + 차원."""

    def test_default_provider_is_upstage(self):
        s = Settings(_env_file=None)
        assert s.embedding_provider == "upstage"

    def test_default_dim_is_4096(self):
        s = Settings(_env_file=None)
        assert s.embedding_dim == 4096

    def test_default_query_passage_models(self):
        s = Settings(_env_file=None)
        assert s.upstage_embedding_query_model == "embedding-query"
        assert s.upstage_embedding_passage_model == "embedding-passage"

    def test_upstage_effective_fields(self):
        s = Settings(embedding_provider="upstage", upstage_api_key="up-key")
        assert s.effective_embedding_api_key == "up-key"
        assert s.effective_embedding_base_url == "https://api.upstage.ai/v1"


# ===========================================================================
# get_settings 캐시
# ===========================================================================


class TestGetSettingsCache:
    """get_settings lru_cache 동작 검증."""

    def test_get_settings_returns_settings_instance(self, tmp_settings):
        # tmp_settings 픽스처가 캐시를 초기화하므로 새 Settings 반환
        from app.infrastructure.core.config import get_settings

        s = get_settings()
        assert isinstance(s, Settings)

    def test_get_settings_returns_same_instance(self, tmp_settings):
        # 캐시 덕분에 같은 인스턴스 반환
        from app.infrastructure.core.config import get_settings

        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
