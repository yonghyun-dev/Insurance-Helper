"""tests.chunks.test_parser

app/chunks/parser.py 단위 테스트.

테스트 대상:
    - parse_pdf: 파일 없음, 손상 파일 에러 처리
    - _detect_repeating_header_footer: 반복 라인 감지
    - _strip_header_footer: 헤더/푸터 제거
    - _normalize_table_rows: None 셀 정규화
    - _infer_table_caption: 캡션 후보 탐색

PyMuPDF 직접 생성이 복잡하므로 fitz/pdfplumber 를 mock 하고
parse_pdf 경로 검증은 실제 에러 케이스만 다룬다.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.domains.chunks.parser import (
    _detect_repeating_header_footer,
    _infer_table_caption,
    _normalize_table_rows,
    _strip_header_footer,
    parse_pdf,
)
from app.infrastructure.core.exceptions import IngestionError

# ===========================================================================
# parse_pdf — 에러 케이스 (파일 시스템 / 손상 파일)
# ===========================================================================


class TestParsePdfErrors:
    """parse_pdf 파일 오류 처리 검증."""

    def test_nonexistent_file_raises_ingestion_error(self, tmp_path):
        # 없는 파일 경로 → IngestionError
        missing = tmp_path / "nonexistent.pdf"
        with pytest.raises(IngestionError, match="찾을 수 없습니다"):
            parse_pdf(missing)

    def test_directory_path_raises_ingestion_error(self, tmp_path):
        # 경로가 파일이 아닌 디렉터리 → IngestionError
        with pytest.raises(IngestionError, match="파일이 아닙니다"):
            parse_pdf(tmp_path)

    def test_corrupt_pdf_raises_ingestion_error(self, tmp_path):
        # 내용이 깨진 파일 → IngestionError
        bad_pdf = tmp_path / "corrupt.pdf"
        bad_pdf.write_bytes(b"not a real pdf content")

        with pytest.raises(IngestionError):
            parse_pdf(bad_pdf)


# ===========================================================================
# parse_pdf — mock 기반 정상 케이스
# ===========================================================================


class TestParsePdfMocked:
    """fitz/pdfplumber 를 mock 해서 parse_pdf 정상 흐름을 검증한다."""

    def _make_fitz_doc_mock(self, page_texts: list[str]):
        """fitz.open 컨텍스트 매니저 mock 을 만든다."""
        mock_pages = []
        for text in page_texts:
            page_mock = MagicMock()
            page_mock.get_text.return_value = text
            rect_mock = MagicMock()
            rect_mock.width = 595.0
            rect_mock.height = 842.0
            page_mock.rect = rect_mock
            mock_pages.append(page_mock)

        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)
        mock_doc.__iter__ = MagicMock(return_value=iter(mock_pages))
        mock_doc.metadata = {"title": "테스트약관", "producer": "테스트출판"}
        return mock_doc

    def _make_pdfplumber_mock(self):
        """pdfplumber.open 컨텍스트 매니저 mock (표 없음)."""
        mock_page = MagicMock()
        mock_page.extract_tables.return_value = []
        mock_page.extract_text.return_value = ""

        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]
        return mock_pdf

    def test_parse_pdf_returns_raw_document(self, tmp_path):
        # 정상 PDF → RawDocument 반환
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")  # 파일 존재만 확인용

        fitz_mock = self._make_fitz_doc_mock(["제1조 본문입니다."])
        plumber_mock = self._make_pdfplumber_mock()

        with (
            patch("app.domains.chunks.parser.fitz.open", return_value=fitz_mock),
            patch("app.domains.chunks.parser.pdfplumber.open", return_value=plumber_mock),
        ):
            result = parse_pdf(pdf_path)

        assert result.page_count == 1
        assert len(result.pages) == 1
        assert result.pages[0].page == 1

    def test_parse_pdf_preserves_text(self, tmp_path):
        # 텍스트가 RawPage.text 에 보존됨
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        expected_text = "제1조 (보험금 지급)\n보험사고 발생 시 지급합니다."
        fitz_mock = self._make_fitz_doc_mock([expected_text])
        plumber_mock = self._make_pdfplumber_mock()

        with (
            patch("app.domains.chunks.parser.fitz.open", return_value=fitz_mock),
            patch("app.domains.chunks.parser.pdfplumber.open", return_value=plumber_mock),
        ):
            result = parse_pdf(pdf_path)

        # 헤더/푸터 없으므로 원문 그대로 (3페이지 미만 — 헤더 감지 미동작)
        assert "제1조" in result.pages[0].text

    def test_parse_pdf_empty_pages_raises_ingestion_error(self, tmp_path):
        # 페이지를 한 개도 추출 못하면 IngestionError
        pdf_path = tmp_path / "empty.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        fitz_mock = MagicMock()
        fitz_mock.__enter__ = MagicMock(return_value=fitz_mock)
        fitz_mock.__exit__ = MagicMock(return_value=False)
        fitz_mock.__iter__ = MagicMock(return_value=iter([]))
        fitz_mock.metadata = {}

        plumber_mock = self._make_pdfplumber_mock()
        plumber_mock.pages = []

        with (
            patch("app.domains.chunks.parser.fitz.open", return_value=fitz_mock),
            patch("app.domains.chunks.parser.pdfplumber.open", return_value=plumber_mock),
            pytest.raises(IngestionError, match="한 개도"),
        ):
            parse_pdf(pdf_path)


# ===========================================================================
# _detect_repeating_header_footer
# ===========================================================================


class TestDetectRepeatingHeaderFooter:
    """반복 헤더/푸터 감지 로직 검증."""

    def test_fewer_than_3_pages_returns_empty(self):
        # 3페이지 미만이면 감지 안 함
        texts = ["페이지1 내용", "페이지2 내용"]
        headers, footers = _detect_repeating_header_footer(texts)
        assert len(headers) == 0
        assert len(footers) == 0

    def test_repeated_header_line_detected(self):
        # 첫 줄이 모든 페이지에서 반복 → 헤더로 감지
        repeated = "한국화재보험 약관"
        texts = [
            f"{repeated}\n제1조 본문1입니다.",
            f"{repeated}\n제2조 본문2입니다.",
            f"{repeated}\n제3조 본문3입니다.",
            f"{repeated}\n제4조 본문4입니다.",
            f"{repeated}\n제5조 본문5입니다.",
        ]
        headers, _ = _detect_repeating_header_footer(texts)
        assert repeated in headers

    def test_unique_lines_not_detected_as_header(self):
        # 반복되지 않는 라인은 헤더 아님
        texts = [
            "고유한 첫 줄 1\n본문입니다.",
            "고유한 첫 줄 2\n본문입니다.",
            "고유한 첫 줄 3\n본문입니다.",
        ]
        headers, _ = _detect_repeating_header_footer(texts)
        assert len(headers) == 0


# ===========================================================================
# _strip_header_footer
# ===========================================================================


class TestStripHeaderFooter:
    """헤더/푸터 제거 로직 검증."""

    def test_header_lines_removed(self):
        # 헤더 라인이 제거됨
        raw = "한국화재보험\n제1조 본문입니다.\n연락처: 1588-0000"
        headers = {"한국화재보험"}
        footers = {"연락처: 1588-0000"}
        result = _strip_header_footer(raw, headers, footers)
        assert "한국화재보험" not in result
        assert "연락처: 1588-0000" not in result
        assert "제1조 본문입니다." in result

    def test_empty_headers_footers_returns_original(self):
        # 헤더/푸터 없으면 원문 그대로
        raw = "제1조 본문입니다."
        result = _strip_header_footer(raw, set(), set())
        assert result == raw

    def test_body_text_preserved(self):
        # 본문은 그대로 유지됨
        raw = "헤더\n본문 내용1\n본문 내용2\n푸터"
        result = _strip_header_footer(raw, {"헤더"}, {"푸터"})
        assert "본문 내용1" in result
        assert "본문 내용2" in result


# ===========================================================================
# _normalize_table_rows
# ===========================================================================


class TestNormalizeTableRows:
    """표 행 정규화 로직 검증."""

    def test_none_cells_replaced_with_empty_string(self):
        # None 셀 → 빈 문자열
        rows = [[None, "값", None], ["a", None, "b"]]
        result = _normalize_table_rows(rows)
        assert result[0][0] == ""
        assert result[0][2] == ""
        assert result[1][1] == ""

    def test_all_empty_row_removed(self):
        # 모든 셀이 비어 있는 행은 제거
        rows = [["항목", "값"], [None, None], ["a", "b"]]
        result = _normalize_table_rows(rows)
        assert len(result) == 2  # [None, None] 행 제거됨

    def test_empty_input_returns_empty(self):
        # 빈 입력 → 빈 리스트
        assert _normalize_table_rows([]) == []
        assert _normalize_table_rows(None) == []  # type: ignore

    def test_whitespace_cells_stripped(self):
        # 공백만 있는 셀 → 빈 문자열
        rows = [["  항목  ", "  값  "]]
        result = _normalize_table_rows(rows)
        assert result[0][0] == "항목"
        assert result[0][1] == "값"


# ===========================================================================
# _infer_table_caption
# ===========================================================================


class TestInferTableCaption:
    """표 캡션 추론 로직 검증."""

    def test_table_pattern_returns_caption(self):
        # "표 1." 패턴 → 캡션 반환
        lines = ["제1조 본문", "표 1. 보장 한도", "내용"]
        result = _infer_table_caption(lines)
        assert result == "표 1. 보장 한도"

    def test_annex_pattern_returns_caption(self):
        # "[별표 1]" 패턴 → 캡션 반환
        lines = ["[별표 1] 보장 한도표"]
        result = _infer_table_caption(lines)
        assert result == "[별표 1] 보장 한도표"

    def test_no_matching_line_returns_none(self):
        # 캡션 패턴 없으면 None
        lines = ["제1조 본문입니다.", "① 보험료를 납입합니다."]
        result = _infer_table_caption(lines)
        assert result is None

    def test_first_match_returned(self):
        # 여러 캡션 후보 중 첫 번째만 반환
        lines = ["표 1. 첫 번째", "표 2. 두 번째"]
        result = _infer_table_caption(lines)
        assert result == "표 1. 첫 번째"

    def test_empty_lines_returns_none(self):
        # 빈 리스트 → None
        assert _infer_table_caption([]) is None
