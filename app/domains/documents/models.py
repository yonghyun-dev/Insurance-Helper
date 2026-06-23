"""app.domains.documents.models

파일 경로: app/documents/models.py
목적: 보험사·상품·판매기간·문서 메타데이터의 SQLAlchemy 2.0 ORM 모델.
주요 객체:
    - Insurer: 보험사 (PK: lower_snake_case 코드)
    - Product: 상품 (보험사 × 영역 × 상품명)
    - ProductVersion: 판매기간 버전 (약관 개정 시점별)
    - Document: PDF 파일 1개 (상품요약/사업방법/약관)
주요 의존성: sqlalchemy

설계 참고:
    - docs/design/data-model.md `documents` 테이블 섹션
    - area 코드: auto / accident_disease / fire — 실데이터(주택화재) 반영해 fire 추가
    - doc_type CHECK: summary / business / terms
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.core.database import Base

if TYPE_CHECKING:
    from app.domains.chunks.models import ClauseChunk

# 도메인 enum 코드 (Python 측 enum 보다 단순 상수 — SQLite CHECK 제약과 호환)
AREA_CODES: tuple[str, ...] = ("auto", "accident_disease", "fire")
DOC_TYPES: tuple[str, ...] = ("summary", "business", "terms")


def _area_check_sql() -> str:
    """area CHECK 제약 SQL 문구를 enum 상수에서 생성."""
    quoted = ",".join(f"'{c}'" for c in AREA_CODES)
    return f"area IN ({quoted})"


def _doc_type_check_sql() -> str:
    """doc_type CHECK 제약 SQL 문구."""
    quoted = ",".join(f"'{c}'" for c in DOC_TYPES)
    return f"doc_type IN ({quoted})"


class Insurer(Base):
    """보험사 메타. 사용자가 임의로 선정한 1~2곳 단위."""

    __tablename__ = "insurers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    homepage_url: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    products: Mapped[list[Product]] = relationship(back_populates="insurer", cascade="all, delete-orphan")


class Product(Base):
    """상품. 보험사 × 영역 × 상품명."""

    __tablename__ = "products"
    __table_args__ = (CheckConstraint(_area_check_sql(), name="ck_products_area"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    insurer_id: Mapped[str] = mapped_column(ForeignKey("insurers.id"), nullable=False, index=True)
    area: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    insurer: Mapped[Insurer] = relationship(back_populates="products")
    versions: Mapped[list[ProductVersion]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductVersion(Base):
    """상품 판매기간 버전. 약관 개정 시점별로 다른 row 를 가진다."""

    __tablename__ = "product_versions"
    __table_args__ = (UniqueConstraint("product_id", "valid_from", name="uq_versions_product_valid_from"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    product: Mapped[Product] = relationship(back_populates="versions")
    documents: Mapped[list[Document]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class Document(Base):
    """원본 PDF 1개. 종류는 summary/business/terms."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(_doc_type_check_sql(), name="ck_documents_doc_type"),
        UniqueConstraint("version_id", "doc_type", name="uq_documents_version_doc_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("product_versions.id"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    version: Mapped[ProductVersion] = relationship(back_populates="documents")
    chunks: Mapped[list[ClauseChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
