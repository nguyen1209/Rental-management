"""Record the current rental application schema.

Revision ID: 20260918_01
Revises:
Create Date: 2026-09-18
"""
from alembic import op
from models import db

revision = '20260918_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # checkfirst makes this baseline safe for the existing production database
    # while still creating every table for a new installation.
    db.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    # A baseline downgrade must never delete an existing production schema.
    pass
