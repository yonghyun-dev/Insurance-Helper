"""tests.ingestion.test_ingestion_service

app/ingestion/service.py 단위 테스트.

테스트 대상:
    - _parse_version_label: 3가지 형식 파싱 + 폴백
    - _infer_doc_type: 키워드 매칭 + 인식 불가
    - _sha256_of: 파일 SHA256 계산
    - parse_pdf_path: 경로 분해 정상/에러 케이스
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from app.domains.ingestion.service import (
    _infer_doc_type,
    _parse_version_label,
    _sha256_of,
    parse_pdf_path,
)
from app.infrastructure.core.exceptions import IngestionError

# ===========================================================================
# _parse_version_label
# ===========================================================================


class TestParseVersionLabel:
    """버전 라벨 파싱 3가지 형식 검증."""

    def test_present_format_returns_none_valid_to(self):
        # "2026-03-01_present" → valid_to = None
        start, end = _parse_version_label("2026-03-01_present")
        assert start == date(2026, 3, 1)
        assert end is None

    def test_date_range_format(self):
        # "2026-03-01_2026-12-31" → 종료일 있음
        start, end = _parse_version_label("2026-03-01_2026-12-31")
        assert start == date(2026, 3, 1)
        assert end == date(2026, 12, 31)

    def test_compact_8digit_format(self):
        # "20260301" → 2026-03-01, None
        start, end = _parse_version_label("20260301")
        assert start == date(2026, 3, 1)
        assert end is None

    def test_unknown_format_falls_back_to_1900(self):
        # 인식 불가 → 1900-01-01, None (폴백)
        start, end = _parse_version_label("v2026-invalid")
        assert start == date(1900, 1, 1)
        assert end is None

    def test_empty_string_falls_back_to_1900(self):
        # 빈 문자열 → 폴백
        start, end = _parse_version_label("")
        assert start == date(1900, 1, 1)

    def test_compact_format_start_month_day(self):
        # "20261231" → 2026-12-31
        start, end = _parse_version_label("20261231")
        assert start == date(2026, 12, 31)
        assert end is None

    def test_present_format_start_date_correct(self):
        # 시작일이 정확히 파싱됨
        start, _ = _parse_version_label("2025-07-15_present")
        assert start == date(2025, 7, 15)

    def test_date_range_end_date_correct(self):
        # 종료일이 정확히 파싱됨
        _, end = _parse_version_label("2025-01-01_2025-06-30")
        assert end == date(2025, 6, 30)


# ===========================================================================
# _infer_doc_type
# ===========================================================================


class TestInferDocType:
    """파일명 키워드 기반 doc_type 추론 검증."""

    def test_terms_keyword_returns_terms(self):
        assert _infer_doc_type("hanwha_terms_2026.pdf") == "terms"

    def test_gain_keyword_returns_terms(self):
        # 한화 자동차 약관 패턴
        assert _infer_doc_type("gain_auto_standard.pdf") == "terms"

    def test_korean_terms_keyword(self):
        assert _infer_doc_type("자동차보험약관.pdf") == "terms"

    def test_policy_keyword_returns_terms(self):
        assert _infer_doc_type("policy_document.pdf") == "terms"

    def test_summary_keyword_returns_summary(self):
        assert _infer_doc_type("product_summary_2026.pdf") == "summary"

    def test_korean_summary_keyword(self):
        assert _infer_doc_type("상품요약서.pdf") == "summary"

    def test_business_keyword_returns_business(self):
        assert _infer_doc_type("business_method.pdf") == "business"

    def test_korean_business_keyword(self):
        assert _infer_doc_type("사업방법서_2026.pdf") == "business"

    def test_unknown_filename_returns_none(self):
        assert _infer_doc_type("random_file.pdf") is None

    def test_empty_filename_returns_none(self):
        assert _infer_doc_type("") is None

    def test_case_insensitive_matching(self):
        # 대소문자 무관
        assert _infer_doc_type("TERMS_DOC.pdf") == "terms"
        assert _infer_doc_type("Summary_2026.pdf") == "summary"


# ===========================================================================
# _sha256_of
# ===========================================================================


class TestSha256Of:
    """파일 SHA256 계산 검증."""

    def test_returns_64_char_hex_string(self, tmp_path):
        # SHA256 → 64자 hex
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello insurance")
        result = _sha256_of(f)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_content_same_hash(self, tmp_path):
        # 동일 내용 → 동일 해시
        content = b"test content for hashing"
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(content)
        f2.write_bytes(content)
        assert _sha256_of(f1) == _sha256_of(f2)

    def test_different_content_different_hash(self, tmp_path):
        # 내용 다름 → 해시 다름
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        assert _sha256_of(f1) != _sha256_of(f2)

    def test_empty_file_has_known_sha256(self, tmp_path):
        # 빈 파일의 SHA256 은 알려진 값
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        # SHA256 of empty string
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert _sha256_of(f) == expected


# ===========================================================================
# parse_pdf_path
# ===========================================================================


class TestParsePdfPath:
    """경로 분해 정상/에러 케이스 검증."""

    def _make_pdf(self, tmp_path: Path, parts: list[str]) -> tuple[Path, Path]:
        """지정한 경로 구조로 가짜 PDF 파일을 생성."""
        raw_root = tmp_path / "raw"
        pdf_path = raw_root / Path(*parts)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake pdf")
        return pdf_path, raw_root

    def test_valid_path_parsed_correctly(self, tmp_path):
        # 정상 5단계 경로 → PathInfo 반환
        pdf_path, raw_root = self._make_pdf(
            tmp_path,
            ["hanwha", "auto", "standard", "2026-01-01_present", "terms.pdf"],
        )
        result = parse_pdf_path(pdf_path, raw_root)

        assert result.insurer_id == "hanwha"
        assert result.area == "auto"
        assert result.product_id == "standard"
        assert result.version_label == "2026-01-01_present"
        assert result.doc_type == "terms"

    def test_fire_area_is_accepted(self, tmp_path):
        # fire 영역 코드 허용
        pdf_path, raw_root = self._make_pdf(
            tmp_path,
            ["samsung", "fire", "home_fire", "20260101", "terms.pdf"],
        )
        result = parse_pdf_path(pdf_path, raw_root)
        assert result.area == "fire"

    def test_accident_disease_area_is_accepted(self, tmp_path):
        # accident_disease 영역 코드 허용
        pdf_path, raw_root = self._make_pdf(
            tmp_path,
            ["lotte", "accident_disease", "injury_prod", "2026-01-01_present", "summary.pdf"],
        )
        result = parse_pdf_path(pdf_path, raw_root)
        assert result.area == "accident_disease"
        assert result.doc_type == "summary"

    def test_invalid_area_raises_ingestion_error(self, tmp_path):
        # 허용 목록에 없는 영역 코드 → IngestionError
        pdf_path, raw_root = self._make_pdf(
            tmp_path,
            ["hanwha", "health", "prod", "2026-01-01_present", "terms.pdf"],
        )
        with pytest.raises(IngestionError, match="영역 코드"):
            parse_pdf_path(pdf_path, raw_root)

    def test_too_shallow_path_raises_ingestion_error(self, tmp_path):
        # 4단계 미만 경로 → IngestionError
        pdf_path, raw_root = self._make_pdf(
            tmp_path,
            ["hanwha", "auto", "terms.pdf"],
        )
        with pytest.raises(IngestionError, match="5단계"):
            parse_pdf_path(pdf_path, raw_root)

    def test_unknown_doc_type_raises_ingestion_error(self, tmp_path):
        # doc_type 추론 불가 파일명 → IngestionError
        pdf_path, raw_root = self._make_pdf(
            tmp_path,
            ["hanwha", "auto", "prod", "2026-01-01_present", "unknown_file.pdf"],
        )
        with pytest.raises(IngestionError, match="doc_type"):
            parse_pdf_path(pdf_path, raw_root)

    def test_valid_from_parsed_from_version_label(self, tmp_path):
        # version_label 에서 valid_from 파싱
        pdf_path, raw_root = self._make_pdf(
            tmp_path,
            ["hanwha", "auto", "prod", "2026-03-15_present", "terms.pdf"],
        )
        result = parse_pdf_path(pdf_path, raw_root)
        assert result.valid_from == date(2026, 3, 15)
        assert result.valid_to is None

    def test_file_path_preserved_in_result(self, tmp_path):
        # file_path 가 PathInfo 에 보존됨
        pdf_path, raw_root = self._make_pdf(
            tmp_path,
            ["hanwha", "auto", "prod", "2026-01-01_present", "terms.pdf"],
        )
        result = parse_pdf_path(pdf_path, raw_root)
        assert result.file_path == pdf_path
