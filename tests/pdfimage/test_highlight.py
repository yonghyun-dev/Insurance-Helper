"""find_highlights — 세로/가로(2단) 페이지 하이라이트 계산 검증.

Sprint 35: 가로 2단 약관(삼성/현대)에서 y-앵커 윈도우가 오른쪽 단 전체를
오탐 처리해 하이라이트가 사라지던 버그(실측 64단어→5단어)의 회귀 방지.
"""

from __future__ import annotations

import fitz
from app.infrastructure.pdfimage.highlight import find_highlights

# 매칭 대상 본문 — 왼쪽 단 하단에서 시작해 오른쪽 단 상단으로 이어지는 조항.
_BODY_LEFT = ["회사는", "피보험자가", "상해로", "의료기관에", "입원하여"]
_BODY_RIGHT = ["치료를", "받은", "경우에는", "보상한도", "내에서", "의료비를", "보상합니다"]
_CHUNK_TEXT = "제3조 " + " ".join(_BODY_LEFT + _BODY_RIGHT)


def _make_pdf(tmp_path, landscape: bool):
    """왼쪽 단 하단에 조항 시작, (가로면) 오른쪽 단 상단에 본문이 이어지는 페이지."""
    w, h = (842, 595) if landscape else (595, 842)
    doc = fitz.open()
    page = doc.new_page(width=w, height=h)
    # 앵커: 왼쪽 단 하단(가로) / 상단(세로)
    anchor_y = h - 120 if landscape else 100
    page.insert_text((40, anchor_y), "제3조 (보장종목별 보상내용)", fontsize=10, fontname="korea")
    y = anchor_y + 16
    for word in _BODY_LEFT:
        page.insert_text((40, y), f"{word} 보상", fontsize=10, fontname="korea")  # 라인당 2글자+ 단어 2개(≥2 히트)
        y += 14
    # 이어지는 본문: 가로면 오른쪽 단 상단, 세로면 같은 단 아래
    x2 = w / 2 + 40 if landscape else 40
    y2 = 60 if landscape else y
    for word in _BODY_RIGHT:
        page.insert_text((x2, y2), f"{word} 한도", fontsize=10, fontname="korea")
        y2 += 14
    p = tmp_path / ("landscape.pdf" if landscape else "portrait.pdf")
    doc.save(str(p))
    doc.close()
    return p


class TestLandscapeTwoColumn:
    def test_right_column_continuation_is_highlighted(self, tmp_path):
        """가로 2단: 앵커(왼쪽 단)와 다른 단(오른쪽)의 이어지는 본문도 잡아야 한다."""
        pdf = _make_pdf(tmp_path, landscape=True)
        rects = find_highlights(pdf, 1, _CHUNK_TEXT, "제3조")
        assert rects, "가로 2단에서 하이라이트가 비면 안 됨"
        right = [r for r in rects if r["x"] >= 0.5]
        assert right, "오른쪽 단(이어지는 본문) 하이라이트가 있어야 함"

    def test_no_full_width_merged_box(self, tmp_path):
        """가로 2단: 좌/우 단이 같은 y 라인으로 병합돼 전폭 박스가 되면 안 된다."""
        pdf = _make_pdf(tmp_path, landscape=True)
        rects = find_highlights(pdf, 1, _CHUNK_TEXT, "제3조")
        assert all(r["w"] < 0.6 for r in rects), "단일 단 폭을 넘는 병합 박스 금지"

    def test_previous_column_excluded_when_anchor_right(self, tmp_path):
        """앵커가 오른쪽 단이면 왼쪽 단(이전 조항)은 제외된다."""
        w, h = 842, 595
        doc = fitz.open()
        page = doc.new_page(width=w, height=h)
        # 왼쪽 단: 이전 조항의 흔한 단어들 (오탐 후보)
        for i, word in enumerate(_BODY_RIGHT):
            page.insert_text((40, 80 + i * 14), f"{word} 한도", fontsize=10, fontname="korea")
        # 오른쪽 단: 앵커 + 본문
        page.insert_text((w / 2 + 40, 60), "제3조 (보장종목별 보상내용)", fontsize=10, fontname="korea")
        for i, word in enumerate(_BODY_LEFT):
            page.insert_text((w / 2 + 40, 80 + i * 14), f"{word} 보상", fontsize=10, fontname="korea")
        p = tmp_path / "anchor_right.pdf"
        doc.save(str(p))
        doc.close()
        rects = find_highlights(p, 1, _CHUNK_TEXT, "제3조")
        assert rects
        assert all(r["x"] >= 0.5 for r in rects), "앵커가 오른쪽 단이면 왼쪽 단은 이전 본문 → 제외"


class TestPortraitRegression:
    def test_portrait_anchor_window_still_applies(self, tmp_path):
        """세로: 기존 y-윈도우 동작 유지 — 앵커 아래 본문이 잡힌다."""
        pdf = _make_pdf(tmp_path, landscape=False)
        rects = find_highlights(pdf, 1, _CHUNK_TEXT, "제3조")
        assert rects, "세로 페이지 하이라이트 회귀"

    def test_empty_on_missing_file(self, tmp_path):
        assert find_highlights(tmp_path / "none.pdf", 1, _CHUNK_TEXT) == []

    def test_empty_on_short_text(self, tmp_path):
        pdf = _make_pdf(tmp_path, landscape=False)
        assert find_highlights(pdf, 1, "짧음") == []
