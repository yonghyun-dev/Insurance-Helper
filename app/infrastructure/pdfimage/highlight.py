"""app.infrastructure.pdfimage.highlight

인용된 약관 조항의 PDF 내 위치를 즉석 검색(PyMuPDF search_for)해 정규화 하이라이트
박스를 만든다. 청크에 bbox 를 저장하지 않았어도 재적재 없이 인용 hydrate 시점에 계산한다.

좌표는 페이지 크기 대비 0~1 로 정규화 → 프론트가 렌더된 이미지 크기에 맞춰 오버레이한다
(render_page 의 scale 과 무관하게 동작).
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF

from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

_MAX_RECTS = 60


def _chunk_haystack(text: str) -> str:
    """청크 텍스트를 매칭용으로 정규화 — 표 파이프/구분선/공백 제거."""
    return re.sub(r"\s+", "", re.sub(r"\|+|:?-{2,}:?", " ", text))


def find_highlights(
    pdf_path: str | Path,
    page_no: int,
    text: str,
    clause_no: str | None = None,
) -> list[dict[str, float]]:
    """인용 조항 텍스트가 페이지에서 차지하는 라인들을 정규화 박스로 반환.

    페이지 단어(get_text('words')) 중 청크 텍스트에 포함되는 단어를 찾아 라인 단위로
    병합한다. 단서(clause_no)로 세로 앵커를 잡아 다른 위치의 흔한 단어 오탐을 줄인다.
    실패/미검출 시 빈 리스트.
    """
    p = Path(pdf_path)
    if not p.exists() or not text:
        return []
    try:
        with fitz.open(str(p)) as doc:
            if page_no < 1 or page_no > doc.page_count:
                return []
            page = doc.load_page(page_no - 1)  # 0-indexed
            pw, ph = page.rect.width, page.rect.height
            if not pw or not ph:
                return []

            haystack = _chunk_haystack(text)
            if len(haystack) < 6:
                return []

            words = page.get_text("words")  # (x0,y0,x1,y1, word, block, line, word_no)

            # 세로 앵커: clause_no(예: '제4조')가 있으면 그 위치 y 를 기준으로 근처만 채택
            anchor_y: float | None = None
            if clause_no:
                for wr in page.search_for(clause_no.strip(), quads=False):
                    anchor_y = wr.y0
                    break

            # 라인(y 근사) 별로 매칭 단어 박스를 병합
            lines: dict[int, list[float]] = {}
            line_hits: dict[int, int] = {}
            for x0, y0, x1, y1, word, *_ in words:
                tok = re.sub(r"\s+", "", word)
                if len(tok) < 2 or tok not in haystack:
                    continue
                if anchor_y is not None and not (anchor_y - 40 <= y0 <= anchor_y + 520):
                    continue  # 앵커에서 너무 먼 흔한 단어 오탐 제외
                key = round(y0 / 4.0)  # 같은 라인 근사 그룹
                box = lines.get(key)
                if box is None:
                    lines[key] = [x0, y0, x1, y1]
                    line_hits[key] = 1
                else:
                    box[0] = min(box[0], x0)
                    box[1] = min(box[1], y0)
                    box[2] = max(box[2], x1)
                    box[3] = max(box[3], y1)
                    line_hits[key] += 1

            rects: list[dict[str, float]] = []
            for key, box in lines.items():
                if line_hits[key] < 2:
                    continue  # 단어 1개만 맞은 라인은 오탐 가능 → 제외
                x0, y0, x1, y1 = box
                rects.append(
                    {
                        "x": max(0.0, min(1.0, x0 / pw)),
                        "y": max(0.0, min(1.0, y0 / ph)),
                        "w": max(0.0, min(1.0, (x1 - x0) / pw)),
                        "h": max(0.0, min(1.0, (y1 - y0) / ph)),
                    }
                )
                if len(rects) >= _MAX_RECTS:
                    break
            return rects
    except Exception as exc:  # PyMuPDF 예외 등 — 하이라이트는 부가 기능이라 조용히 무시
        logger.warning("하이라이트 계산 실패 %s p%d: %s", pdf_path, page_no, exc)
        return []
