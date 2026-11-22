import uuid

from sqlalchemy import Column, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class RoleToolMap(Base):
    __tablename__ = "role_tool_map"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String, nullable=False, index=True)
    tool_name = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("role", "tool_name", name="uq_role_tool_map_role_tool_name"),
    )
