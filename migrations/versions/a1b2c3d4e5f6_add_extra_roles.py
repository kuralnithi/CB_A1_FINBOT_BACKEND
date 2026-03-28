"""add_extra_roles_to_users

Revision ID: a1b2c3d4e5f6
Revises: 5858d4dae09b
Create Date: 2026-03-28 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '5858d4dae09b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('extra_roles', sa.String(), nullable=True, server_default='')
    )


def downgrade() -> None:
    op.drop_column('users', 'extra_roles')
