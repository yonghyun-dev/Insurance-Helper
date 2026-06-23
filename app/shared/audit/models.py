"""app.shared.audit.models

파일 경로: app/audit/models.py
목적: 감사 로그 SQLAlchemy 모델 — 모든 응답에 대해 1 row.
주요 객체:
    - AuditLog: response_id PK + LLM/RAG/외부 API trace 영구 보존
주요 의존성: sqlalchemy

설계 참고:
    - docs/design/tech-decisions.md § Sprint 8~11 결정 2 (감사 로그)
    - docs/design/agent-architecture.md § 4 (운영 흐름)
    - 보존 기간 7년 ([확인 필요] 법무) — schema 단계에서는 제약 없음
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.core.database import Base


class AuditLog(Base):
    """단일 응답에 대한 감사 로그.

    PostgreSQL 환경에서는 JSON 컬럼이 JSONB 로 자동 매핑되므로 그대로 사용 가능.
    SQLite 환경에서도 JSON 컬럼이 TEXT 로 동작 — 회귀 0.

    Sprint 9~10 에서 `tool_calls` / `external_api_calls` 가 채워짐. Sprint 8 은 골격만.
    """

    __tablename__ = "audit_log"

    response_id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID4 hex
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    turn: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    masked_user_input: Mapped[str | None] = mapped_column(Text)
    llm_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)  # Sprint 9+ 확장
    retrieved_chunk_ids: Mapped[list[str] | None] = mapped_column(JSON)
    external_api_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)  # Sprint 9+
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)  # Sprint 11 ReAct
    assistant_response_type: Mapped[str | None] = mapped_column(String(16))  # ask | assessment
    assistant_message_hash: Mapped[str | None] = mapped_column(String(64))  # sha256
    confidence: Mapped[str | None] = mapped_column(String(8))  # partial | full
    error: Mapped[str | None] = mapped_column(Text)  # 실패 시 예외 메시지 (PII 마스킹 후)
    # Sprint 14 (REQ-10): 로그인 사용자 추적용 nullable FK. Alembic c2d3e4f5a6b7 와 동기화.
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
