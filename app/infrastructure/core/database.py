"""app.infrastructure.core.database

파일 경로: app/core/database.py
목적: SQLAlchemy 엔진과 세션 팩토리 관리.
주요 기능:
    - SQLite 엔진 생성 (설정의 `sqlite_db_path` 사용)
    - 세션 컨텍스트 매니저 (`session_scope`)
    - 모델 베이스 클래스 `Base` 노출
주요 의존성: sqlalchemy
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.infrastructure.core.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 스타일 모델 베이스 클래스.

    모든 도메인 모델은 이 클래스를 상속한다.
    """


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """DB 엔진을 생성하고 캐시한다.

    `Settings.database_url` 가 빈 문자열이면 SQLite (sqlite_db_path 사용).
    값이 있으면 그대로 사용 (예: 'postgresql+psycopg://user:pw@host:5432/db').

    Sprint 8 — PostgreSQL 옵션 추가. SQLite 가 기본이라 회귀 0.

    Returns:
        Engine: SQLAlchemy 엔진.
    Side Effects:
        - SQLite 인 경우 데이터 디렉터리가 없으면 생성
    """
    settings = get_settings()
    if settings.database_url:
        return create_engine(settings.database_url, future=True, echo=False)
    settings.ensure_data_dirs()
    url = f"sqlite:///{settings.sqlite_db_path.as_posix()}"
    return create_engine(url, future=True, echo=False)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    """세션 팩토리를 반환한다."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """트랜잭션을 자동 관리하는 세션 컨텍스트 매니저.

    Yields:
        Session: 사용 후 자동 commit / 예외 시 rollback.
    """
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Iterator[Session]:
    """FastAPI Depends 용 read-only 세션 제공자.

    트랜잭션 commit 은 하지 않는다 (router 단에서 노출하는 엔드포인트는 read-only).
    close 는 보장. write 가 필요하면 service 가 `session_scope` 를 직접 사용.
    """
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
