"""app.infrastructure.external._common

외부 API 어댑터 공통 유틸 — circuit breaker + cache 헬퍼.

설계 참고: docs/design/external-apis.md § 5 공통 정책
"""

from __future__ import annotations

import logging
from functools import lru_cache

from cachetools import TTLCache
from pybreaker import CircuitBreaker

from app.infrastructure.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def get_breaker(name: str) -> CircuitBreaker:
    """외부 API 별 circuit breaker. 같은 name 은 같은 인스턴스 (싱글톤).

    이름 규칙: "law", "hira", "kidi", "fss"
    """
    s = get_settings()
    return CircuitBreaker(
        fail_max=s.circuit_breaker_fail_max,
        reset_timeout=s.circuit_breaker_reset_seconds,
        name=f"external_{name}",
    )


def make_ttl_cache(maxsize: int, ttl_seconds: int) -> TTLCache:
    """TTLCache 생성 헬퍼. 어댑터마다 호출."""
    return TTLCache(maxsize=maxsize, ttl=ttl_seconds)
