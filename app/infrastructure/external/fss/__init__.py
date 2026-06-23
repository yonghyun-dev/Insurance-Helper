"""app.infrastructure.external.fss

금융감독원 공시실 — 보험상품 약관 PDF 메타 크롤링 (Sprint 10).

공식 전용 API 없음 → 각 보험사 공시실 HTML scraping.
복잡도 ↑ + 법적 risk (저작권·robots.txt) → Sprint 10 에서 본격 구현.

Sprint 9 현재: 인터페이스 골격만. Sprint 10 에서 어댑터별 (hanwha/samsung) 추가.
"""

from app.infrastructure.external.fss.service import (
    FssNotImplementedError,
    ProductMeta,
    get_product_meta,
)

__all__ = ["FssNotImplementedError", "ProductMeta", "get_product_meta"]
