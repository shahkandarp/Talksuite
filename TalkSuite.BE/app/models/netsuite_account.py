import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class NetSuiteAccount(Base):
    __tablename__ = "netsuite_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    account_id = Column(String, nullable=False)
    client_id = Column(String, nullable=False)
    client_secret = Column(Text, nullable=True)  # encrypted
    mcp_url = Column(String, nullable=True)
    redirect_uri = Column(String, nullable=True)
    scope = Column(String, nullable=False, default="mcp")
    refresh_token = Column(Text, nullable=True)  # encrypted
    access_token = Column(Text, nullable=True)  # encrypted
    token_expiry = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user_links = relationship(
        "UserAccountMap", back_populates="account", cascade="all, delete-orphan"
    )
