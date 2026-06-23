"""app.domains.documents.crud

파일 경로: app/documents/crud.py
목적: 보험사·상품·판매기간 버전·문서 메타데이터의 CRUD 헬퍼.
주요 의존성: sqlalchemy
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.documents.models import (
    Document,
    Insurer,
    Product,
    ProductVersion,
)


def get_or_create_insurer(session: Session, insurer_id: str, name: str) -> Insurer:
    """보험사를 ID 로 찾거나 새로 생성."""
    found = session.get(Insurer, insurer_id)
    if found:
        return found
    insurer = Insurer(id=insurer_id, name=name)
    session.add(insurer)
    session.flush()
    return insurer


def get_or_create_product(
    session: Session,
    product_id: str,
    insurer_id: str,
    area: str,
    name: str,
) -> Product:
    """상품을 ID 로 찾거나 새로 생성."""
    found = session.get(Product, product_id)
    if found:
        return found
    product = Product(id=product_id, insurer_id=insurer_id, area=area, name=name)
    session.add(product)
    session.flush()
    return product


def get_or_create_version(
    session: Session,
    product_id: str,
    valid_from: date,
    valid_to: date | None,
    version_label: str,
) -> ProductVersion:
    """판매기간 버전을 (product_id, valid_from) 으로 찾거나 새로 생성."""
    stmt = select(ProductVersion).where(
        ProductVersion.product_id == product_id,
        ProductVersion.valid_from == valid_from,
    )
    found = session.scalar(stmt)
    if found:
        return found
    version = ProductVersion(
        product_id=product_id,
        valid_from=valid_from,
        valid_to=valid_to,
        version_label=version_label,
        is_active=True,
    )
    session.add(version)
    session.flush()
    return version


def find_document_by_sha(session: Session, file_sha256: str) -> Document | None:
    """파일 해시로 기존 Document 조회 (멱등 처리용)."""
    stmt = select(Document).where(Document.file_sha256 == file_sha256)
    return session.scalar(stmt)


def upsert_document(
    session: Session,
    version_id: int,
    doc_type: str,
    file_path: str,
    file_sha256: str,
    page_count: int,
    parser_version: str,
) -> tuple[Document, bool]:
    """문서를 (version_id, doc_type) 으로 찾고, 해시가 같으면 skip, 다르면 갱신.

    Returns:
        (Document, is_new_or_changed) — 새로 만들었거나 해시가 바뀌었으면 True.
    """
    stmt = select(Document).where(
        Document.version_id == version_id,
        Document.doc_type == doc_type,
    )
    found = session.scalar(stmt)
    if found is None:
        doc = Document(
            version_id=version_id,
            doc_type=doc_type,
            file_path=file_path,
            file_sha256=file_sha256,
            page_count=page_count,
            parser_version=parser_version,
        )
        session.add(doc)
        session.flush()
        return doc, True

    if found.file_sha256 == file_sha256 and found.parser_version == parser_version:
        return found, False  # 변경 없음 — 재처리 불필요

    # 변경됨 — 갱신
    found.file_path = file_path
    found.file_sha256 = file_sha256
    found.page_count = page_count
    found.parser_version = parser_version
    session.flush()
    return found, True
