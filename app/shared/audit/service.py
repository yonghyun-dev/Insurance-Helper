"""app.shared.audit.service

파일 경로: app/audit/service.py
목적: 감사 로그 생성·완료·실패 기록 — `post_message` 흐름과 try/finally 결합.
주요 함수:
    - begin(session_id, masked_input) -> AuditContext: 응답 시작 시 호출
    - complete(ctx, ...): 정상 응답 시 호출
    - fail(ctx, error): 예외 발생 시 호출
주요 의존성: app.infrastructure.core.database, app.shared.audit.models
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from prometheus_client import Counter
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.core.config import get_settings
from app.infrastructure.core.database import session_scope
from app.shared.audit.models import AuditLog

logger = logging.getLogger(__name__)

# Sprint 8 reviewer W-3 보정: audit insert 실패 모니터링.
# /metrics 엔드포인트에서 audit_insert_failures_total 카운터로 노출.
# 운영자가 Grafana 알람으로 임계값 초과 시 즉시 인지 가능.
_AUDIT_INSERT_FAILURES = Counter(
    "audit_insert_failures_total",
    "audit_log INSERT 실패 누적 횟수 (응답은 정상 반환, audit 만 누락)",
)


@dataclass
class AuditContext:
    """audit 생애주기 컨텍스트. post_message 안에서 try/finally 로 사용."""

    response_id: str
    session_id: str | None = None
    turn: int | None = None
    masked_user_input: str | None = None
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    external_api_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # Sprint 14.1 (REQ-10) — 로그인 사용자 추적용. 비로그인 시 None.
    user_id: int | None = None


def begin(
    *,
    session_id: str | None = None,
    turn: int | None = None,
    raw_user_input: str | None = None,
    user_id: int | None = None,
) -> AuditContext:
    """응답 시작 시 호출. response_id 발급 + 컨텍스트 반환.

    Sprint 8 reviewer W-1 보정: 호출자가 mask_pii 호출을 빠뜨릴 위험 차단 — `raw_user_input` 받아
    내부에서 `mask_pii()` 직접 적용 후 컨텍스트에 저장. 호출자는 원문 그대로 전달.

    Sprint 14.1 (REQ-10): 로그인 사용자 user_id keyword 추가. 비로그인 시 None — audit_log.user_id NULL.

    DB 미기록 — `complete`/`fail` 에서 한번에 INSERT (트랜잭션 1회).
    """
    from app.shared.security.pii import mask_pii

    return AuditContext(
        response_id=uuid4().hex,
        session_id=session_id,
        turn=turn,
        masked_user_input=mask_pii(raw_user_input) if raw_user_input else None,
        user_id=user_id,
    )


def _mask_trace(obj: Any) -> Any:
    """tool_calls / external_api_calls trace 의 모든 문자열 값에 PII 마스킹 재귀 적용.

    args/result 에 사용자 평문(진단명·연락처 등)이 섞일 수 있어 평문 저장을 차단한다.
    숫자/불리언 등 비문자열은 그대로 둔다.
    """
    from app.shared.security.pii import mask_pii

    if isinstance(obj, str):
        return mask_pii(obj)
    if isinstance(obj, dict):
        return {k: _mask_trace(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask_trace(v) for v in obj]
    return obj


def complete(
    ctx: AuditContext,
    *,
    assistant_response_type: str,
    assistant_message: str | None = None,
    confidence: str | None = None,
) -> None:
    """정상 응답 직전 호출. AuditLog row INSERT.

    Settings.audit_enabled 가 false 면 no-op (테스트 환경).
    """
    if not get_settings().audit_enabled:
        return
    msg_hash = (
        hashlib.sha256(assistant_message.encode("utf-8")).hexdigest()
        if assistant_message
        else None
    )
    _insert(
        AuditLog(
            response_id=ctx.response_id,
            session_id=ctx.session_id,
            turn=ctx.turn,
            masked_user_input=ctx.masked_user_input,
            llm_calls=ctx.llm_calls or None,
            retrieved_chunk_ids=ctx.retrieved_chunk_ids or None,
            external_api_calls=_mask_trace(ctx.external_api_calls) or None,
            tool_calls=_mask_trace(ctx.tool_calls) or None,
            assistant_response_type=assistant_response_type,
            assistant_message_hash=msg_hash,
            confidence=confidence,
            user_id=ctx.user_id,
        )
    )


def fail(ctx: AuditContext, *, error: str) -> None:
    """예외 발생 시 호출. error 필드에 마스킹된 메시지 기록."""
    if not get_settings().audit_enabled:
        return
    _insert(
        AuditLog(
            response_id=ctx.response_id,
            session_id=ctx.session_id,
            turn=ctx.turn,
            masked_user_input=ctx.masked_user_input,
            llm_calls=ctx.llm_calls or None,
            retrieved_chunk_ids=ctx.retrieved_chunk_ids or None,
            external_api_calls=_mask_trace(ctx.external_api_calls) or None,
            tool_calls=_mask_trace(ctx.tool_calls) or None,
            error=error,
            user_id=ctx.user_id,
        )
    )


def _insert(row: AuditLog) -> None:
    """audit row 1건 INSERT. DB 실패는 logger.warning + prometheus counter — 핵심 응답을 막지 않음.

    Sprint 8 reviewer W-3 보정: prometheus counter 추가로 운영 모니터링 가능.
    """
    try:
        with session_scope() as session:
            session.add(row)
    except SQLAlchemyError as exc:
        logger.warning("audit insert 실패 (응답은 계속): %s", exc)
        _AUDIT_INSERT_FAILURES.inc()
