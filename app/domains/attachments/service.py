"""app.domains.attachments.service

첨부 파일 저장/조회/삭제 + TTL cleanup.

설계 (tech-decisions § Sprint 15):
    - 저장: `data/uploads/{session_id}/{uuid}.{ext}`
    - DB 미저장 — 파일시스템 + audit_log hash 만
    - TTL: settings.attachment_ttl_hours (기본 24h)
    - cleanup: 1시간 주기 APScheduler (app/main.py startup)
"""

from __future__ import annotations

import contextlib
import hashlib
import mimetypes
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domains.attachments.schemas import AttachmentMeta
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.exceptions import DomainError, StorageError
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

_ALLOWED_MIME = {
    "image/jpeg",
    "image/png",
    "image/webp",
    # PDF 는 OpenAI Vision 직접 미지원 — W-1 (reviewer 10) 보정으로 제거.
    # 향후 PyMuPDF 로 PDF → 이미지 변환 후 OCR 활성 시 재허용.
}


def _ext_for(mime_type: str, filename: str) -> str:
    """mime + 파일명 기반 확장자 결정."""
    ext = Path(filename).suffix.lower()
    if ext:
        return ext
    guessed = mimetypes.guess_extension(mime_type)
    return guessed or ".bin"


def save_bytes(
    session_id: str,
    filename: str,
    mime_type: str,
    content: bytes,
) -> AttachmentMeta:
    """첨부 파일 저장 + 메타 반환.

    Raises:
        DomainError: mime type 미허용 / 크기 초과
        StorageError: 파일시스템 쓰기 실패
    """
    settings = get_settings()
    if mime_type not in _ALLOWED_MIME:
        raise DomainError(
            f"허용되지 않은 파일 형식: {mime_type}. 허용: {sorted(_ALLOWED_MIME)}"
        )
    max_bytes = settings.attachment_max_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise DomainError(
            f"파일 크기 초과: {len(content)} bytes > {max_bytes} bytes"
        )

    base = settings.attachment_storage_path / session_id
    base.mkdir(parents=True, exist_ok=True)

    att_id = uuid.uuid4().hex
    ext = _ext_for(mime_type, filename)
    target = base / f"{att_id}{ext}"

    try:
        target.write_bytes(content)
    except OSError as exc:
        raise StorageError(f"첨부 파일 저장 실패: {exc}") from exc

    now = datetime.now(UTC)
    meta = AttachmentMeta(
        id=att_id,
        session_id=session_id,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        mime_type=mime_type,
        filename=filename,
        created_at=now,
        expires_at=now + timedelta(hours=settings.attachment_ttl_hours),
    )
    logger.info(
        "첨부 저장: session=%s id=%s size=%d mime=%s",
        session_id, att_id, len(content), mime_type,
    )
    return meta


def read_bytes(session_id: str, attachment_id: str) -> bytes:
    """저장된 첨부 파일 본문 읽기.

    Raises:
        StorageError: 미존재 또는 읽기 실패
    """
    base = get_settings().attachment_storage_path / session_id
    for path in base.glob(f"{attachment_id}.*"):
        return path.read_bytes()
    raise StorageError(f"첨부 미존재: session={session_id} id={attachment_id}")


def delete_attachment(session_id: str, attachment_id: str) -> bool:
    """첨부 파일 삭제. 미존재면 False."""
    base = get_settings().attachment_storage_path / session_id
    deleted = False
    for path in base.glob(f"{attachment_id}.*"):
        try:
            path.unlink()
            deleted = True
        except OSError as exc:
            logger.warning("첨부 삭제 실패: %s (%s)", path, exc)
    return deleted


def cleanup_expired() -> int:
    """TTL 초과 첨부 파일 일괄 삭제. 삭제된 파일 수 반환.

    `attachment_ttl_hours` 시간 이상 된 모든 파일 (모든 session_id) 삭제.
    """
    settings = get_settings()
    if settings.attachment_ttl_hours <= 0:
        return 0
    root = settings.attachment_storage_path
    if not root.exists():
        return 0

    threshold = datetime.now(UTC).timestamp() - settings.attachment_ttl_hours * 3600
    deleted_count = 0

    for session_dir in root.iterdir():
        if not session_dir.is_dir():
            continue
        for f in session_dir.iterdir():
            try:
                if f.stat().st_mtime < threshold:
                    f.unlink()
                    deleted_count += 1
            except OSError as exc:
                logger.warning("cleanup 실패: %s (%s)", f, exc)
        # 빈 디렉토리 정리 (비어있지 않으면 OSError — OK)
        with contextlib.suppress(OSError):
            session_dir.rmdir()

    if deleted_count:
        logger.info("첨부 TTL cleanup: %d 파일 삭제 (TTL=%dh)", deleted_count, settings.attachment_ttl_hours)
    return deleted_count
