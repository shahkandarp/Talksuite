from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role_tool_map import RoleToolMap


class RoleFilter:
    """
    Filters tool definitions based on the current user's role.

    Only tools listed in role_tool_map for the user's role will be
    presented to the LLM. Tools outside the whitelist are invisible
    to Claude — it cannot call what it cannot see.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_allowed_tools(self, role: str) -> list[str]:
        """Get the list of tool names allowed for a given role."""
        stmt = select(RoleToolMap.tool_name).where(RoleToolMap.role == role)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def filter_tools(
        self, all_tools: list[dict[str, Any]], allowed_tool_names: list[str]
    ) -> list[dict[str, Any]]:
        """
        Filter tool definitions to only include those in the allowed set.

        Returns an empty list if no tools are allowed for the role.
        """
        if not allowed_tool_names:
            return []
        return [t for t in all_tools if t.get("name") in allowed_tool_names]
