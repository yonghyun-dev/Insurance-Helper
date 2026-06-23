"""tests.test_main_lifespan

app/main.py 의 APScheduler startup/shutdown lifespan 이벤트 테스트 (Sprint 15 REQ-11 F-9).

테스트 대상:
    - lifespan startup — TTL=0 시 scheduler 미시작 (logger.info 만)
    - lifespan startup — TTL>0 시 scheduler 시작 (AsyncIOScheduler.start 호출)
    - lifespan startup — scheduler 예외 시 graceful (logger.warning 만, raise X)
    - lifespan shutdown — _scheduler=None 이면 no-op
    - lifespan shutdown — _scheduler 존재 시 shutdown(wait=False) 호출 + None 초기화
    - lifespan shutdown — shutdown 예외 시 graceful

설계 메모:
    - main.py 가 lifespan contextmanager 로 리팩토링됨 (on_event deprecated).
    - main._settings 를 monkeypatch.setattr 로 교체 (metrics 테스트 패턴 동일).
    - lifespan 은 asynccontextmanager 이므로 async iterator 소비 방식으로 호출.
    - APScheduler 는 `apscheduler.schedulers.asyncio.AsyncIOScheduler` 경로 patch.
"""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 헬퍼 — FakeSettings
# ---------------------------------------------------------------------------


class _FakeSettingsTTLZero:
    """attachment_ttl_hours = 0 (scheduler skip 분기)."""

    attachment_ttl_hours = 0
    prometheus_enabled = True
    rate_limit_enabled = False
    cors_allow_origins = ["http://localhost:5173"]
    openai_api_key = "test-key"


class _FakeSettingsTTLPositive:
    """attachment_ttl_hours = 24 (scheduler 시작 분기)."""

    attachment_ttl_hours = 24
    prometheus_enabled = True
    rate_limit_enabled = False
    cors_allow_origins = ["http://localhost:5173"]
    openai_api_key = "test-key"


async def _run_lifespan_startup(main_mod, extra_patches=None):
    """lifespan contextmanager 의 startup 부분만 실행한다.

    contextmanager 는 yield 전까지가 startup 이다.
    yield 이후(shutdown)는 실행하지 않는다.
    """
    ctx = main_mod.lifespan(main_mod.app)
    with contextlib.suppress(StopAsyncIteration):
        await ctx.__aenter__()


async def _run_lifespan_full(main_mod, extra_patches=None):
    """lifespan contextmanager 전체(startup + shutdown)를 실행한다."""
    ctx = main_mod.lifespan(main_mod.app)
    await ctx.__aenter__()
    try:
        yield
    finally:
        await ctx.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# TTL=0 시 scheduler 미시작
# ---------------------------------------------------------------------------


class TestLifespanStartupTTLZero:
    """ATTACHMENT_TTL_HOURS=0 이면 APScheduler 를 시작하지 않는다."""

    def test_scheduler_not_started_when_ttl_zero(self, monkeypatch):
        """TTL=0 이면 AsyncIOScheduler 인스턴스화가 발생하지 않는다."""
        import app.main as main_mod

        # Arrange
        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLZero())
        monkeypatch.setattr(main_mod, "_scheduler", None)

        mock_sched_cls = MagicMock()

        with patch(
            "apscheduler.schedulers.asyncio.AsyncIOScheduler",
            mock_sched_cls,
        ):
            asyncio.run(_run_lifespan_startup(main_mod))

        # scheduler 클래스 인스턴스화 없음
        mock_sched_cls.assert_not_called()

    def test_scheduler_module_var_stays_none_when_ttl_zero(self, monkeypatch):
        """TTL=0 이면 main._scheduler 가 None 으로 유지된다."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLZero())
        monkeypatch.setattr(main_mod, "_scheduler", None)

        asyncio.run(_run_lifespan_startup(main_mod))

        assert main_mod._scheduler is None

    def test_info_logged_when_ttl_zero(self, monkeypatch, caplog):
        """TTL=0 이면 'skip' 관련 info 로그가 기록된다."""
        import logging

        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLZero())
        monkeypatch.setattr(main_mod, "_scheduler", None)

        with caplog.at_level(logging.INFO, logger="app.main"):
            asyncio.run(_run_lifespan_startup(main_mod))

        log_messages = " ".join(r.message for r in caplog.records)
        assert "skip" in log_messages or "TTL=0" in log_messages


# ---------------------------------------------------------------------------
# TTL>0 시 scheduler 시작
# ---------------------------------------------------------------------------


class TestLifespanStartupTTLPositive:
    """ATTACHMENT_TTL_HOURS>0 이면 APScheduler 를 시작한다."""

    def test_scheduler_start_called(self, monkeypatch):
        """TTL>0 이면 scheduler.start() 가 1회 호출된다."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLPositive())
        monkeypatch.setattr(main_mod, "_scheduler", None)

        mock_sched_instance = MagicMock()
        mock_sched_cls = MagicMock(return_value=mock_sched_instance)
        mock_service = MagicMock()

        with (
            patch("apscheduler.schedulers.asyncio.AsyncIOScheduler", mock_sched_cls),
            patch.dict(
                "sys.modules",
                {"app.domains.attachments.service": mock_service},
            ),
        ):
            asyncio.run(_run_lifespan_startup(main_mod))

        mock_sched_instance.start.assert_called_once()

    def test_add_job_registered_with_interval_1h(self, monkeypatch):
        """scheduler.add_job 이 trigger='interval', hours=1 로 호출된다."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLPositive())
        monkeypatch.setattr(main_mod, "_scheduler", None)

        mock_sched_instance = MagicMock()
        mock_sched_cls = MagicMock(return_value=mock_sched_instance)
        mock_service = MagicMock()

        with (
            patch("apscheduler.schedulers.asyncio.AsyncIOScheduler", mock_sched_cls),
            patch.dict("sys.modules", {"app.domains.attachments.service": mock_service}),
        ):
            asyncio.run(_run_lifespan_startup(main_mod))

        add_job_calls = mock_sched_instance.add_job.call_args_list
        assert len(add_job_calls) == 1
        call_kwargs = add_job_calls[0][1]
        # hours=1 검증
        assert call_kwargs.get("hours") == 1

    def test_scheduler_assigned_after_start(self, monkeypatch):
        """scheduler 시작 후 main._scheduler 가 None 이 아니다."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLPositive())
        monkeypatch.setattr(main_mod, "_scheduler", None)

        mock_sched_instance = MagicMock()
        mock_sched_cls = MagicMock(return_value=mock_sched_instance)
        mock_service = MagicMock()

        with (
            patch("apscheduler.schedulers.asyncio.AsyncIOScheduler", mock_sched_cls),
            patch.dict("sys.modules", {"app.domains.attachments.service": mock_service}),
        ):
            asyncio.run(_run_lifespan_startup(main_mod))

        assert main_mod._scheduler is not None


# ---------------------------------------------------------------------------
# startup — scheduler 예외 시 graceful
# ---------------------------------------------------------------------------


class TestLifespanStartupSchedulerError:
    """APScheduler 생성/시작 예외 시 graceful — warning 로그 + 예외 propagate X."""

    def test_no_exception_propagated_on_error(self, monkeypatch):
        """AsyncIOScheduler 생성 실패해도 lifespan startup 은 예외를 propagate 하지 않는다."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLPositive())
        monkeypatch.setattr(main_mod, "_scheduler", None)

        with patch(
            "apscheduler.schedulers.asyncio.AsyncIOScheduler",
            side_effect=RuntimeError("apscheduler 없음"),
        ):
            try:
                asyncio.run(_run_lifespan_startup(main_mod))
            except RuntimeError:
                pytest.fail("scheduler 시작 실패가 RuntimeError 를 propagate 했음")

    def test_warning_logged_on_error(self, monkeypatch, caplog):
        """scheduler 시작 실패 시 logger.warning 이 기록된다."""
        import logging

        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLPositive())
        monkeypatch.setattr(main_mod, "_scheduler", None)

        with (
            caplog.at_level(logging.WARNING, logger="app.main"),
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler",
                side_effect=RuntimeError("테스트 에러"),
            ),
        ):
            asyncio.run(_run_lifespan_startup(main_mod))

        assert any(r.levelno >= logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# shutdown — _scheduler=None 이면 no-op
# ---------------------------------------------------------------------------


class TestLifespanShutdownNoScheduler:
    """_scheduler = None 이면 shutdown 에서 아무것도 하지 않는다."""

    def test_no_error_when_scheduler_is_none(self, monkeypatch):
        """_scheduler = None 상태에서 lifespan shutdown 이 예외 없이 완료된다."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLZero())
        monkeypatch.setattr(main_mod, "_scheduler", None)

        async def _run():
            ctx = main_mod.lifespan(main_mod.app)
            await ctx.__aenter__()
            await ctx.__aexit__(None, None, None)

        # 예외 없이 완료되어야 함
        asyncio.run(_run())

    def test_scheduler_remains_none_after_shutdown_with_no_scheduler(self, monkeypatch):
        """_scheduler = None 이면 shutdown 후에도 None 이다."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLZero())
        monkeypatch.setattr(main_mod, "_scheduler", None)

        async def _run():
            ctx = main_mod.lifespan(main_mod.app)
            await ctx.__aenter__()
            await ctx.__aexit__(None, None, None)

        asyncio.run(_run())

        assert main_mod._scheduler is None


# ---------------------------------------------------------------------------
# shutdown — scheduler 존재 시 동작
# ---------------------------------------------------------------------------


class TestLifespanShutdownWithScheduler:
    """_scheduler 가 있으면 shutdown(wait=False) 호출 후 None 초기화."""

    def test_shutdown_called_with_wait_false(self, monkeypatch):
        """lifespan 종료 시 scheduler.shutdown(wait=False) 가 호출된다."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLZero())

        mock_sched = MagicMock()
        monkeypatch.setattr(main_mod, "_scheduler", mock_sched)

        async def _run():
            ctx = main_mod.lifespan(main_mod.app)
            await ctx.__aenter__()
            await ctx.__aexit__(None, None, None)

        asyncio.run(_run())

        mock_sched.shutdown.assert_called_once_with(wait=False)

    def test_scheduler_set_none_after_shutdown(self, monkeypatch):
        """shutdown 이후 main._scheduler 가 None 이 된다."""
        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLZero())

        mock_sched = MagicMock()
        monkeypatch.setattr(main_mod, "_scheduler", mock_sched)

        async def _run():
            ctx = main_mod.lifespan(main_mod.app)
            await ctx.__aenter__()
            await ctx.__aexit__(None, None, None)

        asyncio.run(_run())

        assert main_mod._scheduler is None

    def test_shutdown_error_is_graceful(self, monkeypatch, caplog):
        """scheduler.shutdown() 예외 시 propagate 없이 warning 기록."""
        import logging

        import app.main as main_mod

        monkeypatch.setattr(main_mod, "_settings", _FakeSettingsTTLZero())

        mock_sched = MagicMock()
        mock_sched.shutdown.side_effect = RuntimeError("shutdown 오류")
        monkeypatch.setattr(main_mod, "_scheduler", mock_sched)

        async def _run():
            ctx = main_mod.lifespan(main_mod.app)
            await ctx.__aenter__()
            await ctx.__aexit__(None, None, None)

        with caplog.at_level(logging.WARNING, logger="app.main"):
            try:
                asyncio.run(_run())
            except RuntimeError:
                pytest.fail("shutdown 오류가 propagate 되었음")

        assert any(r.levelno >= logging.WARNING for r in caplog.records)
