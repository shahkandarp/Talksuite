from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation
from app.models.user import User


class ConversationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user: User,
        title: str = "New Conversation",
        account_id: UUID | None = None,
    ) -> Conversation:
        conversation = Conversation(
            user_id=user.id, title=title, account_id=account_id
        )
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def list_for_user(
        self, user: User, account_id: UUID | None = None
    ) -> list[Conversation]:
        conditions = [
            Conversation.user_id == user.id,
            Conversation.deleted_at.is_(None),
        ]
        if account_id is not None:
            conditions.append(Conversation.account_id == account_id)

        stmt = (
            select(Conversation)
            .where(*conditions)
            .order_by(desc(Conversation.updated_at))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_with_messages(
        self, conversation_id: UUID, user: User
    ) -> Conversation | None:
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
                Conversation.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, conversation_id: UUID, user: User) -> bool:
        conversation = await self.get_with_messages(conversation_id, user)
        if not conversation:
            return False
        conversation.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True

    async def update_title(self, conversation_id: UUID, title: str) -> None:
        stmt = (
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(title=title, updated_at=datetime.now(timezone.utc))
        )
        await self.db.execute(stmt)
        await self.db.commit()
