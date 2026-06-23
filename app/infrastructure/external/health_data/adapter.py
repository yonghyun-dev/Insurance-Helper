"""app.infrastructure.external.health_data.adapter

HealthDataAdapter Protocol + DummyAdapter + RealAdapter skeleton.

설계 (REQ-14 § 어댑터 분리 + PM-22 결정 1):
    - 단일 메서드 `fetch_treatments(user_external_id) -> TreatmentDict 리스트`
    - DummyAdapter: 파일 fixture 매핑 (사업자 인증 대기 동안 사용)
    - RealAdapter: skeleton (raise HealthDataNotConfiguredError) — 사업자 인증 발급 후 활성
    - env 토글 `HEALTH_DATA_BACKEND=dummy|real` (기본 dummy)

응답 스키마 (REQ-14 § 응답 스키마):
    - treatment_id / treatment_date / treatment_period
    - hospital_name / hospital_code / department
    - diagnosis_codes (KCD-7) / diagnosis_names (한국어)
    - is_hospitalization / hospitalization_days / outpatient_visits
    - total_cost / patient_paid (= claim_amount 매핑 대상)
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


class TreatmentDict(TypedDict):
    """진료내역 1건 (REQ-14 § 응답 스키마)."""

    treatment_id: str
    treatment_date: str           # YYYY-MM-DD
    treatment_period: str         # "YYYY-MM-DD ~ YYYY-MM-DD"
    hospital_name: str
    hospital_code: str
    department: str               # 진료과 (예: 정형외과)
    diagnosis_codes: list[str]    # KCD-7 코드 (예: ["S82.5"])
    diagnosis_names: list[str]    # 한국어 진단명 (예: ["발목 골절"])
    is_hospitalization: bool
    hospitalization_days: int
    outpatient_visits: int
    total_cost: int               # 의료기관 청구 총액 (원)
    patient_paid: int             # 환자 본인부담분 = claim_amount 매핑 대상


class HealthDataAdapter(Protocol):
    def fetch_treatments(self, user_external_id: str) -> list[TreatmentDict]:
        """진료내역 리스트 반환. 미존재 user 는 빈 리스트."""
        ...


class HealthDataNotConfiguredError(ConfigurationError):
    """실 건강보험 API 미설정 (사업자 인증 대기)."""


# ---------------------------------------------------------------------------
# DummyAdapter — fixture 기반
# ---------------------------------------------------------------------------


_DEFAULT_FIXTURE = (
    # app/infrastructure/external/health_data/adapter.py → 5x parent = repo 루트
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "health_data"
    / "users.json"
)


class DummyAdapter:
    """파일 fixture 기반 더미 어댑터. PoC / dev / 검증 대기 기간 용도."""

    def __init__(self, fixture_path: Path | None = None) -> None:
        self._fixture_path = fixture_path or _DEFAULT_FIXTURE
        self._data: dict[str, dict[str, Any]] | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._data is None:
            if not self._fixture_path.exists():
                logger.warning(
                    "HealthData fixture 미존재: %s (빈 매핑 사용)", self._fixture_path
                )
                self._data = {}
            else:
                self._data = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        return self._data

    def fetch_treatments(self, user_external_id: str) -> list[TreatmentDict]:
        user_rec = self._load().get(user_external_id)
        if not user_rec:
            return []
        return [TreatmentDict(**t) for t in user_rec.get("treatments", [])]


# ---------------------------------------------------------------------------
# RealAdapter — Sprint 18+ 실 API 발급 후 활성
# ---------------------------------------------------------------------------


class RealAdapter:
    """실 NHIS/HIRA/의료마이데이터 API 어댑터 skeleton.

    활성 조건:
        - HEALTH_DATA_BACKEND=real
        - 사업자 인증 완료 + API key 발급
        - 응답 스키마가 DummyAdapter 와 다르면 normalizer 추가
    """

    def fetch_treatments(self, user_external_id: str) -> list[TreatmentDict]:  # noqa: ARG002
        raise HealthDataNotConfiguredError(
            "실 건강보험 API 미설정 — HEALTH_DATA_BACKEND=dummy 사용 또는 "
            "사업자 인증 완료 후 RealAdapter 활성화."
        )


# ---------------------------------------------------------------------------
# 팩토리
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_health_data_adapter() -> HealthDataAdapter:
    """Settings.health_data_backend 기반 어댑터 선택."""
    settings = get_settings()
    if settings.health_data_backend == "real":
        return RealAdapter()
    return DummyAdapter()


def clear_cache() -> None:
    """테스트용 — 어댑터 싱글톤 캐시 초기화."""
    get_health_data_adapter.cache_clear()
