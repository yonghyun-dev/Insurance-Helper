"""app.domains.documents.schemas

파일 경로: app/documents/schemas.py
목적: 보험사·상품·판매기간·문서 메타데이터의 입력/응답 pydantic 모델.

`models.py`(SQLAlchemy ORM) 와 분리하는 이유는 도메인 응집 원칙:
    - models = DB 테이블 구조 (내부)
    - schemas = 외부 노출 형태 (HTTP 응답, CLI 출력, JSON)
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class _OrmBase(BaseModel):
    """SQLAlchemy ORM 객체에서 직접 만들 수 있도록 from_attributes 활성화."""

    model_config = ConfigDict(from_attributes=True)


# --- 보험사 ---

class InsurerCreate(BaseModel):
    """보험사 등록 요청."""

    id: str = Field(..., min_length=1, max_length=64, description="lower_snake_case 코드")
    name: str = Field(..., min_length=1, max_length=120, description="보험사 한글명")
    homepage_url: str | None = Field(default=None, max_length=255)


class InsurerRead(_OrmBase):
    """보험사 응답."""

    id: str
    name: str
    homepage_url: str | None = None
    created_at: datetime


# --- 상품 ---

class ProductCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=120)
    insurer_id: str = Field(..., min_length=1, max_length=64)
    area: str = Field(..., description="auto / accident_disease / fire")
    name: str = Field(..., min_length=1, max_length=255)


class ProductRead(_OrmBase):
    id: str
    insurer_id: str
    area: str
    name: str
    created_at: datetime


# --- 판매기간 버전 ---

class ProductVersionRead(_OrmBase):
    id: int
    product_id: str
    valid_from: date
    valid_to: date | None = None
    version_label: str
    is_active: bool
    created_at: datetime


# --- 문서 ---

class DocumentRead(_OrmBase):
    id: int
    version_id: int
    doc_type: str = Field(..., description="summary / business / terms")
    file_path: str
    file_sha256: str
    page_count: int
    parser_version: str
    extracted_at: datetime
