"""sprint14_users_audit_user_id

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-26 11:30:00.000000

Sprint 14 (REQ-10): 자체 JWT 로그인 시스템 도입.
- users 테이블 신규 (email + bcrypt password_hash)
- audit_log.user_id nullable FK 추가 (기존 row 마이그레이션 0 — NULL 폴백)
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """users 테이블 생성 + audit_log.user_id FK 추가."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # audit_log.user_id nullable FK — 기존 row 그대로 (NULL 폴백)
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_audit_log_user_id_users", "users", ["user_id"], ["id"]
        )
        batch_op.create_index("ix_audit_log_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_log_user_id")
        batch_op.drop_constraint("fk_audit_log_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
