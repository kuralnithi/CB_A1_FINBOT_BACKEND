"""Add eval_runs table

Revision ID: c9d0e1f2a3b4
Revises: b3b67ecb7608
Create Date: 2026-03-29

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b3b67ecb7608'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'eval_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, index=True),
        sa.Column('experiment_name', sa.String(), nullable=False),
        sa.Column('dataset_name', sa.String(), nullable=False, server_default='finbot_eval'),
        sa.Column('total_examples', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_exact_match', sa.Float(), nullable=True),
        sa.Column('results_url', sa.String(), nullable=True),
        sa.Column('per_example_results', sa.Text(), nullable=True),
        sa.Column('triggered_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('eval_runs')
