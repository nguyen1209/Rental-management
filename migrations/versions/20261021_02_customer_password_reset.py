"""Add single-use password reset token storage for admin and customer accounts.

Revision ID: 20261021_02
Revises: 20261021_01
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa


revision = '20261021_02'
down_revision = '20261021_01'
branch_labels = None
depends_on = None


def _columns(table):
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column['name'] for column in inspector.get_columns(table)}


def _indexes(table):
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {index['name'] for index in inspector.get_indexes(table)}


def upgrade():
    for table in ('admin', 'customer'):
        columns = _columns(table)
        if 'password_reset_token_hash' not in columns:
            op.add_column(table, sa.Column(
                'password_reset_token_hash', sa.String(length=64), nullable=True))
        if 'password_reset_expires_at' not in columns:
            op.add_column(table, sa.Column(
                'password_reset_expires_at', sa.DateTime(), nullable=True))

        index_name = f'ix_{table}_password_reset_token_hash'
        if index_name not in _indexes(table):
            op.create_index(index_name, table,
                            ['password_reset_token_hash'], unique=True)


def downgrade():
    for table in ('customer', 'admin'):
        index_name = f'ix_{table}_password_reset_token_hash'
        if index_name in _indexes(table):
            op.drop_index(index_name, table_name=table)
        columns = _columns(table)
        if 'password_reset_expires_at' in columns:
            op.drop_column(table, 'password_reset_expires_at')
        if 'password_reset_token_hash' in columns:
            op.drop_column(table, 'password_reset_token_hash')
