"""app.infrastructure.external.health_data.router

GET /api/v1/me/health/history — 로그인 사용자의 진료 내역 조회 + 슬롯 사전 매핑.

설계 (PM-22 결정 3):
    - 새 router 신설 (auth router 와 분리, 의료 데이터 도메인 응집)
    - prefix `/me/health`, 비로그인 401
    - 응답: 진료 카드 N개 (UI 노출용 + slot_mapping 사전 계산)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.domains.auth.deps import get_current_user_optional
from app.domains.users.models import User
from app.infrastructure.core.logging import get_logger
from app.infrastructure.external.health_data.adapter import (
    HealthDataNotConfiguredError,
    get_health_data_adapter,
)
from app.infrastructure.external.health_data.mapper import treatment_to_card

logger = get_logger(__name__)

router = APIRouter(prefix="/me/health", tags=["health_data"])


@router.get("/history", response_model=dict[str, Any])
def get_health_history(
    current_user: User | None = Depends(get_current_user_optional),  # noqa: B008
) -> dict[str, Any]:
    """로그인 사용자의 최근 진료 내역 + 슬롯 사전 매핑.

    응답:
        { "treatments": [TreatmentCard, ...] }

    Raises:
        401: 비로그인
        503: 실 API 미설정 (HEALTH_DATA_BACKEND=real 인데 사업자 인증 미완료)
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "로그인이 필요합니다."},
        )

    adapter = get_health_data_adapter()
    try:
        treatments = adapter.fetch_treatments(str(current_user.id))
    except HealthDataNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "HEALTH_DATA_NOT_CONFIGURED", "message": str(exc)},
        ) from exc

    cards = [treatment_to_card(t) for t in treatments]
    logger.info(
        "health history fetched: user=%s treatments=%d", current_user.id, len(cards)
    )
    return {"treatments": cards}
