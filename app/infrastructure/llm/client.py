"""app.infrastructure.llm.client

파일 경로: app/llm/client.py
목적: 추론(Chat Completions / Function Calling / Structured Outputs) LLM 클라이언트의
      단일 생성 지점. provider별 base_url·키·모델명을 한 곳에서 결정한다.

설계 (Sprint 16 1a):
    - [하드 제약] 제품 추론은 국내 모델(Upstage Solar)만. provider=upstage 가 기본.
    - Upstage 는 OpenAI-SDK 호환(`api.upstage.ai/v1`)이라 `base_url` 교체로 흡수.
    - **OpenAI 폴백 없음**: 키 누락 시 즉시 ConfigurationError. provider=openai 는
      오프라인 dev/eval 전용이며 제품 경로에서 자동 선택되지 않는다.
    - 임베딩(1b)·OCR(1c)은 본 모듈 범위 밖 — 별도 클라이언트(잔존 OpenAI) 사용.

사용:
    from app.infrastructure.llm.client import get_chat_client, get_chat_model
    client = get_chat_client()
    client.chat.completions.create(model=get_chat_model(), ...)
"""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from app.infrastructure.core.config import get_settings
from app.infrastructure.core.exceptions import ConfigurationError
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_chat_client() -> OpenAI:
    """추론용 OpenAI-호환 클라이언트(캐시 싱글톤).

    provider=upstage 시 Upstage base_url + UPSTAGE_API_KEY 로 생성한다.
    키 누락 시 즉시 ConfigurationError — **OpenAI 로 폴백하지 않는다**.

    Raises:
        ConfigurationError: 선택된 provider 의 API 키가 비어 있는 경우.
    """
    settings = get_settings()
    api_key = settings.effective_llm_api_key
    if not api_key:
        raise ConfigurationError(
            "UPSTAGE_API_KEY 가 비어 있습니다. .env 또는 환경변수에 설정하세요. "
            "(제품 전 영역 국내 모델 전용 — OpenAI 미지원)"
        )

    # 견고성 — 타임아웃/재시도 명시(SDK 기본값 의존 제거). 루프 내 행/단발 실패 방어.
    timeout = settings.llm_timeout_s
    max_retries = settings.llm_max_retries
    base_url = settings.effective_llm_base_url
    logger.info(
        "추론 LLM 클라이언트 생성 — Upstage base_url=%s model=%s timeout=%ss retries=%d",
        base_url,
        settings.effective_llm_model,
        timeout,
        max_retries,
    )
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)


def get_chat_model() -> str:
    """선택된 provider 의 추론 모델명. upstage → solar_model, openai → llm_model."""
    return get_settings().effective_llm_model


@lru_cache(maxsize=1)
def get_embedding_client() -> OpenAI:
    """임베딩용 OpenAI-호환 클라이언트(캐시 싱글톤). Sprint 16 1b.

    embedding_provider=upstage 시 Upstage base_url + UPSTAGE_API_KEY 로 생성.
    키 누락 시 즉시 ConfigurationError — **OpenAI 로 폴백하지 않는다**.

    Raises:
        ConfigurationError: 선택된 임베딩 provider 의 API 키가 비어 있는 경우.
    """
    settings = get_settings()
    api_key = settings.effective_embedding_api_key
    if not api_key:
        raise ConfigurationError(
            "UPSTAGE_API_KEY 가 비어 있습니다. .env 또는 환경변수에 설정하세요. "
            "(제품 임베딩 국내 모델 전용 — OpenAI 미지원)"
        )
    return OpenAI(api_key=api_key, base_url=settings.effective_embedding_base_url)


def clear_cache() -> None:
    """테스트용 — 클라이언트 싱글톤 캐시 초기화."""
    get_chat_client.cache_clear()
    get_embedding_client.cache_clear()
