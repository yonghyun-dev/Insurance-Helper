"""tests.audit.test_audit_models

app/audit/models.py 단위 테스트.

테스트 대상:
    - AuditLog 필수/optional 필드 검증
    - 인덱스 컬럼 확인
    - JSON 컬럼 round-trip (SQLite in-memory)
    - response_id PK 설정

mock 정책:
    - 기존 conftest.py 의 in-memory SQLite 엔진 픽스처 재사용
    - 실제 DB 호출 (SQLite in-memory) — 모델 동작 직접 검증
"""

from __future__ import annotations

import hashlib

import pytest
from app.infrastructure.core.database import Base
from app.shared.audit.models import AuditLog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ===========================================================================
# DB 픽스처 — AuditLog 전용 in-memory SQLite
# ===========================================================================


@pytest.fixture()
def audit_engine():
    """AuditLog 테이블 포함 in-memory SQLite 엔진."""
    engine = create_engine("sqlite:///:memory:", future=True, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def audit_session(audit_engine):
    """AuditLog 테스트용 세션."""
    factory = sessionmaker(bind=audit_engine, expire_on_commit=False, future=True)
    sess = factory()
    yield sess
    sess.rollback()
    sess.close()


# ===========================================================================
# AuditLog — 필수 필드 검증
# ===========================================================================


class TestAuditLogSchema:
    """AuditLog 모델 스키마 검증."""

    def test_table_name_is_audit_log(self):
        assert AuditLog.__tablename__ == "audit_log"

    def test_response_id_is_primary_key(self):
        # SQLAlchemy mapper inspect
        mapper = AuditLog.__mapper__
        pk_columns = [col.name for col in mapper.primary_key]
        assert "response_id" in pk_columns

    def test_session_id_is_indexed(self):
        """session_id 컬럼에 인덱스가 있다."""
        col = AuditLog.__table__.c["session_id"]
        # 인덱스 참여 여부 확인 (index=True 로 선언됨)
        table_indexes = AuditLog.__table__.indexes
        indexed_cols = set()
        for idx in table_indexes:
            for col in idx.columns:
                indexed_cols.add(col.name)
        assert "session_id" in indexed_cols

    def test_created_at_is_indexed(self):
        """created_at 컬럼에 인덱스가 있다."""
        table_indexes = AuditLog.__table__.indexes
        indexed_cols = set()
        for idx in table_indexes:
            for col in idx.columns:
                indexed_cols.add(col.name)
        assert "created_at" in indexed_cols

    def test_optional_fields_default_to_none(self):
        """optional 필드들은 기본값 None."""
        row = AuditLog(response_id="abc123")
        assert row.session_id is None
        assert row.turn is None
        assert row.masked_user_input is None
        assert row.llm_calls is None
        assert row.retrieved_chunk_ids is None
        assert row.external_api_calls is None
        assert row.tool_calls is None
        assert row.assistant_response_type is None
        assert row.assistant_message_hash is None
        assert row.confidence is None
        assert row.error is None


# ===========================================================================
# AuditLog — INSERT / SELECT (round-trip)
# ===========================================================================


class TestAuditLogRoundTrip:
    """SQLite in-memory DB 에서 INSERT 후 SELECT 로 round-trip 검증."""

    def test_insert_minimal_row(self, audit_session):
        """response_id 만으로 INSERT 가능하다."""
        # Arrange
        row = AuditLog(response_id="test-response-id-001")
        # Act
        audit_session.add(row)
        audit_session.commit()
        # Assert
        fetched = audit_session.get(AuditLog, "test-response-id-001")
        assert fetched is not None
        assert fetched.response_id == "test-response-id-001"

    def test_insert_full_row(self, audit_session):
        """모든 필드를 채운 AuditLog row INSERT 가능."""
        # Arrange
        msg_hash = hashlib.sha256("보험금 지급 가능합니다.".encode()).hexdigest()
        row = AuditLog(
            response_id="test-response-full-001",
            session_id="sess-abc",
            turn=2,
            masked_user_input="자동차보험 청구 [PHONE] 입니다.",
            llm_calls=[{"model": "gpt-4o-mini", "tokens": 150}],
            retrieved_chunk_ids=["chunk-01", "chunk-02"],
            external_api_calls=None,
            tool_calls=None,
            assistant_response_type="assessment",
            assistant_message_hash=msg_hash,
            confidence="full",
            error=None,
        )
        # Act
        audit_session.add(row)
        audit_session.commit()
        # Assert
        fetched = audit_session.get(AuditLog, "test-response-full-001")
        assert fetched.session_id == "sess-abc"
        assert fetched.turn == 2
        assert fetched.assistant_response_type == "assessment"
        assert fetched.confidence == "full"
        assert fetched.assistant_message_hash == msg_hash

    def test_json_column_round_trip_llm_calls(self, audit_session):
        """llm_calls JSON 컬럼이 INSERT → SELECT 후 동일 구조다."""
        # Arrange
        llm_data = [{"model": "gpt-4o-mini", "tokens": 200, "cost": 0.001}]
        row = AuditLog(
            response_id="json-test-llm",
            llm_calls=llm_data,
        )
        # Act
        audit_session.add(row)
        audit_session.commit()
        # Assert
        fetched = audit_session.get(AuditLog, "json-test-llm")
        assert fetched.llm_calls == llm_data
        assert fetched.llm_calls[0]["model"] == "gpt-4o-mini"

    def test_json_column_round_trip_retrieved_chunk_ids(self, audit_session):
        """retrieved_chunk_ids JSON 컬럼 round-trip."""
        # Arrange
        chunk_ids = ["chunk-001", "chunk-002", "chunk-003"]
        row = AuditLog(
            response_id="json-test-chunks",
            retrieved_chunk_ids=chunk_ids,
        )
        # Act
        audit_session.add(row)
        audit_session.commit()
        # Assert
        fetched = audit_session.get(AuditLog, "json-test-chunks")
        assert fetched.retrieved_chunk_ids == chunk_ids
        assert len(fetched.retrieved_chunk_ids) == 3

    def test_error_field_stores_text(self, audit_session):
        """error 필드에 마스킹된 오류 메시지를 저장한다."""
        # Arrange
        row = AuditLog(
            response_id="error-test-001",
            error="LLMError: OpenAI 서비스 연결 실패",
        )
        # Act
        audit_session.add(row)
        audit_session.commit()
        # Assert
        fetched = audit_session.get(AuditLog, "error-test-001")
        assert "LLMError" in fetched.error

    def test_response_id_uniqueness_constraint(self, audit_session):
        """동일 response_id 로 두 번 INSERT 시 PK 제약 위반."""
        from sqlalchemy.exc import IntegrityError

        # Arrange
        row1 = AuditLog(response_id="dup-id-001")
        row2 = AuditLog(response_id="dup-id-001")
        audit_session.add(row1)
        audit_session.commit()
        # Act / Assert
        audit_session.add(row2)
        with pytest.raises(IntegrityError):
            audit_session.commit()

    def test_assistant_message_hash_is_sha256_hex(self, audit_session):
        """assistant_message_hash 는 sha256 hex(64자) 저장."""
        # Arrange
        message = "청구 가능합니다."
        expected_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
        row = AuditLog(
            response_id="hash-test-001",
            assistant_message_hash=expected_hash,
        )
        # Act
        audit_session.add(row)
        audit_session.commit()
        # Assert
        fetched = audit_session.get(AuditLog, "hash-test-001")
        assert len(fetched.assistant_message_hash) == 64
        assert fetched.assistant_message_hash == expected_hash
