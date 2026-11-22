from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class PkceSession(Base):
    __tablename__ = "pkce_sessions"

    state = Column(String, primary_key=True)
    code_verifier = Column(String, nullable=False)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("netsuite_accounts.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
