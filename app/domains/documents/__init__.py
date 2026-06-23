"""app.domains.documents

파일 경로: app/documents/__init__.py
목적: 보험사·상품·판매기간 버전·문서 메타데이터 도메인.
"""

from app.domains.documents.models import (
    AREA_CODES,
    DOC_TYPES,
    Document,
    Insurer,
    Product,
    ProductVersion,
)
from app.domains.documents.schemas import (
    DocumentRead,
    InsurerCreate,
    InsurerRead,
    ProductCreate,
    ProductRead,
    ProductVersionRead,
)

__all__ = [
    "AREA_CODES",
    "DOC_TYPES",
    "Document",
    "DocumentRead",
    "Insurer",
    "InsurerCreate",
    "InsurerRead",
    "Product",
    "ProductCreate",
    "ProductRead",
    "ProductVersion",
    "ProductVersionRead",
]
