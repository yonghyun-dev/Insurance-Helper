"""app.domains.attachments.schemas

첨부 파일 메타 + 응답 모델.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentMeta(BaseModel):
    """저장된 첨부 파일 메타 (DB 미저장 — 파일시스템 + audit_log 만)."""

    id: str = Field(..., description="UUID hex")
    session_id: str
    sha256: str = Field(..., min_length=64, max_length=64)
    size: int = Field(..., ge=0, description="바이트")
    mime_type: str
    filename: str = Field(..., description="원본 파일명")
    created_at: datetime
    expires_at: datetime
