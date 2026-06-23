"""sprint26_users_mydata_external_id

Revision ID: f4a5b6c7d8e9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-23 16:30:00.000000

Sprint 26: 데모 페르소나(이름+전화 매핑) 연동.
- users.mydata_external_id (nullable) 추가 — 로그인 사용자를 마이데이터/건강보험
  external_id(페르소나)로 연결. 비데모 사용자는 NULL.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: str | Sequence[str] | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("mydata_external_id", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("mydata_external_id")
