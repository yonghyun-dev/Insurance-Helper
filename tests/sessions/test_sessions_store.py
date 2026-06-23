"""tests.sessions.test_sessions_store

app/sessions/store.py 단위 테스트.

테스트 대상:
    - SessionStore.create: 세션 생성 + uuid v4 형식 + 기본값
    - SessionStore.get: 정상 조회 / 없는 ID / 만료 → None + 자동 삭제
    - SessionStore.touch: last_activity_at 갱신 / status 변경
    - SessionStore.delete: 존재 시 True / 없는 ID False
    - SessionStore.count: 빈 스토어 / 생성 후 / 만료 포함
    - SessionStore.purge_expired: 만료 세션 일괄 제거
    - Session.is_expired: TTL 경과 / 미경과 분기
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domains.sessions.schemas import Session, SlotState
from app.domains.sessions.store import SessionStore

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _past(seconds: int) -> datetime:
    """현재보다 seconds 초 전 UTC datetime."""
    return _utcnow() - timedelta(seconds=seconds)


# ===========================================================================
# Session.is_expired
# ===========================================================================


class TestSessionIsExpired:
    """Session.is_expired TTL 경과 분기 검증."""

    def _make_session(self, last_activity_at: datetime) -> Session:
        now = _utcnow()
        return Session(
            session_id="test-id",
            created_at=now,
            last_activity_at=last_activity_at,
            status="gathering",
        )

    def test_not_expired_when_within_ttl(self):
        # 마지막 활동 10초 전, TTL 1800초 → 만료 아님
        session = self._make_session(_past(10))
        assert session.is_expired(_utcnow(), ttl_seconds=1800) is False

    def test_expired_when_exceeds_ttl(self):
        # 마지막 활동 1801초 전, TTL 1800초 → 만료
        session = self._make_session(_past(1801))
        assert session.is_expired(_utcnow(), ttl_seconds=1800) is True

    def test_exactly_at_ttl_boundary_not_expired(self):
        # 정확히 TTL 초 전 → 경과 아님 (> 조건이므로 경계값은 유효)
        # 단일 고정 시각 기준 — _utcnow() 를 두 번 부르면 경과가 1800 을 미세 초과해 flaky.
        now = _utcnow()
        session = self._make_session(now - timedelta(seconds=1800))
        # total_seconds = 1800.0 → is_expired 조건 > ttl_seconds → False
        assert session.is_expired(now, ttl_seconds=1800) is False

    def test_one_second_over_ttl_is_expired(self):
        # TTL + 1초 경과 → 만료
        session = self._make_session(_past(1801))
        assert session.is_expired(_utcnow(), ttl_seconds=1800) is True

    def test_short_ttl_expires_quickly(self):
        # TTL=5초, 10초 전 활동 → 만료
        session = self._make_session(_past(10))
        assert session.is_expired(_utcnow(), ttl_seconds=5) is True


# ===========================================================================
# SessionStore.create
# ===========================================================================


class TestSessionStoreCreate:
    """SessionStore.create 검증."""

    def test_create_returns_session(self):
        # 반환값이 Session 인스턴스
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        assert isinstance(session, Session)

    def test_created_session_has_uuid_format(self):
        # session_id 가 uuid 형식 (32자 hex + 4 대시)
        import uuid

        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        # uuid4 로 파싱 가능해야 함
        parsed = uuid.UUID(session.session_id)
        assert str(parsed) == session.session_id

    def test_created_session_status_is_gathering(self):
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        assert session.status == "gathering"

    def test_created_session_empty_history(self):
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        assert session.history == []

    def test_created_session_empty_slots(self):
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        assert isinstance(session.slots, SlotState)
        assert session.slots.area is None

    def test_create_increments_count(self):
        store = SessionStore(ttl_seconds=1800)
        assert store.count() == 0
        store.create()
        assert store.count() == 1
        store.create()
        assert store.count() == 2

    def test_each_create_returns_unique_id(self):
        store = SessionStore(ttl_seconds=1800)
        s1 = store.create()
        s2 = store.create()
        assert s1.session_id != s2.session_id


# ===========================================================================
# SessionStore.get
# ===========================================================================


class TestSessionStoreGet:
    """SessionStore.get 검증."""

    def test_get_existing_session_returns_session(self):
        # 정상 조회 → Session 반환
        store = SessionStore(ttl_seconds=1800)
        created = store.create()
        result = store.get(created.session_id)
        assert result is not None
        assert result.session_id == created.session_id

    def test_get_nonexistent_id_returns_none(self):
        # 없는 ID → None
        store = SessionStore(ttl_seconds=1800)
        assert store.get("nonexistent-id") is None

    def test_get_expired_session_returns_none(self):
        # 만료된 세션 조회 → None
        store = SessionStore(ttl_seconds=1)  # TTL 1초
        session = store.create()
        # last_activity_at 을 2초 전으로 조작
        session.last_activity_at = _past(2)
        result = store.get(session.session_id)
        assert result is None

    def test_get_expired_session_removes_from_store(self):
        # 만료 세션 조회 후 count 감소 확인
        store = SessionStore(ttl_seconds=1)
        session = store.create()
        session.last_activity_at = _past(2)
        assert store.count() == 1
        store.get(session.session_id)
        assert store.count() == 0

    def test_get_valid_session_not_removed(self):
        # 유효한 세션은 조회 후에도 유지
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        store.get(session.session_id)
        assert store.count() == 1


# ===========================================================================
# SessionStore.touch
# ===========================================================================


class TestSessionStoreTouch:
    """SessionStore.touch 검증."""

    def test_touch_updates_last_activity_at(self):
        # touch 후 last_activity_at 이 갱신됨
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        # 60초 전으로 조작 → touch 후 현재 시각으로 갱신되었는지 확인
        past_ts = _past(60)
        session.last_activity_at = past_ts
        store.touch(session)
        # touch 이후 시각이 조작된 과거 시각보다 커야 함
        assert session.last_activity_at > past_ts

    def test_touch_with_status_updates_status(self):
        # status 파라미터 전달 시 상태 변경
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        assert session.status == "gathering"
        store.touch(session, status="analyzing")
        assert session.status == "analyzing"

    def test_touch_without_status_keeps_existing_status(self):
        # status 없이 touch → 상태 유지
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        store.touch(session, status="analyzing")
        store.touch(session)  # status 없음
        assert session.status == "analyzing"

    def test_touch_reflects_in_get(self):
        # touch 후 get 으로 같은 객체 조회 확인
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        store.touch(session, status="answered")
        retrieved = store.get(session.session_id)
        assert retrieved is not None
        assert retrieved.status == "answered"


# ===========================================================================
# SessionStore.delete
# ===========================================================================


class TestSessionStoreDelete:
    """SessionStore.delete 검증."""

    def test_delete_existing_returns_true(self):
        # 존재하는 세션 삭제 → True
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        result = store.delete(session.session_id)
        assert result is True

    def test_delete_nonexistent_returns_false(self):
        # 없는 ID 삭제 → False
        store = SessionStore(ttl_seconds=1800)
        result = store.delete("nonexistent-id")
        assert result is False

    def test_delete_removes_from_store(self):
        # 삭제 후 count 감소
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        store.delete(session.session_id)
        assert store.count() == 0

    def test_delete_makes_get_return_none(self):
        # 삭제 후 get → None
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        store.delete(session.session_id)
        assert store.get(session.session_id) is None

    def test_delete_idempotent_second_call_returns_false(self):
        # 이미 삭제된 세션 재삭제 → False (멱등)
        store = SessionStore(ttl_seconds=1800)
        session = store.create()
        store.delete(session.session_id)
        result = store.delete(session.session_id)
        assert result is False


# ===========================================================================
# SessionStore.count
# ===========================================================================


class TestSessionStoreCount:
    """SessionStore.count 검증."""

    def test_empty_store_count_is_zero(self):
        store = SessionStore(ttl_seconds=1800)
        assert store.count() == 0

    def test_count_includes_expired_sessions(self):
        # count 는 만료 검사 없이 저장 중인 모든 세션 수
        store = SessionStore(ttl_seconds=1)
        session = store.create()
        session.last_activity_at = _past(10)  # 만료 상태
        assert store.count() == 1  # get 하지 않으면 포함됨

    def test_count_after_multiple_creates(self):
        store = SessionStore(ttl_seconds=1800)
        for _ in range(5):
            store.create()
        assert store.count() == 5


# ===========================================================================
# SessionStore.purge_expired
# ===========================================================================


class TestSessionStorePurgeExpired:
    """SessionStore.purge_expired 검증."""

    def test_purge_removes_expired_sessions(self):
        # 만료 세션 2개 + 유효 세션 1개 → 만료 2개만 제거
        store = SessionStore(ttl_seconds=1800)
        expired1 = store.create()
        expired2 = store.create()
        valid = store.create()

        # 만료 상태로 조작
        expired1.last_activity_at = _past(1801)
        expired2.last_activity_at = _past(1801)

        removed = store.purge_expired()
        assert removed == 2
        assert store.count() == 1
        assert store.get(valid.session_id) is not None

    def test_purge_empty_store_returns_zero(self):
        store = SessionStore(ttl_seconds=1800)
        assert store.purge_expired() == 0

    def test_purge_no_expired_returns_zero(self):
        # 모두 유효 → 0
        store = SessionStore(ttl_seconds=1800)
        store.create()
        store.create()
        removed = store.purge_expired()
        assert removed == 0

    def test_purge_all_expired_empties_store(self):
        # 전부 만료 → count = 0
        store = SessionStore(ttl_seconds=1800)
        for _ in range(3):
            s = store.create()
            s.last_activity_at = _past(2000)
        store.purge_expired()
        assert store.count() == 0
