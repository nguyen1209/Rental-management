"""Add the rental cancel reason column and the missing query indexes.

The baseline migration only creates missing tables, so an existing production
database never received the columns and indexes introduced afterwards. This
revision is idempotent: it only touches what is actually missing.

Revision ID: 20261021_01
Revises: 20260918_01
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa

revision = '20261021_01'
down_revision = '20260918_01'
branch_labels = None
depends_on = None

NEW_INDEXES = (
    ('customer', 'ix_customer_phone', ['phone']),
    ('customer', 'ix_customer_created_at', ['created_at']),
    ('product', 'ix_product_category', ['category']),
    ('product', 'ix_product_status', ['status']),
    ('product', 'ix_product_created_at', ['created_at']),
    ('rental', 'ix_rental_customer_id', ['customer_id']),
    ('rental', 'ix_rental_rental_date', ['rental_date']),
    ('rental', 'ix_rental_start_date', ['start_date']),
    ('rental', 'ix_rental_status', ['status']),
    ('rental', 'ix_rental_payment_status', ['payment_status']),
    ('rental_detail', 'ix_rental_detail_rental_id', ['rental_id']),
    ('rental_detail', 'ix_rental_detail_product_id', ['product_id']),
    ('category', 'ix_category_parent_id', ['parent_id']),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table):
    return table in _inspector().get_table_names()


def _columns(table):
    if not _table_exists(table):
        return set()
    return {column['name'] for column in _inspector().get_columns(table)}


def _indexes(table):
    if not _table_exists(table):
        return set()
    return {index['name'] for index in _inspector().get_indexes(table)}


def upgrade():
    if 'cancel_reason' not in _columns('rental'):
        op.add_column('rental', sa.Column('cancel_reason', sa.Text(), nullable=True))
    for table, name, columns in NEW_INDEXES:
        if not _table_exists(table):
            continue
        if name in _indexes(table):
            continue
        op.create_index(name, table, columns, unique=False)


def downgrade():
    for table, name, _columns_list in NEW_INDEXES:
        if name in _indexes(table):
            op.drop_index(name, table_name=table)
    if 'cancel_reason' in _columns('rental'):
        op.drop_column('rental', 'cancel_reason')
