"""app.domains.documents.router

파일 경로: app/documents/router.py
목적: 보험사·상품·문서 메타데이터의 read-only HTTP 엔드포인트.

Sprint 3 부터:
    - GET /documents/insurers           — 등록된 모든 보험사 목록
    - GET /documents/products           — 상품 목록 (insurer, area 필터)

설계 원칙:
    - 본 router 는 read-only GET 만 노출. service.register_document 같은 write 헬퍼는
      ingestion 도메인 (CLI) 만 사용. UI 가 임의 INSERT 못 하게 분리.
    - DB 세션은 `app.infrastructure.core.database.get_db_session` Depends 로 주입 — 테스트에서
      `dependency_overrides` 로 in-memory 세션 교체 가능.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.domains.documents import service
from app.domains.documents.schemas import InsurerRead, ProductRead
from app.infrastructure.core.database import get_db_session

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/insurers", response_model=list[InsurerRead])
def list_insurers_endpoint(
    db: Session = Depends(get_db_session),  # noqa: B008
) -> list[InsurerRead]:
    """등록된 보험사 전체를 id 오름차순으로 반환한다."""
    return service.list_insurers(db)


@router.get("/products", response_model=list[ProductRead])
def list_products_endpoint(
    insurer: str | None = Query(
        default=None, description="보험사 id 필터 (예: 'hanwha')"
    ),
    area: str | None = Query(
        default=None, description="영역 필터 (auto / accident_disease / fire)"
    ),
    db: Session = Depends(get_db_session),  # noqa: B008
) -> list[ProductRead]:
    """상품 목록을 id 오름차순으로 반환한다.

    `insurer`, `area` 쿼리로 필터링 가능. 둘 다 미지정 시 전체.
    """
    return service.list_products(db, insurer_id=insurer, area=area)
