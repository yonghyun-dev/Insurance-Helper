"""app.domains.documents.service

파일 경로: app/documents/service.py
목적: 보험사·상품·문서 메타데이터의 비즈니스 로직 진입점.

원칙(domain-architecture):
    - router/CLI/다른 도메인이 본 service 만 호출. crud/models 직접 접근 금지
    - read 헬퍼 (list_*, count_*, get_*) 와 write 헬퍼 (register_document) 를 모두 노출
      → ingestion 도메인이 documents.crud 를 우회 호출하지 않도록 함
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.documents import crud as _crud
from app.domains.documents.models import Document, Insurer, Product, ProductVersion
from app.domains.documents.schemas import InsurerRead, ProductRead, ProductVersionRead

# --- read helpers ---------------------------------------------------------

def list_insurers(session: Session) -> list[InsurerRead]:
    """등록된 모든 보험사를 반환한다."""
    rows = session.scalars(select(Insurer).order_by(Insurer.id)).all()
    return [InsurerRead.model_validate(row) for row in rows]


def list_products(
    session: Session,
    *,
    insurer_id: str | None = None,
    area: str | None = None,
) -> list[ProductRead]:
    """필터(보험사·영역) 조건으로 상품 목록을 반환한다."""
    stmt = select(Product)
    if insurer_id is not None:
        stmt = stmt.where(Product.insurer_id == insurer_id)
    if area is not None:
        stmt = stmt.where(Product.area == area)
    rows = session.scalars(stmt.order_by(Product.id)).all()
    return [ProductRead.model_validate(row) for row in rows]


def list_versions(session: Session, product_id: str) -> list[ProductVersionRead]:
    """특정 상품의 판매기간 버전 목록을 최신순으로 반환한다."""
    stmt = (
        select(ProductVersion)
        .where(ProductVersion.product_id == product_id)
        .order_by(ProductVersion.valid_from.desc())
    )
    rows = session.scalars(stmt).all()
    return [ProductVersionRead.model_validate(row) for row in rows]


def count_documents(session: Session) -> int:
    """등록 문서 총 개수."""
    return session.scalar(select(func.count()).select_from(Document)) or 0


# --- write helpers (ingestion 도메인이 호출) ------------------------------

def register_document(
    session: Session,
    *,
    insurer_id: str,
    insurer_name: str,
    area: str,
    product_id: str,
    product_name: str,
    valid_from: date,
    valid_to: date | None,
    version_label: str,
    doc_type: str,
    file_path: str,
    file_sha256: str,
    page_count: int,
    parser_version: str,
) -> tuple[int, int, bool]:
    """보험사·상품·버전·문서를 한 번에 upsert.

    ingestion 도메인이 documents.crud 를 우회 호출하지 않도록 service 가 캡슐화한다.

    Returns:
        (document_id, version_id, changed)
        - changed True 면 새로 만들었거나 해시·파서버전이 바뀐 케이스 (재처리 필요)
    """
    _crud.get_or_create_insurer(session, insurer_id, insurer_name)
    _crud.get_or_create_product(session, product_id, insurer_id, area, product_name)
    version = _crud.get_or_create_version(
        session, product_id, valid_from, valid_to, version_label
    )
    doc, changed = _crud.upsert_document(
        session=session,
        version_id=version.id,
        doc_type=doc_type,
        file_path=file_path,
        file_sha256=file_sha256,
        page_count=page_count,
        parser_version=parser_version,
    )
    return doc.id, version.id, changed


def find_document_id_by_sha(session: Session, file_sha256: str) -> int | None:
    """해시로 기존 문서 id 조회 (멱등성 사전 체크용)."""
    doc = _crud.find_document_by_sha(session, file_sha256)
    return doc.id if doc else None


def find_file_path_by_id(session: Session, document_id: int) -> str | None:
    """document_id 로 file_path 조회 (Sprint 5 — Citation hydrate 용)."""
    row = session.scalars(
        select(Document).where(Document.id == document_id)
    ).one_or_none()
    return row.file_path if row else None
