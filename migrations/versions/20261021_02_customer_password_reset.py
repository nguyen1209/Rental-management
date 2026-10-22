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


def upgrade():
    op.add_column('admin', sa.Column('password_reset_token_hash', sa.String(length=64), nullable=True))
    op.add_column('admin', sa.Column('password_reset_expires_at', sa.DateTime(), nullable=True))
    op.create_index('ix_admin_password_reset_token_hash', 'admin',
                    ['password_reset_token_hash'], unique=True)
    op.add_column('customer', sa.Column('password_reset_token_hash', sa.String(length=64), nullable=True))
    op.add_column('customer', sa.Column('password_reset_expires_at', sa.DateTime(), nullable=True))
    op.create_index('ix_customer_password_reset_token_hash', 'customer',
                    ['password_reset_token_hash'], unique=True)


def downgrade():
    op.drop_index('ix_customer_password_reset_token_hash', table_name='customer')
    op.drop_column('customer', 'password_reset_expires_at')
    op.drop_column('customer', 'password_reset_token_hash')
    op.drop_index('ix_admin_password_reset_token_hash', table_name='admin')
    op.drop_column('admin', 'password_reset_expires_at')
    op.drop_column('admin', 'password_reset_token_hash')
