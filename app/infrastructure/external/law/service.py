"""app.infrastructure.external.law.service

파일 경로: app/external/law/service.py
목적: 국가법령정보센터 OpenAPI lookup.

Endpoint: https://www.law.go.kr/DRF/lawService.do
인증: OC = 로그인 이메일 ID (운영자 신청 → 1~2일 승인)
응답: JSON (type=JSON 파라미터)
캐싱: TTL 30일 (법령 본문은 거의 안 바뀜)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pybreaker import CircuitBreakerError
from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.core.config import get_settings
from app.infrastructure.external._common import get_breaker, make_ttl_cache

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.law.go.kr/DRF/lawService.do"
_TIMEOUT_S = 5.0

# 30일 TTL — 법령 본문 거의 불변
_CACHE = make_ttl_cache(maxsize=10_000, ttl_seconds=30 * 24 * 60 * 60)


class LawNotConfiguredError(Exception):
    """LAW_GO_KR_OC env 미설정 — 운영자가 발급해야 활성."""


class LawClause(BaseModel):
    """법령 조항 단일 결과."""

    model_config = ConfigDict(extra="forbid")

    law_name: str = Field(description="법령명 (예: '보험업법')")
    article_no: str = Field(description="조항 번호 (예: '제4조')")
    sub_no: str | None = Field(default=None, description="항/호 (예: '①')")
    text: str = Field(description="조문 본문")
    source_url: str = Field(description="법령정보센터 URL")


def lookup_clause(law_name: str, keyword_or_article: str) -> LawClause | None:
    """법령 조항 검색.

    Args:
        law_name: 법령명 (예: '보험업법')
        keyword_or_article: 키워드 또는 조항 번호

    Returns:
        LawClause 또는 None (매칭 0건)

    Raises:
        LawNotConfiguredError: OC 미설정
    """
    settings = get_settings()
    oc = getattr(settings, "law_go_kr_oc", None) or ""
    if not oc:
        raise LawNotConfiguredError(
            "LAW_GO_KR_OC env 미설정. 운영자 회원가입 후 OC (이메일 ID) 신청 필요."
        )

    cache_key = f"{law_name}|{keyword_or_article}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    breaker = get_breaker("law")
    try:
        data = breaker.call(_fetch, oc, law_name, keyword_or_article)
    except CircuitBreakerError:
        logger.warning("law.go.kr circuit open — null 반환 (degraded)")
        return None
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("law.go.kr 호출 실패: %s", exc)
        return None

    result = _parse(data, law_name)
    _CACHE[cache_key] = result
    return result


def _fetch(oc: str, law_name: str, keyword: str) -> dict[str, Any]:
    """실 HTTP 호출. circuit breaker 가 감쌈."""
    with httpx.Client(timeout=_TIMEOUT_S) as client:
        response = client.get(
            _BASE_URL,
            params={"OC": oc, "target": "law", "LM": law_name, "JO": keyword, "type": "JSON"},
        )
        response.raise_for_status()
        return response.json()


def _parse(data: dict[str, Any], law_name: str) -> LawClause | None:
    """law.go.kr JSON 응답 → LawClause.

    실 응답 구조는 데이터 받아본 후 보정 필요. 현재는 일반적 패턴 가정.
    """
    try:
        articles = data.get("법령", {}).get("조문", {}).get("조문단위", [])
    except (AttributeError, KeyError):
        return None
    if not articles:
        return None
    first = articles[0] if isinstance(articles, list) else articles
    return LawClause(
        law_name=law_name,
        article_no=first.get("조문번호", "?"),
        sub_no=first.get("항번호"),
        text=first.get("조문내용", ""),
        source_url=f"https://www.law.go.kr/법령/{law_name}/{first.get('조문번호', '')}",
    )


def clear_cache() -> None:
    """테스트용 — TTL 캐시 비움."""
    _CACHE.clear()
