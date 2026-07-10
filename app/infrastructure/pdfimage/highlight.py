"""app.infrastructure.pdfimage.highlight

인용된 약관 조항의 PDF 내 위치를 즉석 검색(PyMuPDF)해 정규화 하이라이트 박스를 만든다.
청크에 bbox 를 저장하지 않았어도 재적재 없이 인용 hydrate 시점에 계산한다.

Sprint 35 재작성 — '매칭 단어만' 칠하던 방식은 조사·표기 차이로 문장 중간이 뚝뚝
끊긴 누더기 하이라이트가 됐다(사용자 실지적). 지금은 **라인별 매칭 밀도**로 인용
본문이 차지하는 연속 라인 구간을 찾고, 구간 안 라인은 **라인 전체**를 형광펜 블록처럼
덮는다(중간 1~2라인의 저밀도 표·숫자 라인은 갭으로 허용).

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
# 라인이 인용 본문에 속한다고 보는 매칭 밀도(글자 기준) 하한.
_LINE_RATIO = 0.5
# 구간 병합 시 허용하는 연속 저밀도 라인 수(표 셀·숫자·기호 라인 관용).
_GAP_LINES = 2


def _chunk_haystack(text: str) -> str:
    """청크 텍스트를 매칭용으로 정규화 — 표 파이프/구분선/공백 제거."""
    return re.sub(r"\s+", "", re.sub(r"\|+|:?-{2,}:?", " ", text))


def find_highlights(
    pdf_path: str | Path,
    page_no: int,
    text: str,
    clause_no: str | None = None,
) -> list[dict[str, float]]:
    """인용 조항 텍스트가 페이지에서 차지하는 연속 라인 블록을 정규화 박스로 반환.

    1) 페이지 단어를 (단, 라인) 으로 그룹 → 라인별 '청크 텍스트 매칭 밀도' 계산
    2) clause_no 앵커·단(column) 윈도우로 다른 조항의 흔한 단어 오탐 제외
    3) 밀도 ≥ 0.5 라인을 시드로 연속 구간을 만들고(저밀도 1~2라인 갭 허용),
       구간 안 라인은 라인 전체 폭으로 반환 — 끊긴 조각이 아닌 블록 하이라이트.
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

            # 앵커: clause_no(예: '제4조')가 있으면 그 위치를 기준으로 근처만 채택
            anchor_x: float | None = None
            anchor_y: float | None = None
            if clause_no:
                for wr in page.search_for(clause_no.strip(), quads=False):
                    anchor_x, anchor_y = wr.x0, wr.y0
                    break

            # 가로(2단) 페이지는 텍스트가 '왼쪽 단 하단 → 오른쪽 단 상단'으로 흐른다.
            # 세로 페이지용 y-윈도우를 그대로 쓰면 오른쪽 단 전체가 오탐 처리돼
            # 하이라이트가 거의 사라짐(삼성/현대 실측) → 단(column) 인지 윈도우로 분기.
            landscape = pw > ph
            mid_x = pw / 2.0

            def _in_window(wx0: float, wy0: float) -> bool:
                if anchor_y is None:
                    return True
                if not landscape or anchor_x is None:
                    return anchor_y - 40 <= wy0 <= anchor_y + 520
                anchor_left = anchor_x < mid_x
                word_left = wx0 < mid_x
                if anchor_left == word_left:
                    return wy0 >= anchor_y - 40  # 같은 단 — 앵커부터 아래로
                # 다른 단: 앵커가 왼쪽이면 오른쪽 단은 이어지는 본문(전체 허용),
                # 앵커가 오른쪽이면 왼쪽 단은 이전 조항 → 제외
                return anchor_left

            # 표 셀 감지 — 셀 안 단어는 '가로 라인'이 아니라 **셀 단위**로 밀도를 판정한다.
            # 라인 그룹핑은 같은 y 의 여러 셀(구분|공제금액|보장한도)을 한 줄로 합쳐
            # 행 전체를 가로지르는 스트라이프를 만들었다(사용자 실지적) → 셀 격리.
            cell_rects: list[fitz.Rect] = []
            try:
                for tab in page.find_tables().tables:
                    for c in tab.cells or []:
                        if c:
                            cell_rects.append(fitz.Rect(c))
            except Exception:
                cell_rects = []  # 표 감지 실패 시 라인 모드 폴백

            def _cell_of(wx0: float, wy0: float, wx1: float, wy1: float) -> int | None:
                pt = fitz.Point((wx0 + wx1) / 2, (wy0 + wy1) / 2)
                for i, r in enumerate(cell_rects):
                    if r.contains(pt):
                        return i
                return None

            # 1) 그룹 구성 — 표 밖: (단, y근사) 라인 / 표 안: 셀. 매칭 여부와 무관하게
            #    전체 박스와 글자수·매칭 글자수를 함께 적산한다.
            class _Line:
                __slots__ = ("box", "total", "matched")

                def __init__(self) -> None:
                    self.box = [float("inf"), float("inf"), 0.0, 0.0]
                    self.total = 0
                    self.matched = 0

            lines: dict[tuple[int, int], _Line] = {}
            cells: dict[int, _Line] = {}
            for x0, y0, x1, y1, word, *_ in words:
                tok = re.sub(r"\s+", "", word)
                if not tok:
                    continue
                if not _in_window(x0, y0):
                    continue
                cell_id = _cell_of(x0, y0, x1, y1)
                if cell_id is not None:
                    ln = cells.setdefault(cell_id, _Line())
                else:
                    col = 1 if (landscape and x0 >= mid_x) else 0
                    key = (round(y0 / 4.0), col)
                    ln = lines.setdefault(key, _Line())
                ln.box[0] = min(ln.box[0], x0)
                ln.box[1] = min(ln.box[1], y0)
                ln.box[2] = max(ln.box[2], x1)
                ln.box[3] = max(ln.box[3], y1)
                ln.total += len(tok)
                if len(tok) >= 2 and tok in haystack:
                    ln.matched += len(tok)

            # 2) 단별로 y 순 정렬 → 밀도 시드 라인의 연속 구간(run) 병합 (갭 허용)
            rects: list[dict[str, float]] = []
            for col in (0, 1):
                ordered = sorted(
                    (ln for (k, c), ln in lines.items() if c == col),
                    key=lambda ln: ln.box[1],
                )
                runs: list[list[_Line]] = []
                cur: list[_Line] = []
                pending: list[_Line] = []  # 시드 사이 저밀도 라인 후보(갭)
                for ln in ordered:
                    dense = ln.total > 0 and (ln.matched / ln.total) >= _LINE_RATIO
                    if dense:
                        # 세로 간격이 라인 높이 2.5배를 넘으면 본문 흐름이 끊긴 것
                        # (페이지 푸터·머리말 등) → 갭 라인 수와 무관하게 런 분리.
                        far = bool(cur) and (
                            ln.box[1] - cur[-1].box[3]
                            > 2.5 * max(ln.box[3] - ln.box[1], 8.0)
                        )
                        if cur and not far and len(pending) <= _GAP_LINES:
                            cur.extend(pending)  # 시드 사이 갭 라인 포함
                        elif cur:
                            runs.append(cur)
                            cur = []
                        pending = []
                        cur.append(ln)
                    elif cur:
                        pending.append(ln)
                        if len(pending) > _GAP_LINES:
                            runs.append(cur)
                            cur = []
                            pending = []
                if cur:
                    runs.append(cur)

                # 지배적 블록(3줄+)이 있으면 고립 1줄 run 은 오탐(페이지 푸터·머리말 등)으로 제거
                if any(len(r) >= 3 for r in runs):
                    runs = [r for r in runs if len(r) >= 2]
                selected = [ln for r in runs for ln in r]

                for ln in selected:
                    x0, y0, x1, y1 = ln.box
                    rects.append(
                        {
                            "x": max(0.0, min(1.0, x0 / pw)),
                            "y": max(0.0, min(1.0, y0 / ph)),
                            "w": max(0.0, min(1.0, (x1 - x0) / pw)),
                            "h": max(0.0, min(1.0, (y1 - y0) / ph)),
                        }
                    )
                    if len(rects) >= _MAX_RECTS:
                        return rects

            # 3) 표 셀 — 셀 텍스트의 매칭 밀도로 셀 단위 채택(행 스트라이프 없음).
            #    셀 문구는 본문 상용구와 우연히 겹치기 쉬워(실측: 본문만 담은 청크에서
            #    '주사치료를 받아 본인이 실제로 부담한…' 셀이 0.68) 라인보다 강한
            #    임계(밀도 0.75 + 매칭 8자)를 요구한다 — 청크가 셀을 실제 포함하면 ~1.0.
            for ln in cells.values():
                if ln.total <= 0 or ln.matched < 8:
                    continue
                if (ln.matched / ln.total) < 0.75:
                    continue
                x0, y0, x1, y1 = ln.box
                rects.append(
                    {
                        "x": max(0.0, min(1.0, x0 / pw)),
                        "y": max(0.0, min(1.0, y0 / ph)),
                        "w": max(0.0, min(1.0, (x1 - x0) / pw)),
                        "h": max(0.0, min(1.0, (y1 - y0) / ph)),
                    }
                )
                if len(rects) >= _MAX_RECTS:
                    return rects
            return rects
    except Exception as exc:  # PyMuPDF 예외 등 — 하이라이트는 부가 기능이라 조용히 무시
        logger.warning("하이라이트 계산 실패 %s p%d: %s", pdf_path, page_no, exc)
        return []
