"""Seed data - test user and default role tool mappings

Revision ID: 002
Revises: 001
Create Date: 2025-06-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # Insert test user using raw SQL to avoid parameter/cast issues
    op.execute(
        sa.text(
            f"""
            INSERT INTO users (id, email, name, role)
            VALUES ('{TEST_USER_ID}'::uuid, 'test@talksuite.dev', 'Test User', 'admin')
            ON CONFLICT (email) DO NOTHING
            """
        )
    )

    # Insert default role-tool mappings
    role_tools = {
        "admin": [
            "netsuite_get_invoice",
            "netsuite_get_customer",
            "netsuite_get_inventory",
            "netsuite_get_sales_order",
            "netsuite_get_vendor",
            "netsuite_get_purchase_order",
            "netsuite_search_records",
            "netsuite_get_financial_report",
        ],
        "finance": [
            "netsuite_get_invoice",
            "netsuite_get_customer",
            "netsuite_get_financial_report",
        ],
        "inventory": [
            "netsuite_get_inventory",
            "netsuite_get_purchase_order",
            "netsuite_get_vendor",
        ],
    }

    for role, tools in role_tools.items():
        for tool_name in tools:
            op.execute(
                sa.text(
                    f"""
                    INSERT INTO role_tool_map (id, role, tool_name)
                    VALUES (gen_random_uuid(), '{role}', '{tool_name}')
                    ON CONFLICT ON CONSTRAINT uq_role_tool_map_role_tool_name DO NOTHING
                    """
                )
            )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM role_tool_map"))
    op.execute(sa.text(f"DELETE FROM users WHERE id = '{TEST_USER_ID}'::uuid"))
