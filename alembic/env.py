"""Alembic 마이그레이션 환경.

- target_metadata 는 본 프로젝트 Base 의 metadata 를 사용한다.
- sqlalchemy.url 은 `app.infrastructure.core.config.Settings.sqlite_db_path`
  에서 동적으로 채운다. alembic.ini 의 sqlalchemy.url 은 비워둔다.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 프로젝트 루트를 sys.path 에 추가 (app/ 단일 패키지 레이아웃)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.infrastructure.core.config import get_settings  # noqa: E402
from app.infrastructure.core.database import Base  # noqa: E402

# 모델 모듈 import 로 metadata 등록 보장
import app.shared.audit.models  # noqa: F401, E402
import app.domains.chunks.models  # noqa: F401, E402
import app.domains.documents.models  # noqa: F401, E402
import app.domains.users.models  # noqa: F401, E402  # Sprint 14 — users + audit_log.user_id FK

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# DB URL 동적 설정.
# Sprint 8: Settings.database_url 가 비어 있으면 SQLite (기본), 값이 있으면 그대로 사용 (PostgreSQL 등).
_settings = get_settings()
if _settings.database_url:
    _db_url = _settings.database_url
else:
    _settings.ensure_data_dirs()
    _db_url = f"sqlite:///{_settings.sqlite_db_path.as_posix()}"
config.set_main_option("sqlalchemy.url", _db_url)


def run_migrations_offline() -> None:
    """오프라인 모드 — DBAPI 없이 SQL 만 생성."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite ALTER 호환
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """온라인 모드 — 실제 SQLite 에 적용."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite ALTER 호환
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
