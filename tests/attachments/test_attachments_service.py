"""tests.attachments.test_attachments_service

app/attachments/service.py 단위 테스트.

테스트 대상:
    - save_bytes — 정상 / mime 거부 / 크기 초과 / sha256 정확
    - read_bytes — round trip / 미존재 raise
    - delete_attachment — 정상 / 미존재 False
    - cleanup_expired — TTL 초과 삭제 + 미초과 유지
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest
from app.domains.attachments import service
from app.infrastructure.core.exceptions import DomainError, StorageError


@pytest.fixture
def tmp_attachment_settings(tmp_path: Path, monkeypatch):
    """Settings 격리 — 임시 attachment_storage_path."""
    upload_dir = tmp_path / "uploads"
    monkeypatch.setenv("ATTACHMENT_STORAGE_PATH", str(upload_dir))
    monkeypatch.setenv("ATTACHMENT_TTL_HOURS", "24")
    monkeypatch.setenv("ATTACHMENT_MAX_SIZE_MB", "10")
    from app.infrastructure.core.config import get_settings

    get_settings.cache_clear()
    yield upload_dir
    get_settings.cache_clear()


class TestSaveBytes:
    def test_saves_jpeg_and_returns_meta(self, tmp_attachment_settings):
        content = b"fake jpeg bytes"
        meta = service.save_bytes("session-1", "scan.jpg", "image/jpeg", content)
        assert meta.session_id == "session-1"
        assert meta.size == len(content)
        assert meta.sha256 == hashlib.sha256(content).hexdigest()
        assert meta.mime_type == "image/jpeg"

    def test_rejects_disallowed_mime(self, tmp_attachment_settings):
        with pytest.raises(DomainError, match="허용되지 않은"):
            service.save_bytes("s", "x.txt", "text/plain", b"hi")

    def test_rejects_pdf_mime_after_w1_fix(self, tmp_attachment_settings):
        """W-1 보정: PDF 는 OpenAI Vision 직접 미지원 — 저장 단계에서 거부."""
        with pytest.raises(DomainError, match="허용되지 않은"):
            service.save_bytes("s", "x.pdf", "application/pdf", b"%PDF-1.4 fake")

    def test_rejects_oversize(self, tmp_attachment_settings, monkeypatch):
        monkeypatch.setenv("ATTACHMENT_MAX_SIZE_MB", "1")
        from app.infrastructure.core.config import get_settings

        get_settings.cache_clear()
        big = b"x" * (2 * 1024 * 1024)  # 2 MB > 1 MB 제한
        with pytest.raises(DomainError, match="크기 초과"):
            service.save_bytes("s", "x.png", "image/png", big)


class TestReadBytes:
    def test_round_trip(self, tmp_attachment_settings):
        content = b"hello bytes"
        meta = service.save_bytes("s", "x.png", "image/png", content)
        result = service.read_bytes("s", meta.id)
        assert result == content

    def test_missing_raises(self, tmp_attachment_settings):
        with pytest.raises(StorageError, match="첨부 미존재"):
            service.read_bytes("nosuch", "nonexistent")


class TestDeleteAttachment:
    def test_delete_existing_returns_true(self, tmp_attachment_settings):
        meta = service.save_bytes("s", "x.png", "image/png", b"abc")
        assert service.delete_attachment("s", meta.id) is True
        with pytest.raises(StorageError):
            service.read_bytes("s", meta.id)

    def test_delete_missing_returns_false(self, tmp_attachment_settings):
        assert service.delete_attachment("nosuch", "nonexistent") is False


class TestCleanupExpired:
    def test_cleanup_removes_old_files(self, tmp_attachment_settings, monkeypatch):
        monkeypatch.setenv("ATTACHMENT_TTL_HOURS", "1")  # 1 시간
        from app.infrastructure.core.config import get_settings

        get_settings.cache_clear()

        meta = service.save_bytes("s", "x.png", "image/png", b"old")
        # 파일 mtime 을 2시간 전으로 조작
        upload_root = tmp_attachment_settings
        for f in (upload_root / "s").glob(f"{meta.id}.*"):
            old_time = time.time() - 2 * 3600
            import os

            os.utime(f, (old_time, old_time))

        deleted = service.cleanup_expired()
        assert deleted == 1

    def test_cleanup_keeps_fresh_files(self, tmp_attachment_settings):
        service.save_bytes("s", "x.png", "image/png", b"fresh")
        deleted = service.cleanup_expired()
        assert deleted == 0

    def test_cleanup_disabled_when_ttl_zero(self, tmp_attachment_settings, monkeypatch):
        monkeypatch.setenv("ATTACHMENT_TTL_HOURS", "0")
        # ge=1 validator 때문에 0 은 불가 — 검증
        from app.infrastructure.core.config import get_settings
        from pydantic import ValidationError

        get_settings.cache_clear()
        with pytest.raises(ValidationError):
            get_settings()
