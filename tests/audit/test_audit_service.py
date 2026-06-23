"""tests.audit.test_audit_service

app/audit/service.py 단위 테스트.

테스트 대상:
    - begin(): response_id UUID4 hex 생성 + AuditContext 필드 설정 (DB 미접근)
    - complete(): AuditLog INSERT + assistant_message_hash sha256 검증
    - complete(): Settings.audit_enabled=False → no-op
    - fail(): error 필드 채움 + AuditLog INSERT
    - fail(): Settings.audit_enabled=False → no-op
    - _insert(): DB 실패 시 logger.warning 만 (응답 흐름 안 막음)

mock 정책:
    - get_settings() → monkeypatch 로 FakeSettings 주입
    - session_scope() → monkeypatch 로 in-memory SQLite 세션 주입
    - DB 실패 테스트 → session_scope 에서 SQLAlchemyError 발생시킴
"""

from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from app.infrastructure.core.database import Base
from app.shared.audit.models import AuditLog
from app.shared.audit.service import AuditContext, begin, complete, fail
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

# ===========================================================================
# 픽스처
# ===========================================================================


@pytest.fixture()
def audit_db():
    """in-memory SQLite — AuditLog 테이블 포함."""
    engine = create_engine("sqlite:///:memory:", future=True, echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


class FakeSettings:
    """audit_enabled 제어용 더미 설정."""

    def __init__(self, audit_enabled: bool = True):
        self.audit_enabled = audit_enabled


def make_session_scope(factory):
    """in-memory SQLite factory 를 session_scope 컨텍스트 매니저로 래핑."""

    @contextmanager
    def _scope():
        sess = factory()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    return _scope


# ===========================================================================
# begin() — AuditContext 생성
# ===========================================================================


class TestBegin:
    """begin() 은 DB 접근 없이 AuditContext 를 반환한다."""

    def test_begin_returns_audit_context(self):
        # begin() 은 raw_user_input 을 받아 내부에서 mask_pii 적용
        ctx = begin(session_id="sess-001", turn=1, raw_user_input="안녕하세요")
        assert isinstance(ctx, AuditContext)

    def test_begin_response_id_is_uuid4_hex(self):
        """response_id 는 UUID4 hex (32자 소문자 16진수)."""
        ctx = begin()
        # UUID4 hex 는 32자
        assert len(ctx.response_id) == 32
        assert ctx.response_id == ctx.response_id.lower()
        # 16진수 문자만 포함
        int(ctx.response_id, 16)  # ValueError 없이 통과

    def test_begin_response_id_is_unique_each_call(self):
        """호출할 때마다 다른 response_id 를 생성한다."""
        ctx1 = begin()
        ctx2 = begin()
        assert ctx1.response_id != ctx2.response_id

    def test_begin_stores_session_id(self):
        ctx = begin(session_id="sess-abc")
        assert ctx.session_id == "sess-abc"

    def test_begin_stores_turn(self):
        ctx = begin(turn=3)
        assert ctx.turn == 3

    def test_begin_stores_masked_user_input(self):
        """raw_user_input 은 begin() 내부에서 mask_pii 적용 후 ctx.masked_user_input 에 저장."""
        # PII 없는 일반 문자열은 그대로 저장됨
        ctx = begin(raw_user_input="보험금 청구 문의입니다.")
        assert ctx.masked_user_input == "보험금 청구 문의입니다."

    def test_begin_masks_pii_in_raw_user_input(self):
        """raw_user_input 에 PII 포함 시 masked_user_input 에 마스킹된 값이 저장."""
        ctx = begin(raw_user_input="연락처: 010-1234-5678 입니다.")
        assert "[PHONE]" in ctx.masked_user_input
        assert "010-1234-5678" not in ctx.masked_user_input

    def test_begin_with_no_args_sets_defaults(self):
        """파라미터 없이 호출하면 optional 필드가 None."""
        ctx = begin()
        assert ctx.session_id is None
        assert ctx.turn is None
        assert ctx.masked_user_input is None

    def test_begin_initializes_empty_lists(self):
        """list 필드들은 빈 리스트로 초기화된다."""
        ctx = begin()
        assert ctx.llm_calls == []
        assert ctx.retrieved_chunk_ids == []
        assert ctx.external_api_calls == []
        assert ctx.tool_calls == []

    def test_begin_does_not_access_db(self, monkeypatch):
        """begin() 은 session_scope 를 호출하지 않는다."""
        import app.shared.audit.service as svc

        called = []

        @contextmanager
        def fake_scope():
            called.append(True)
            yield MagicMock()

        monkeypatch.setattr(svc, "session_scope", fake_scope)
        begin(session_id="sess-001")
        assert called == []  # DB 미접근


# ===========================================================================
# complete() — 정상 INSERT
# ===========================================================================


class TestComplete:
    """complete() 는 AuditLog row 를 INSERT 한다."""

    def test_complete_inserts_row(self, monkeypatch, audit_db):
        """complete() 호출 후 AuditLog row 가 DB 에 저장된다."""
        import app.shared.audit.service as svc

        monkeypatch.setattr(svc, "get_settings", lambda: FakeSettings(audit_enabled=True))
        monkeypatch.setattr(svc, "session_scope", make_session_scope(audit_db))

        ctx = begin(session_id="sess-complete", turn=1)
        complete(
            ctx,
            assistant_response_type="assessment",
            assistant_message="보험금 지급 가능합니다.",
            confidence="full",
        )

        # DB 에서 직접 조회
        sess = audit_db()
        row = sess.get(AuditLog, ctx.response_id)
        sess.close()

        assert row is not None
        assert row.session_id == "sess-complete"
        assert row.turn == 1
        assert row.assistant_response_type == "assessment"
        assert row.confidence == "full"

    def test_complete_stores_sha256_hash(self, monkeypatch, audit_db):
        """assistant_message_hash 가 sha256 hex 와 일치한다."""
        import app.shared.audit.service as svc

        monkeypatch.setattr(svc, "get_settings", lambda: FakeSettings(True))
        monkeypatch.setattr(svc, "session_scope", make_session_scope(audit_db))

        message = "청구 불가 판정입니다."
        expected_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
        ctx = begin()
        complete(ctx, assistant_response_type="assessment", assistant_message=message)

        sess = audit_db()
        row = sess.get(AuditLog, ctx.response_id)
        sess.close()

        assert row.assistant_message_hash == expected_hash
        assert len(row.assistant_message_hash) == 64

    def test_complete_with_none_message_hash_is_none(self, monkeypatch, audit_db):
        """assistant_message=None 이면 hash 도 None."""
        import app.shared.audit.service as svc

        monkeypatch.setattr(svc, "get_settings", lambda: FakeSettings(True))
        monkeypatch.setattr(svc, "session_scope", make_session_scope(audit_db))

        ctx = begin()
        complete(ctx, assistant_response_type="ask", assistant_message=None)

        sess = audit_db()
        row = sess.get(AuditLog, ctx.response_id)
        sess.close()

        assert row.assistant_message_hash is None

    def test_complete_noop_when_audit_disabled(self, monkeypatch, audit_db):
        """audit_enabled=False 면 DB 에 row 가 삽입되지 않는다."""
        import app.shared.audit.service as svc

        monkeypatch.setattr(svc, "get_settings", lambda: FakeSettings(False))

        called = []

        @contextmanager
        def spy_scope():
            called.append(True)
            yield MagicMock()

        monkeypatch.setattr(svc, "session_scope", spy_scope)
        ctx = begin()
        complete(ctx, assistant_response_type="ask")

        assert called == []  # DB 미접근

    def test_complete_stores_retrieved_chunk_ids(self, monkeypatch, audit_db):
        """ctx 에 retrieved_chunk_ids 가 있으면 row 에 저장된다."""
        import app.shared.audit.service as svc

        monkeypatch.setattr(svc, "get_settings", lambda: FakeSettings(True))
        monkeypatch.setattr(svc, "session_scope", make_session_scope(audit_db))

        ctx = begin()
        ctx.retrieved_chunk_ids = ["chunk-001", "chunk-002"]
        complete(ctx, assistant_response_type="assessment")

        sess = audit_db()
        row = sess.get(AuditLog, ctx.response_id)
        sess.close()

        assert row.retrieved_chunk_ids == ["chunk-001", "chunk-002"]


# ===========================================================================
# fail() — 에러 기록
# ===========================================================================


class TestFail:
    """fail() 은 error 필드를 채운 AuditLog row 를 INSERT 한다."""

    def test_fail_inserts_row_with_error(self, monkeypatch, audit_db):
        """fail() 호출 후 error 필드가 채워진 row 가 저장된다."""
        import app.shared.audit.service as svc

        monkeypatch.setattr(svc, "get_settings", lambda: FakeSettings(True))
        monkeypatch.setattr(svc, "session_scope", make_session_scope(audit_db))

        ctx = begin(session_id="sess-fail", turn=2)
        fail(ctx, error="LLMError: OpenAI 연결 실패")

        sess = audit_db()
        row = sess.get(AuditLog, ctx.response_id)
        sess.close()

        assert row is not None
        assert row.error == "LLMError: OpenAI 연결 실패"
        assert row.session_id == "sess-fail"
        assert row.turn == 2

    def test_fail_noop_when_audit_disabled(self, monkeypatch):
        """audit_enabled=False 면 fail() 도 no-op."""
        import app.shared.audit.service as svc

        monkeypatch.setattr(svc, "get_settings", lambda: FakeSettings(False))

        called = []

        @contextmanager
        def spy_scope():
            called.append(True)
            yield MagicMock()

        monkeypatch.setattr(svc, "session_scope", spy_scope)
        ctx = begin()
        fail(ctx, error="테스트 오류")

        assert called == []

    def test_fail_has_no_assistant_response_type(self, monkeypatch, audit_db):
        """fail() 로 저장된 row 는 assistant_response_type 이 None."""
        import app.shared.audit.service as svc

        monkeypatch.setattr(svc, "get_settings", lambda: FakeSettings(True))
        monkeypatch.setattr(svc, "session_scope", make_session_scope(audit_db))

        ctx = begin()
        fail(ctx, error="timeout")

        sess = audit_db()
        row = sess.get(AuditLog, ctx.response_id)
        sess.close()

        assert row.assistant_response_type is None
        assert row.error == "timeout"


# ===========================================================================
# _insert() — DB 실패 → warning 만 (응답 흐름 차단 없음)
# ===========================================================================


class TestInsertDbFailure:
    """DB 실패 시 logger.warning 만 발생하고 예외를 전파하지 않는다."""

    def test_db_failure_does_not_raise(self, monkeypatch):
        """session_scope 에서 SQLAlchemyError 발생 시 _insert 는 예외를 삼킨다."""
        import app.shared.audit.service as svc

        monkeypatch.setattr(svc, "get_settings", lambda: FakeSettings(True))

        def failing_scope():
            """SQLAlchemyError 를 즉시 발생시키는 컨텍스트 매니저."""
            raise SQLAlchemyError("DB 연결 실패")

        # contextmanager 대신 __enter__ / __exit__ 구현
        class FailingCtx:
            def __enter__(self):
                raise SQLAlchemyError("DB 연결 실패")

            def __exit__(self, *args):
                return False

        monkeypatch.setattr(svc, "session_scope", FailingCtx)

        ctx = begin()
        # complete() 내부에서 _insert() 호출 — 예외가 전파되지 않아야 한다
        complete(ctx, assistant_response_type="assessment")  # 예외 없음

    def test_db_failure_logs_warning(self, monkeypatch, caplog):
        """DB 실패 시 logger.warning 이 호출된다."""
        import app.shared.audit.service as svc

        monkeypatch.setattr(svc, "get_settings", lambda: FakeSettings(True))

        class FailingCtx:
            def __enter__(self):
                raise SQLAlchemyError("connection error")

            def __exit__(self, *args):
                return False

        monkeypatch.setattr(svc, "session_scope", FailingCtx)

        ctx = begin()
        with caplog.at_level(logging.WARNING, logger="app.shared.audit.service"):
            fail(ctx, error="테스트")

        assert any("audit insert 실패" in record.message for record in caplog.records)
