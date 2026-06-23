"""app.infrastructure.core.logging

파일 경로: app/core/logging.py
목적: 일관된 로깅 설정 제공.
주요 기능:
    - 환경 변수 `LOG_LEVEL` 기반 루트 로거 구성
    - Rich 핸들러로 가독성 향상
주요 의존성: logging, rich
"""

import logging

from rich.logging import RichHandler

from app.infrastructure.core.config import get_settings
from app.shared.security.pii import PiiMaskingFilter

_INITIALIZED = False


def setup_logging() -> None:
    """루트 로거를 한 번만 구성한다.

    중복 호출 시 무시된다. CLI 진입점이나 테스트 셋업에서 호출한다.

    Sprint 8 — PiiMaskingFilter 자동 부착. Settings.pii_masking_enabled 가 false 면 filter 가 no-op.

    Side Effects:
        - 루트 로거의 핸들러를 RichHandler로 교체
        - 루트 로거에 PiiMaskingFilter 부착
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    level = get_settings().log_level.upper()
    handler = RichHandler(rich_tracebacks=True, show_path=False)
    handler.addFilter(PiiMaskingFilter())
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
    )
    _INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    """모듈 이름 기반 로거를 반환한다.

    Args:
        name: 보통 `__name__` 을 전달한다.
    Returns:
        설정된 로거.
    """
    setup_logging()
    return logging.getLogger(name)
