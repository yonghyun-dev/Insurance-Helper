"""app.infrastructure.pdfimage.service

파일 경로: app/pdfimage/service.py
목적: PyMuPDF 로 PDF page → PNG 변환 + 디스크 캐시.

캐시 정책:
    - 경로: `{settings.page_images_path}/{document_id}/{page_no:04d}.png`
    - 캐시 hit 시 변환 skip — 첫 호출 시점 lazy 변환
    - 변환은 sync (PyMuPDF blocking) — PoC 동시 호출 적음

PDF 원본 URL 생성:
    - documents.file_path 가 `data/raw/...` 아래에 있으면 `/static/raw/...` 로 변환
    - 그 외 경로면 None (StaticFiles 가 못 서빙)
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF — app/chunks/parser.py 와 동일 import

from app.infrastructure.core.config import get_settings
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 변환
# ---------------------------------------------------------------------------


def render_page(
    document_id: int,
    page_no: int,
    file_path: str | Path,
    *,
    scale: float = 1.5,
) -> Path:
    """PDF 한 페이지를 PNG 로 변환 후 캐시 경로 반환.

    Args:
        document_id: SQLite documents.id (캐시 디렉터리 구분)
        page_no: 1-indexed (사용자 응답의 page 와 일치)
        file_path: 원본 PDF 경로 (절대 또는 cwd 기준 상대)
        scale: PyMuPDF Matrix scale. 1.5 = ~150 DPI (~80~150KB/page)

    Returns:
        캐시된 PNG 절대 경로. 호출자는 page_image_url() 로 URL 변환.
    """
    settings = get_settings()
    settings.ensure_data_dirs()

    out_dir = settings.page_images_path / str(document_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{page_no:04d}.png"

    if out_path.exists():
        return out_path

    pdf_path = Path(file_path)
    if not pdf_path.exists():
        logger.warning("PDF 원본 미존재: %s (document_id=%d)", pdf_path, document_id)
        raise FileNotFoundError(pdf_path)

    try:
        with fitz.open(str(pdf_path)) as doc:
            if page_no < 1 or page_no > doc.page_count:
                raise ValueError(
                    f"page_no={page_no} 범위 밖 (총 {doc.page_count} 페이지, document_id={document_id})"
                )
            page = doc.load_page(page_no - 1)  # 0-indexed
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
            pix.save(str(out_path))
    except Exception as exc:
        logger.error("PDF 페이지 변환 실패 document_id=%d page=%d: %s", document_id, page_no, exc)
        raise

    logger.info("PDF 페이지 변환 캐시: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# URL 헬퍼
# ---------------------------------------------------------------------------


def page_image_url(document_id: int, page_no: int) -> str:
    """StaticFiles 가 노출하는 캐시 이미지 URL."""
    return f"/static/page_images/{document_id}/{page_no:04d}.png"


def pdf_url(file_path: str | Path) -> str | None:
    """원본 PDF 가 data/raw/ 아래에 있으면 /static/raw/... URL 반환, 아니면 None.

    PDF 가 StaticFiles 의 `data/raw` 마운트 밖에 있으면 (예: 절대 경로 외부 PDF) 노출 불가.
    """
    settings = get_settings()
    pdf_path = Path(file_path).resolve()
    raw_root = settings.raw_data_path.resolve()
    try:
        rel = pdf_path.relative_to(raw_root)
    except ValueError:
        return None
    # Windows 경로 → URL 슬래시
    return f"/static/raw/{rel.as_posix()}"
