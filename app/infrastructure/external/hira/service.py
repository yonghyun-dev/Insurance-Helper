"""app.infrastructure.external.hira.service

HIRA 진단명 → KCD-8 코드 변환 어댑터.

Endpoint: 공공데이터포털 건강보험심사평가원_질병정보서비스
캐싱: TTL 7일 (분기별 갱신)

Sprint 9 — serviceKey 발급 대기. 실 호출 비활성, 단위 테스트 mock 가능.
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

_BASE_URL = "http://apis.data.go.kr/B551182/diseaseInfoService"
_TIMEOUT_S = 5.0
_CACHE = make_ttl_cache(maxsize=5_000, ttl_seconds=7 * 24 * 60 * 60)


class HiraNotConfiguredError(Exception):
    """DATA_GO_KR_SERVICE_KEY env 미설정."""


class DiseaseCode(BaseModel):
    """KCD-8 진단코드 단일 결과."""

    model_config = ConfigDict(extra="forbid")

    kcd_code: str = Field(description="KCD-8 코드 (예: 'S82.6')")
    official_name: str = Field(description="공식 한국어 진단명")
    category: str | None = Field(default=None, description="대분류 (선택)")


def lookup_by_name(diagnosis_korean: str) -> DiseaseCode | None:
    """진단명 → KCD 코드 변환."""
    settings = get_settings()
    key = getattr(settings, "data_go_kr_service_key", None) or ""
    if not key:
        raise HiraNotConfiguredError(
            "DATA_GO_KR_SERVICE_KEY env 미설정. 공공데이터포털 회원가입 + 활용신청 필요."
        )

    if diagnosis_korean in _CACHE:
        return _CACHE[diagnosis_korean]

    breaker = get_breaker("hira")
    try:
        data = breaker.call(_fetch, key, diagnosis_korean)
    except CircuitBreakerError:
        logger.warning("hira circuit open — null 반환 (degraded)")
        return None
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("hira 호출 실패: %s", exc)
        return None

    result = _parse(data)
    _CACHE[diagnosis_korean] = result
    return result


def _fetch(service_key: str, query: str) -> dict[str, Any]:
    """실 HTTP 호출 (circuit breaker 가 감쌈). 실 응답 구조는 받아본 후 보정."""
    with httpx.Client(timeout=_TIMEOUT_S) as client:
        response = client.get(
            f"{_BASE_URL}/getDiseaseInfo",
            params={"serviceKey": service_key, "searchKeyword": query, "_type": "json"},
        )
        response.raise_for_status()
        return response.json()


def _parse(data: dict[str, Any]) -> DiseaseCode | None:
    """공공데이터포털 응답 → DiseaseCode. 실 데이터 받은 후 보정."""
    try:
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
    except (AttributeError, KeyError):
        return None
    if not items:
        return None
    first = items[0] if isinstance(items, list) else items
    return DiseaseCode(
        kcd_code=first.get("sickCd", "?"),
        official_name=first.get("sickNm", ""),
        category=first.get("category"),
    )


def clear_cache() -> None:
    """테스트용."""
    _CACHE.clear()
