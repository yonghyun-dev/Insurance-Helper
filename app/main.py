"""app.main

파일 경로: app/main.py
목적: FastAPI 앱 진입점. 도메인 router 들을 한 곳에서 등록하는 표준 위치.

Sprint 3 부터:
    - 브라우저 UI 호출을 위해 CORSMiddleware 추가 (origin 화이트리스트는 settings)
    - 처리되지 않은 예외에 대한 표준 에러 응답(`INTERNAL_ERROR`) 핸들러 추가
      — 사양서 (`docs/design/ui-states.md § 3`) 에 정의된 형태와 일치

실행:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.domains.chunks.router import router as chunks_router
from app.domains.documents.router import router as documents_router
from app.domains.search.router import router as search_router
from app.domains.sessions.router import router as sessions_router
from app.infrastructure.core.config import get_settings
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()
_scheduler: Any = None  # Sprint 15 (W-3) — APScheduler 인스턴스, lifespan 안에서 관리


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """app startup/shutdown lifecycle (Sprint 15 W-3 — on_event deprecation 보정).

    Sprint 15: 첨부 TTL cleanup scheduler 시작 + 종료 시 정리.
    ATTACHMENT_TTL_HOURS=0 시 skip (테스트 환경 graceful).
    """
    global _scheduler
    if _settings.attachment_ttl_hours > 0:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            from app.domains.attachments import service as attachments_service

            _scheduler = AsyncIOScheduler()
            _scheduler.add_job(attachments_service.cleanup_expired, "interval", hours=1)
            _scheduler.start()
            logger.info(
                "attachment cleanup scheduler started (interval=1h, TTL=%dh)",
                _settings.attachment_ttl_hours,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "attachment cleanup scheduler 시작 실패: %s — 수동 cleanup 필요", exc
            )
    else:
        logger.info("attachment cleanup scheduler skip (TTL=0)")

    # 데모 페르소나 계정 자동 시드(멱등) — 이름+전화 매핑 데모용.
    # PM-43 Tier 0 — production 이면 flag 와 무관하게 시드 안 함(공용 비번 백도어 차단).
    if get_settings().should_seed_demo:
        try:
            from app.domains.auth.personas import seed_demo_users
            from app.infrastructure.core.database import session_scope

            with session_scope() as session:
                created = seed_demo_users(session)
            logger.info("데모 페르소나 시드 완료(신규 %d명)", created)
        except Exception as exc:  # noqa: BLE001
            logger.warning("데모 페르소나 시드 실패(무시): %s", exc)

    yield

    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler shutdown 실패: %s", exc)
        _scheduler = None


app = FastAPI(
    title="보험청구심사 어시스턴트",
    description="약관 RAG 기반 청구 가능성 평가 API",
    version="0.1.0",
    lifespan=lifespan,
)

# Sprint 8 — rate limit (slowapi). Settings.rate_limit_enabled 가 false 면 limiter 가 enabled=False
# config_filename — slowapi 가 내부적으로 starlette Config 로 .env 를 cp949 로 읽다 한글 깨짐.
# 더미 경로 주입해 starlette 가 무시하게 (`Settings` 가 이미 .env 를 utf-8 로 읽음, 중복 제거).
_limiter = Limiter(
    key_func=get_remote_address,
    enabled=_settings.rate_limit_enabled,
    default_limits=[],  # 글로벌 기본 한도 없음 — endpoint 별 @limiter.limit() 로 적용
    config_filename="__slowapi_no_env__",
)
app.state.limiter = _limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# 미들웨어 등록 순서 (LIFO — 마지막 add 가 가장 바깥)
# 1) CORS — 가장 안쪽 (rate limit 응답에도 CORS 헤더 부착되도록)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_allow_origins,
    # Sprint 14 (REQ-10): HttpOnly cookie JWT 자동 전송을 위해 credentials 허용
    # CORS 와일드카드("*") 시 브라우저가 차단하므로 cors_allow_origins 는 CSV 화이트리스트 강제
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
# 2) slowapi — CORS 바깥. _rate_limit_exceeded_handler 가 CORS 후 응답 구성하므로 헤더 손실 없음
app.add_middleware(SlowAPIMiddleware)

# Sprint 5 — PDF 페이지 캡처 + 원본 PDF 정적 노출
_settings.ensure_data_dirs()
app.mount(
    "/static/page_images",
    StaticFiles(directory=str(_settings.page_images_path)),
    name="page_images",
)
app.mount(
    "/static/raw",
    StaticFiles(directory=str(_settings.raw_data_path)),
    name="raw_pdf",
)

_API_PREFIX = "/api/v1"
app.include_router(documents_router, prefix=_API_PREFIX)
app.include_router(chunks_router, prefix=_API_PREFIX)
app.include_router(search_router, prefix=_API_PREFIX)
app.include_router(sessions_router, prefix=_API_PREFIX)

# Sprint 14 — 자체 JWT 로그인 + 마이데이터 (REQ-10)
from app.domains.auth.router import router as auth_router  # noqa: E402

app.include_router(auth_router, prefix=_API_PREFIX)

# Sprint 15 — OCR 서류 업로드 (REQ-11)
from app.domains.attachments.router import router as attachments_router  # noqa: E402

app.include_router(attachments_router, prefix=_API_PREFIX)

# Sprint 18 — 사용자 건강보험 API (REQ-14)
from app.infrastructure.external.health_data.router import (  # noqa: E402
    router as health_data_router,
)

app.include_router(health_data_router, prefix=_API_PREFIX)


_MSG_INTERNAL_ERROR = "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."


@app.exception_handler(Exception)
async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """처리되지 않은 예외를 표준 에러 응답(`INTERNAL_ERROR`) 으로 변환한다.

    FastAPI 의 기본 `HTTPException` 처리(라우터에서 `_error(...)` 로 raise) 보다 우선순위가
    낮으므로, 라우터에서 명시적으로 처리한 4xx/5xx 는 그대로 통과한다. 본 핸들러는 오직
    예상 못 한 5xx 만 잡아 사양서 표준 형태 (`{"error": {"code": "INTERNAL_ERROR", ...}}`)
    로 응답한다. 사용자에게 내부 상세를 노출하지 않는다.
    """
    logger.exception("unhandled exception at %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": _MSG_INTERNAL_ERROR,
            }
        },
    )


@app.get("/health", tags=["meta"])
def healthcheck() -> dict[str, str]:
    """라이브니스 체크. Sprint 1 단계에서 본 모듈 동작을 확인하는 용도."""
    return {"status": "ok"}


@app.get("/metrics", tags=["meta"], include_in_schema=False)
def metrics() -> PlainTextResponse:
    """Sprint 8 — prometheus exposition. Settings.prometheus_enabled 가 false 면 404.

    기본 메트릭: process_cpu_seconds_total / process_resident_memory_bytes 등 (prometheus_client 자동 수집).
    Sprint 11: app 메트릭 (LLM 호출 수, 응답시간 히스토그램 등) 추가 예정.
    """
    if not _settings.prometheus_enabled:
        return PlainTextResponse("metrics disabled", status_code=404)
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
