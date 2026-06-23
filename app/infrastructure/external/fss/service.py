"""app.infrastructure.external.fss.service

금융감독원 공시실 — 보험사·상품명 → 약관 메타 (PDF URL 등) 크롤링.

각 보험사 공시실 페이지 구조가 다름 → 어댑터 패턴 (Sprint 10).
법무 검토 필수: 약관규제법 + 저작권법 + robots.txt.

Sprint 9 현재: 인터페이스만. 호출 시 FssNotImplementedError.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class FssNotImplementedError(Exception):
    """Sprint 10 의 보험사별 어댑터 미구현. 법무 검토 + 어댑터 작성 후 활성."""


class ProductMeta(BaseModel):
    """보험상품 메타 (공시실에서 크롤링)."""

    model_config = ConfigDict(extra="forbid")

    insurer: str = Field(description="보험사명 (예: '한화손해보험')")
    product_name: str = Field(description="상품명")
    version: str = Field(description="약관 버전 (예: '2026-01-01')")
    terms_pdf_url: str = Field(description="약관 PDF 다운로드 URL")
    summary_pdf_url: str | None = Field(default=None)
    discovered_at: str = Field(description="크롤링 시점 ISO 8601")


def get_product_meta(insurer: str, product_name: str) -> ProductMeta | None:
    """Sprint 10 — 보험사별 어댑터 라우팅.

    현재 모든 호출 → FssNotImplementedError. Sprint 10 에서:
        1. _ADAPTERS[insurer_code] 라우팅
        2. 어댑터별 HTML scraping
        3. 결과 ProductMeta 로 정규화

    Args:
        insurer: 보험사명
        product_name: 상품명

    Raises:
        FssNotImplementedError: Sprint 10 활성 전
    """
    logger.info("fss.get_product_meta 호출 (Sprint 10 미구현): %s / %s", insurer, product_name)
    raise FssNotImplementedError(
        f"fss 어댑터는 Sprint 10 의 보험사별 크롤링 구현 후 활성 (현재 요청: {insurer} / {product_name})"
    )
