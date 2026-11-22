"""Add password_hash to users and seed test user password

Revision ID: 004
Revises: 003
Create Date: 2025-06-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import hashlib

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # Add password_hash column with a default empty string
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(), nullable=False, server_default=""),
    )

    # Set password for test user (password: "admin123")
    password_hash = hashlib.sha256("admin123".encode()).hexdigest()
    op.execute(
        sa.text(
            f"""
            UPDATE users SET password_hash = '{password_hash}'
            WHERE id = '{TEST_USER_ID}'::uuid
            """
        )
    )

    # Add a finance user (password: "finance123")
    finance_hash = hashlib.sha256("finance123".encode()).hexdigest()
    op.execute(
        sa.text(
            f"""
            INSERT INTO users (id, email, name, role, password_hash)
            VALUES (gen_random_uuid(), 'finance@talksuite.dev', 'Finance User', 'finance', '{finance_hash}')
            ON CONFLICT (email) DO NOTHING
            """
        )
    )

    # Add an inventory user (password: "inventory123")
    inventory_hash = hashlib.sha256("inventory123".encode()).hexdigest()
    op.execute(
        sa.text(
            f"""
            INSERT INTO users (id, email, name, role, password_hash)
            VALUES (gen_random_uuid(), 'inventory@talksuite.dev', 'Inventory User', 'inventory', '{inventory_hash}')
            ON CONFLICT (email) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM users WHERE email IN ('finance@talksuite.dev', 'inventory@talksuite.dev')")
    )
    op.drop_column("users", "password_hash")
