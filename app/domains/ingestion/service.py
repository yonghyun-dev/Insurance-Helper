"""app.domains.ingestion.service

파일 경로: app/ingestion/service.py
목적: PDF 폴더를 스캔해 메타·청크·임베딩을 적재하는 end-to-end 파이프라인.

처리 단위: 1개 PDF.
처리 흐름:
    1. 폴더 경로에서 보험사/영역/상품/버전/doc_type 메타 추출
    2. 파일 sha256 계산 → 멱등성 판정 (해시 동일 + 파서 동일 → skip)
    3. parser.parse_pdf → structure.recognize_structure → chunker.chunk_document
    4. SQLite 트랜잭션: get_or_create insurer/product/version, upsert document, 청크 INSERT
    5. embeddings.embed_texts → search.upsert_chunks (Chroma)
    6. 동기화: 재처리 시 chunks DELETE + Chroma delete_by_document 후 재삽입

설계 메모:
    - 폴더 규칙: data/raw/{insurer_code}/{area}/{product_code}/{version_label}/{doc_type}.pdf
    - doc_type 매핑: 파일명에 'terms'/'summary'/'business' 키워드 포함 또는 명시.
      매핑 모호 시 가장 큰 PDF 를 terms 로 폴백 (PoC 휴리스틱).
    - 트랜잭션: SQLite 커밋 후 Chroma 호출. Chroma 실패 시 SQLite 롤백 후 재시도.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from app.domains.chunks import service as chunks_service
from app.domains.documents import service as documents_service
from app.domains.documents.models import AREA_CODES  # 상수 import 는 도메인 경계 부담 없음
from app.domains.ingestion.schemas import IngestStats, PathInfo
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.database import session_scope
from app.infrastructure.core.exceptions import IngestionError
from app.infrastructure.core.logging import get_logger
from app.infrastructure.embeddings.service import embed_texts

logger = get_logger(__name__)

_DOC_TYPE_KEYWORDS = {
    "terms": "terms",
    "약관": "terms",
    "policy": "terms",
    "summary": "summary",
    "요약": "summary",
    "product": "summary",
    "business": "business",
    "사업방법": "business",
}


def scan_raw_folder(
    raw_root: Path | None = None,
    insurer: str | None = None,
    area: str | None = None,
) -> list[PathInfo]:
    """원본 폴더를 스캔해 적재 대상 PDF 메타를 수집한다.

    Args:
        raw_root: 스캔 루트 (기본 settings.raw_data_path).
        insurer: 보험사 코드 필터.
        area: 영역 코드 필터.

    Returns:
        PathInfo 리스트. doc_type 매핑 실패한 파일은 제외.
    """
    root = raw_root or get_settings().raw_data_path
    if not root.exists():
        return []

    items: list[PathInfo] = []
    for pdf_path in sorted(root.rglob("*.pdf")):
        try:
            info = parse_pdf_path(pdf_path, raw_root=root)
        except IngestionError as exc:
            logger.warning("경로 파싱 실패, 스킵: %s (%s)", pdf_path, exc)
            continue
        if insurer and info.insurer_id != insurer:
            continue
        if area and info.area != area:
            continue
        items.append(info)
    return items


def parse_pdf_path(pdf_path: Path, raw_root: Path) -> PathInfo:
    """`data/raw/<insurer>/<area>/<product>/<version>/<file>.pdf` 경로를 메타로 분해."""
    rel = pdf_path.relative_to(raw_root)
    parts = rel.parts
    if len(parts) < 5:
        raise IngestionError(
            f"폴더 구조가 5단계({{insurer}}/{{area}}/{{product}}/{{version}}/file.pdf) 가 아닙니다: {rel}"
        )
    insurer_id, area, product_id, version_label, filename = parts[0], parts[1], parts[2], parts[3], parts[-1]
    if area not in AREA_CODES:
        raise IngestionError(f"영역 코드 '{area}' 가 허용 목록 {AREA_CODES} 에 없습니다: {rel}")

    valid_from, valid_to = _parse_version_label(version_label)
    doc_type = _infer_doc_type(filename)
    if doc_type is None:
        raise IngestionError(f"파일명에서 doc_type 을 추론할 수 없습니다: {filename}")

    return PathInfo(
        insurer_id=insurer_id,
        insurer_name=insurer_id,  # 한글명은 추후 별도 매핑 — PoC 우선 코드명
        area=area,
        product_id=product_id,
        product_name=product_id,  # 동일
        version_label=version_label,
        valid_from=valid_from,
        valid_to=valid_to,
        doc_type=doc_type,
        file_path=pdf_path,
    )


def _parse_version_label(label: str) -> tuple[date, date | None]:
    """버전 라벨에서 (valid_from, valid_to) 파싱.

    허용 형식:
        - "2026-03-01_present"
        - "2026-03-01_2026-12-31"
        - "20260301"          → 2026-03-01, None
    인식 실패 시 1900-01-01, None.
    """
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})_(present|\d{4}-\d{2}-\d{2})$", label)
    if m:
        y, mo, d, end = m.groups()
        start = date(int(y), int(mo), int(d))
        if end == "present":
            return start, None
        ey, em, ed = end.split("-")
        return start, date(int(ey), int(em), int(ed))

    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", label)
    if m:
        y, mo, d = m.groups()
        return date(int(y), int(mo), int(d)), None

    logger.warning("버전 라벨 파싱 실패, 1900-01-01 폴백: %s", label)
    return date(1900, 1, 1), None


def _infer_doc_type(filename: str) -> str | None:
    """파일명 키워드로 doc_type 추론."""
    lower = filename.lower()
    for keyword, dtype in _DOC_TYPE_KEYWORDS.items():
        if keyword in lower:
            return dtype
    return None


def _sha256_of(path: Path) -> str:
    """파일 sha256 해시 (멱등 처리 키)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def run_ingest(
    items: Iterable[PathInfo],
    *,
    dry_run: bool = False,
    force: bool = False,
) -> IngestStats:
    """수집된 PathInfo 들에 대해 적재를 실행한다.

    Args:
        items: scan_raw_folder 결과.
        dry_run: True 면 실제 처리 없이 대상만 출력.
        force: 해시 동일해도 재처리.

    Returns:
        IngestStats(processed, skipped, failed).
    """
    processed = 0
    skipped = 0
    failed = 0

    for info in items:
        logger.info(
            "[ingest] %s / %s / %s / %s / %s",
            info.insurer_id, info.area, info.product_id, info.version_label, info.doc_type,
        )
        if dry_run:
            processed += 1
            continue
        try:
            changed = _ingest_one(info, force=force)
            if changed:
                processed += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.exception("적재 실패: %s (%s)", info.file_path, exc)
            failed += 1

    return IngestStats(processed=processed, skipped=skipped, failed=failed)


def _ingest_one(info: PathInfo, *, force: bool) -> bool:
    """1개 PDF 적재. 변경/신규는 True, 변경 없음(skip)은 False 반환.

    다른 도메인은 service 레벨에서만 import 한다는 도메인 응집 원칙을 지켜,
    documents.crud / chunks.crud 직접 호출 없이 두 도메인의 service 만 사용한다.
    """
    sha = _sha256_of(info.file_path)

    # 멱등성 사전 체크 (force=False 일 때만)
    if not force:
        with session_scope() as session:
            existing_id = documents_service.find_document_id_by_sha(session, sha)
            if existing_id is not None:
                logger.info("해시 동일, 스킵: %s", info.file_path.name)
                return False

    # 1) 파싱·구조 인식·청킹 — 트랜잭션 외부 (느린 작업)
    processed = chunks_service.process_pdf(info.file_path)
    chunks = processed.chunks

    # 2) SQLite 트랜잭션: 메타 + 청크
    with session_scope() as session:
        document_id, version_id, changed = documents_service.register_document(
            session=session,
            insurer_id=info.insurer_id,
            insurer_name=info.insurer_name,
            area=info.area,
            product_id=info.product_id,
            product_name=info.product_name,
            valid_from=info.valid_from,
            valid_to=info.valid_to,
            version_label=info.version_label,
            doc_type=info.doc_type,
            file_path=str(info.file_path),
            file_sha256=sha,
            page_count=processed.page_count,
            parser_version=processed.parser_version,
        )

        if not changed and not force:
            logger.info("DB 변경 없음, 스킵: %s", info.file_path.name)
            return False

        # document_id + 문서 메타를 chunks 에 채우고, 청크 교체 (delete + insert)
        # (Sprint 32 T3 — 메타 비정규 부착: 검색 필터가 JOIN 없이 백엔드 무관 동작)
        for c in chunks:
            c.document_id = document_id
            c.insurer_id = info.insurer_id
            c.product_id = info.product_id
            c.area = info.area
            c.doc_type = info.doc_type
        deleted, inserted = chunks_service.replace_chunks_for_document(
            session, document_id, chunks
        )
        if deleted:
            logger.info("기존 청크 교체: 삭제 %d → INSERT %d", deleted, inserted)

    # 3) 벡터 backend 동기화 (SQLite 커밋 후) — Sprint 12: 어댑터 위임
    from app.domains.rag.vectorstore import get_vector_store

    vector_store = get_vector_store()
    try:
        vector_store.delete_by_document(document_id)
    except Exception as exc:
        logger.warning("벡터 backend 기존 삭제 실패(무시): %s", exc)

    embeddings = embed_texts([c.text for c in chunks])
    doc_meta = {
        "document_id": document_id,
        "insurer_id": info.insurer_id,
        "insurer_name": info.insurer_name,
        "product_id": info.product_id,
        "product_name": info.product_name,
        "area": info.area,
        "version_id": version_id,
        "version_label": info.version_label,
        "doc_type": info.doc_type,
    }
    vector_store.upsert(chunks, embeddings, doc_meta)

    # Sprint 32 T2 — 그래프(심볼릭 채널) 동기화. 실패는 경고만(검색은 뉴럴 단독 graceful)
    # 하되, ica verify 의 그래프 카운트 검증이 불일치를 드러낸다.
    try:
        from app.domains.rag.indexer import sync_document

        sync_document(document_id)
    except Exception as exc:  # noqa: BLE001 — 그래프 다운 시 인제스트 자체는 성공
        logger.warning("그래프 동기화 실패 (document_id=%s): %s — 'ica graph-build' 로 복구", document_id, exc)
    return True
