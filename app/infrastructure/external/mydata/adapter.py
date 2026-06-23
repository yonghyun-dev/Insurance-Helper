"""app.infrastructure.external.mydata.adapter

MydataAdapter Protocol + DummyAdapter + RealAdapter.

설계 (tech-decisions § Sprint 14 결정 4):
    - 단일 메서드 `fetch_insurances(user_external_id) -> list[InsuranceDict]`
    - DummyAdapter: 파일 fixture 매핑
    - RealAdapter: skeleton (raise MydataNotConfiguredError) — 사업자 인증 발급 후 활성
    - env 토글 `MYDATA_BACKEND=dummy|real` (기본 dummy)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol, TypedDict

from app.infrastructure.core.config import get_settings
from app.infrastructure.core.exceptions import ConfigurationError
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)


class InsuranceDict(TypedDict):
    """마이데이터 가입 보험 1건."""

    insurer_id: str           # 폴더명 코드 (예: "hanwha")
    insurer_name: str         # 한국어 보험사명
    product_id: str           # 폴더명 코드 (예: "auto_personal")
    product_name: str         # 한국어 상품명
    policy_no: str            # 증권번호
    area: str                 # auto / fire / accident_disease
    valid_from: str           # ISO 날짜
    valid_to: str | None      # ISO 날짜 또는 null (무기한)


class MydataAdapter(Protocol):
    def fetch_insurances(self, user_external_id: str) -> list[InsuranceDict]:
        """가입 보험 목록 반환. 미존재 user 는 빈 리스트."""
        ...


class MydataNotConfiguredError(ConfigurationError):
    """실 마이데이터 API 미설정 (사업자 인증 대기)."""


# ---------------------------------------------------------------------------
# DummyAdapter — fixture 기반
# ---------------------------------------------------------------------------


_DEFAULT_FIXTURE = (
    # app/infrastructure/external/mydata/adapter.py → 5x parent = repo 루트
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "data"
    / "demo"
    / "mydata.json"
)


class DummyAdapter:
    """파일 fixture 기반 더미 어댑터. PoC / dev / 검증 대기 기간 용도."""

    def __init__(self, fixture_path: Path | None = None) -> None:
        self._fixture_path = fixture_path or _DEFAULT_FIXTURE
        self._data: dict[str, list[dict[str, Any]]] | None = None

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if self._data is None:
            if not self._fixture_path.exists():
                logger.warning("Mydata fixture 미존재: %s (빈 매핑 사용)", self._fixture_path)
                self._data = {}
            else:
                self._data = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        return self._data

    def fetch_insurances(self, user_external_id: str) -> list[InsuranceDict]:
        return [InsuranceDict(**rec) for rec in self._load().get(user_external_id, [])]


# ---------------------------------------------------------------------------
# RealAdapter — 사업자 인증 후 활성
# ---------------------------------------------------------------------------


class RealAdapter:
    """실 마이데이터 API 어댑터 skeleton. 사업자 인증 발급 후 구현."""

    def fetch_insurances(self, user_external_id: str) -> list[InsuranceDict]:  # noqa: ARG002
        raise MydataNotConfiguredError(
            "마이데이터 RealAdapter 비활성 — 사업자 인증 대기. MYDATA_BACKEND=dummy 사용."
        )


# ---------------------------------------------------------------------------
# 팩토리
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_mydata_adapter() -> MydataAdapter:
    """Settings.mydata_backend 기반 어댑터 선택."""
    settings = get_settings()
    if settings.mydata_backend == "real":
        return RealAdapter()
    return DummyAdapter()


def clear_cache() -> None:
    """테스트용 — 어댑터 싱글톤 캐시 초기화."""
    get_mydata_adapter.cache_clear()
