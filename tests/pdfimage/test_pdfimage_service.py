"""tests.pdfimage.test_pdfimage_service

app/pdfimage/service.py 단위 테스트.

테스트 대상:
    - render_page: 캐시 hit (파일 존재 시 변환 skip + 동일 경로 반환)
    - render_page: 캐시 miss (PyMuPDF mock — pix.save 호출 확인)
    - render_page: PDF 부재 → FileNotFoundError
    - render_page: page_no 범위 밖 → ValueError
    - page_image_url: 포맷 (/static/page_images/{doc_id}/{page:04d}.png)
    - pdf_url: raw_data_path 안의 경로 → /static/raw/... URL
    - pdf_url: raw_data_path 밖의 경로 → None

mock 정책:
    - fitz.open: 실 PyMuPDF 호출 없이 FakeDoc 으로 교체
    - settings.page_images_path / raw_data_path: tmp_path 기반 격리
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import app.infrastructure.core.config as _cfg
import pytest
from app.infrastructure.pdfimage import service as pdf_service

# ---------------------------------------------------------------------------
# 공통 헬퍼 — Settings 격리
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    """tmp_path 기반 page_images_path + raw_data_path 를 사용하는 Settings."""
    _cfg.get_settings.cache_clear()

    raw_path = tmp_path / "raw"
    page_images_path = tmp_path / "page_images"
    raw_path.mkdir(parents=True)
    page_images_path.mkdir(parents=True)

    monkeypatch.setenv("RAW_DATA_PATH", str(raw_path))
    monkeypatch.setenv("PAGE_IMAGES_PATH", str(page_images_path))
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CHROMA_DB_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")

    settings = _cfg.Settings(
        raw_data_path=raw_path,
        page_images_path=page_images_path,
        sqlite_db_path=tmp_path / "test.db",
        chroma_db_path=tmp_path / "chroma",
        openai_api_key="test-key-not-real",
    )

    monkeypatch.setattr("app.infrastructure.pdfimage.service.get_settings", lambda: settings)

    yield settings

    _cfg.get_settings.cache_clear()


# ---------------------------------------------------------------------------
# FakeDoc — fitz.open 대체
# ---------------------------------------------------------------------------


def _make_fake_doc(page_count: int = 5):
    """PyMuPDF Document stub."""
    fake_pix = MagicMock()
    fake_pix.save = MagicMock()

    fake_page = MagicMock()
    fake_page.get_pixmap = MagicMock(return_value=fake_pix)

    fake_doc = MagicMock()
    fake_doc.page_count = page_count
    fake_doc.load_page = MagicMock(return_value=fake_page)
    # context manager 지원
    fake_doc.__enter__ = MagicMock(return_value=fake_doc)
    fake_doc.__exit__ = MagicMock(return_value=False)

    return fake_doc, fake_page, fake_pix


# ===========================================================================
# render_page
# ===========================================================================


class TestRenderPage:
    """render_page 동작 검증."""

    def test_cache_hit_returns_existing_path_without_conversion(
        self, isolated_settings, tmp_path
    ):
        """캐시 파일이 이미 존재하면 fitz.open 없이 동일 경로 반환."""
        # Arrange: 캐시 파일 미리 생성
        doc_id = 1
        page_no = 3
        cache_dir = isolated_settings.page_images_path / str(doc_id)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{page_no:04d}.png"
        cache_file.write_bytes(b"fake-png-data")

        fake_pdf = tmp_path / "sample.pdf"
        fake_pdf.write_bytes(b"fake-pdf")

        with patch("app.infrastructure.pdfimage.service.fitz.open") as mock_fitz:
            # Act
            result = pdf_service.render_page(doc_id, page_no, fake_pdf)

        # Assert: fitz.open 호출 없음 + 동일 경로 반환
        mock_fitz.assert_not_called()
        assert result == cache_file
        assert result.exists()

    def test_cache_miss_calls_pix_save(self, isolated_settings, tmp_path):
        """캐시 없을 때 fitz.open + pix.save 가 호출된다."""
        # Arrange
        doc_id = 2
        page_no = 1
        fake_pdf = tmp_path / "doc.pdf"
        fake_pdf.write_bytes(b"fake-pdf-content")

        fake_doc, fake_page, fake_pix = _make_fake_doc(page_count=5)

        with patch("app.infrastructure.pdfimage.service.fitz.open", return_value=fake_doc):
            # Act
            pdf_service.render_page(doc_id, page_no, fake_pdf)

        # Assert: pix.save 가 출력 경로로 호출됨
        fake_pix.save.assert_called_once()
        call_args = fake_pix.save.call_args[0][0]
        assert f"{page_no:04d}.png" in call_args
        assert str(doc_id) in call_args

    def test_cache_miss_returns_correct_output_path(self, isolated_settings, tmp_path):
        """캐시 miss 시 반환 경로 = page_images_path/{doc_id}/{page:04d}.png."""
        doc_id = 3
        page_no = 2
        fake_pdf = tmp_path / "doc2.pdf"
        fake_pdf.write_bytes(b"content")

        fake_doc, _, _ = _make_fake_doc(page_count=10)

        with patch("app.infrastructure.pdfimage.service.fitz.open", return_value=fake_doc):
            result = pdf_service.render_page(doc_id, page_no, fake_pdf)

        expected = isolated_settings.page_images_path / str(doc_id) / f"{page_no:04d}.png"
        assert result == expected

    def test_pdf_not_found_raises_file_not_found_error(self, isolated_settings, tmp_path):
        """PDF 파일이 없으면 FileNotFoundError."""
        doc_id = 4
        page_no = 1
        missing_pdf = tmp_path / "nonexistent.pdf"

        with pytest.raises(FileNotFoundError):
            pdf_service.render_page(doc_id, page_no, missing_pdf)

    def test_page_no_zero_raises_value_error(self, isolated_settings, tmp_path):
        """page_no = 0 (1-indexed 경계 밖) → ValueError."""
        doc_id = 5
        page_no = 0
        fake_pdf = tmp_path / "doc3.pdf"
        fake_pdf.write_bytes(b"content")

        fake_doc, _, _ = _make_fake_doc(page_count=5)

        with patch("app.infrastructure.pdfimage.service.fitz.open", return_value=fake_doc), pytest.raises(ValueError, match="page_no=0"):
            pdf_service.render_page(doc_id, page_no, fake_pdf)

    def test_page_no_exceeds_page_count_raises_value_error(
        self, isolated_settings, tmp_path
    ):
        """page_no > doc.page_count → ValueError."""
        doc_id = 6
        page_count = 3
        page_no = page_count + 1  # 4
        fake_pdf = tmp_path / "doc4.pdf"
        fake_pdf.write_bytes(b"content")

        fake_doc, _, _ = _make_fake_doc(page_count=page_count)

        with patch("app.infrastructure.pdfimage.service.fitz.open", return_value=fake_doc), pytest.raises(ValueError, match=f"page_no={page_no}"):
            pdf_service.render_page(doc_id, page_no, fake_pdf)

    def test_load_page_called_with_zero_indexed_page(self, isolated_settings, tmp_path):
        """render_page(page_no=3) → doc.load_page(2) (0-indexed)."""
        doc_id = 7
        page_no = 3
        fake_pdf = tmp_path / "doc5.pdf"
        fake_pdf.write_bytes(b"content")

        fake_doc, fake_page, _ = _make_fake_doc(page_count=5)

        with patch("app.infrastructure.pdfimage.service.fitz.open", return_value=fake_doc):
            pdf_service.render_page(doc_id, page_no, fake_pdf)

        fake_doc.load_page.assert_called_once_with(page_no - 1)


# ===========================================================================
# page_image_url
# ===========================================================================


class TestPageImageUrl:
    """page_image_url 포맷 검증."""

    def test_url_format_with_zero_padded_page(self):
        """/static/page_images/{doc_id}/{page:04d}.png 형식."""
        url = pdf_service.page_image_url(document_id=1, page_no=3)
        assert url == "/static/page_images/1/0003.png"

    def test_url_format_large_doc_id(self):
        """doc_id 가 큰 값이어도 올바르게 포맷."""
        url = pdf_service.page_image_url(document_id=999, page_no=1)
        assert url == "/static/page_images/999/0001.png"

    def test_url_format_page_10_not_zero_padded_beyond_4_digits(self):
        """4자리 미만 페이지는 0-패딩, 4자리 이상은 그대로."""
        url_small = pdf_service.page_image_url(document_id=1, page_no=10)
        assert url_small == "/static/page_images/1/0010.png"

        url_large = pdf_service.page_image_url(document_id=1, page_no=10000)
        assert url_large == "/static/page_images/1/10000.png"

    def test_url_starts_with_static_page_images(self):
        """/static/page_images/ 로 시작한다."""
        url = pdf_service.page_image_url(document_id=42, page_no=7)
        assert url.startswith("/static/page_images/")


# ===========================================================================
# pdf_url
# ===========================================================================


class TestPdfUrl:
    """pdf_url raw_data_path 안/밖 경로 검증."""

    def test_path_inside_raw_data_returns_static_url(
        self, isolated_settings, tmp_path
    ):
        """raw_data_path 안의 PDF → /static/raw/... URL 반환."""
        # Arrange: raw_data_path 안에 파일 경로 생성 (실제 파일 불필요)
        raw_root = isolated_settings.raw_data_path
        file_path = raw_root / "hanwha" / "auto" / "terms.pdf"

        result = pdf_service.pdf_url(file_path)

        # Assert: URL 이 /static/raw/ 로 시작
        assert result is not None
        assert result.startswith("/static/raw/")
        assert "hanwha" in result
        assert "terms.pdf" in result

    def test_path_inside_raw_data_uses_posix_slash(self, isolated_settings, tmp_path):
        """Windows 경로도 URL 에서 슬래시 사용."""
        raw_root = isolated_settings.raw_data_path
        # Windows 구분자 여부와 무관하게 / 사용
        file_path = raw_root / "samsung" / "fire" / "summary.pdf"

        result = pdf_service.pdf_url(file_path)

        assert result is not None
        assert "\\" not in result  # Windows 백슬래시 없음

    def test_path_outside_raw_data_returns_none(self, isolated_settings, tmp_path):
        """raw_data_path 밖의 경로 → None."""
        outside_path = tmp_path / "external" / "other.pdf"

        result = pdf_service.pdf_url(outside_path)

        assert result is None

    def test_absolute_external_path_returns_none(self, isolated_settings):
        """/etc/passwd 같은 외부 절대 경로 → None."""
        result = pdf_service.pdf_url(Path("/etc/some_external_doc.pdf"))
        assert result is None

    def test_url_relative_part_matches_file_structure(
        self, isolated_settings, tmp_path
    ):
        """/static/raw/ 뒤에 raw_data_path 기준 상대 경로가 온다."""
        raw_root = isolated_settings.raw_data_path
        rel = "hanwha/auto/2026-01-01_present/terms.pdf"
        file_path = raw_root / rel

        result = pdf_service.pdf_url(file_path)

        assert result == f"/static/raw/{rel}"
