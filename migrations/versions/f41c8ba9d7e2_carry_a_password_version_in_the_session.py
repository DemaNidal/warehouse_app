"""carry a password version in the session

Changing a password did not end the sessions it had opened. Flask-Login
stores the user's id in the cookie and nothing else, so a browser that was
already signed in stayed signed in for the rest of the eight hours, with the
old password irrelevant to it. Anyone changing a password because they think
somebody else is in their account was not achieving the thing they were
trying to achieve.

The column is a counter the cookie now carries. The loader compares them, and
a cookie holding an older number stops loading the user.

Existing rows start at 1, which is also what new rows default to. Sessions
opened before this hold a cookie with no version at all, and those are not
honoured -- everyone signs in once more after this is deployed.

Revision ID: f41c8ba9d7e2
Revises: d9b2e07c45f1
Create Date: 2026-11-11 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f41c8ba9d7e2'
down_revision = 'd9b2e07c45f1'
branch_labels = None
depends_on = None


TABLE = "user"
COLUMN = "auth_version"


def upgrade():
    op.add_column(
        TABLE,
        sa.Column(COLUMN, sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade():
    # Dropping the column puts every session back on the id alone, which is
    # the behaviour this replaced. Nothing is lost: the counter means nothing
    # without the loader that reads it.
    op.drop_column(TABLE, COLUMN)
