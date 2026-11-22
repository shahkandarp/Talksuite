from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


class MessageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user_message(
        self, conversation_id: UUID, content: str
    ) -> Message:
        """Persist a user message in the conversation."""
        message = Message(
            conversation_id=conversation_id,
            role="user",
            content=content,
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def create_assistant_message(
        self,
        conversation_id: UUID,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> Message:
        """Persist an assistant response message in the conversation."""
        message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            tool_calls=tool_calls,
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_conversation_messages(
        self, conversation_id: UUID
    ) -> list[Message]:
        """Load all messages for a conversation, ordered by created_at."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
