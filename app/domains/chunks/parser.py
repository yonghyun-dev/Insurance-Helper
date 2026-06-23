"""app.domains.chunks.parser

파일 경로: app/chunks/parser.py
목적: PDF 파일을 페이지 단위 텍스트와 표 구조로 추출한다. 구조 인식과 청킹은
      후속 단계(structure.py / chunker.py)에서 처리하며 본 모듈은 원시 추출만 담당.

주요 기능:
    - `parse_pdf(path)` 진입점: PyMuPDF로 텍스트 추출 + pdfplumber로 표 추출
    - 페이지 헤더/푸터 자동 검출(반복 텍스트 휴리스틱)로 노이즈 제거
    - 표 캡션은 표 직전 본문 라인에서 추정

주요 의존성: pymupdf(fitz), pdfplumber

설계 메모:
    - 두 라이브러리를 조합하는 이유: PyMuPDF는 본문 텍스트 추출이 빠르고 안정적,
      pdfplumber는 표 인식 품질이 더 좋다. 표만 pdfplumber에 위임.
    - parser_version 은 구조 변경 시 bump 한다. SQLite documents.parser_version 과 매칭.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber

from app.domains.chunks.schemas import RawDocument, RawPage, RawTable
from app.infrastructure.core.exceptions import IngestionError
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

PARSER_VERSION = "0.1.0"

# 헤더/푸터 탐지에 사용할 페이지 상/하단 비율
HEADER_RATIO = 0.08
FOOTER_RATIO = 0.92

# 표 캡션 후보 패턴 (예: "[별표 1]", "<표 3>", "표 1.")
_TABLE_CAPTION_RE = re.compile(r"^\s*(\[?\s*별표\s*\d+\s*\]?|<\s*표\s*\d+\s*>|표\s*\d+\.?)")


def parse_pdf(file_path: Path | str) -> RawDocument:
    """PDF 파일을 RawDocument 로 파싱한다.

    Args:
        file_path: 파싱할 PDF 경로.

    Returns:
        RawDocument: 페이지 리스트 + 메타.

    Raises:
        IngestionError: 파일이 없거나 PDF 가 손상되어 열 수 없을 때.
    """
    path = Path(file_path)
    if not path.exists():
        raise IngestionError(f"PDF 파일을 찾을 수 없습니다: {path}")
    if not path.is_file():
        raise IngestionError(f"경로가 파일이 아닙니다: {path}")

    logger.info("PDF 파싱 시작: %s", path)

    try:
        pages = _extract_pages(path)
    except Exception as exc:  # PyMuPDF/pdfplumber 모두 PDFSyntaxError 등 다양한 예외
        raise IngestionError(f"PDF 파싱 실패: {path} ({exc})") from exc

    if not pages:
        raise IngestionError(f"PDF 에서 페이지를 한 개도 추출하지 못했습니다: {path}")

    metadata = _extract_metadata(path)
    logger.info(
        "PDF 파싱 완료: %s (페이지 %d, 표 %d)",
        path,
        len(pages),
        sum(len(p.tables) for p in pages),
    )

    return RawDocument(
        file_path=str(path),
        page_count=len(pages),
        pages=pages,
        parser_version=PARSER_VERSION,
        metadata=metadata,
    )


def _extract_metadata(path: Path) -> dict[str, str]:
    """PDF 메타데이터(producer, title 등)를 dict 로 추출."""
    try:
        with fitz.open(path) as doc:
            meta = doc.metadata or {}
    except Exception:
        return {}
    return {k: str(v) for k, v in meta.items() if v}


def _extract_pages(path: Path) -> list[RawPage]:
    """본문 텍스트(PyMuPDF) + 표(pdfplumber) 를 합쳐 RawPage 리스트를 만든다."""
    raw_texts: list[str] = []
    widths: list[float] = []
    heights: list[float] = []

    with fitz.open(path) as doc:
        for page in doc:
            raw_texts.append(page.get_text("text") or "")
            rect = page.rect
            widths.append(rect.width)
            heights.append(rect.height)

    # 헤더/푸터 검출: 페이지 상위 N%/하위 N% 라인 중 반복되는 것
    header_lines, footer_lines = _detect_repeating_header_footer(raw_texts)

    tables_per_page = _extract_tables(path)

    pages: list[RawPage] = []
    for idx, raw in enumerate(raw_texts):
        cleaned = _strip_header_footer(raw, header_lines, footer_lines)
        pages.append(
            RawPage(
                page=idx + 1,
                text=cleaned,
                raw_text=raw,
                tables=tables_per_page.get(idx + 1, []),
                width=widths[idx],
                height=heights[idx],
            )
        )
    return pages


def _detect_repeating_header_footer(
    raw_texts: list[str],
) -> tuple[set[str], set[str]]:
    """페이지 상/하단에서 반복적으로 등장하는 라인을 헤더/푸터로 식별한다.

    기준: 전체 페이지의 60% 이상에서 같은 짧은 라인이 등장하면 반복으로 본다.
    매우 짧은 페이지가 섞여 있어도 false positive 영향이 작도록 라인을 normalize.
    """
    if len(raw_texts) < 3:
        return set(), set()

    threshold = max(2, int(len(raw_texts) * 0.6))
    head_counter: Counter[str] = Counter()
    foot_counter: Counter[str] = Counter()

    for raw in raw_texts:
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:
            continue
        head_window = max(1, int(len(lines) * HEADER_RATIO))
        foot_window = max(1, len(lines) - int(len(lines) * FOOTER_RATIO))
        for line in lines[:head_window]:
            if _looks_like_recurring(line):
                head_counter[line] += 1
        for line in lines[-foot_window:]:
            if _looks_like_recurring(line):
                foot_counter[line] += 1

    headers = {line for line, count in head_counter.items() if count >= threshold}
    footers = {line for line, count in foot_counter.items() if count >= threshold}
    return headers, footers


def _looks_like_recurring(line: str) -> bool:
    """헤더/푸터 후보가 될 만큼 짧고 일반적인 라인인지 판단.

    TODO (Sprint 5+ 백로그):
        현재 80자 초과만 거르고 그 외는 모두 True 라 사실상 필터링 효과가 없다.
        실제 보험약관에서 헤더/푸터 제거 효과 0% 의 원인 중 하나. 페이지 번호를
        `<PAGE_NUM>` 으로 정규화해 카운터에 잡히게 하는 등 추가 휴리스틱 필요.
    """
    if len(line) > 80:
        return False  # 본문일 가능성이 큼
    if re.fullmatch(r"\d+", line):
        return True  # 페이지 번호
    return True


def _strip_header_footer(raw: str, headers: set[str], footers: set[str]) -> str:
    """반복 헤더/푸터 라인을 제거한 본문을 반환."""
    if not headers and not footers:
        return raw
    kept: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped and (stripped in headers or stripped in footers):
            continue
        kept.append(line)
    return "\n".join(kept)


def _extract_tables(path: Path) -> dict[int, list[RawTable]]:
    """pdfplumber 로 표를 추출하고 페이지 번호 기준으로 묶는다."""
    result: dict[int, list[RawTable]] = {}
    try:
        with pdfplumber.open(path) as pdf:
            for idx, page in enumerate(pdf.pages):
                tables_on_page: list[RawTable] = []
                try:
                    page_tables = page.extract_tables() or []
                except Exception as exc:  # 표 추출 실패는 페이지 단위로 무시
                    logger.warning("page %d 표 추출 실패: %s", idx + 1, exc)
                    page_tables = []

                page_text_lines = (page.extract_text() or "").splitlines()
                for raw_rows in page_tables:
                    rows = _normalize_table_rows(raw_rows)
                    if not rows:
                        continue
                    caption = _infer_table_caption(page_text_lines)
                    tables_on_page.append(RawTable(page=idx + 1, rows=rows, caption=caption))
                if tables_on_page:
                    result[idx + 1] = tables_on_page
    except Exception as exc:
        logger.warning("pdfplumber 표 추출 전체 실패: %s", exc)
    return result


def _normalize_table_rows(raw_rows: list[list[str | None]] | None) -> list[list[str]]:
    """None 셀을 빈 문자열로 치환하고 모든 셀이 비어 있는 행은 제거."""
    if not raw_rows:
        return []
    cleaned: list[list[str]] = []
    for row in raw_rows:
        normalized = [(cell or "").strip() for cell in row]
        if any(normalized):
            cleaned.append(normalized)
    return cleaned


def _infer_table_caption(page_text_lines: list[str]) -> str | None:
    """페이지 텍스트에서 표 캡션 후보 라인을 찾아 첫 매칭만 반환."""
    for line in page_text_lines:
        stripped = line.strip()
        if _TABLE_CAPTION_RE.match(stripped):
            return stripped
    return None
