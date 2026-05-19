"""add_resume_kind

Revision ID: 4a3a0aa2188a
Revises: d9b069e47ad3
Create Date: 2026-05-19 02:19:44.086005

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a3a0aa2188a'
down_revision: Union[str, None] = 'd9b069e47ad3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chatbot_scheduled_resumes",
        sa.Column("kind", sa.String(30), nullable=False, server_default="delay_advance"),
        schema="mensageria",
    )


def downgrade() -> None:
    op.drop_column("chatbot_scheduled_resumes", "kind", schema="mensageria")
