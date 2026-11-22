"""Service for user management (admin operations)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.auth_service import hash_password


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, email: str, name: str, password: str, role: str = "viewer"
    ) -> User:
        user = User(
            email=email,
            name=name,
            role=role,
            password_hash=hash_password(password),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get(self, user_id: UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[User]:
        stmt = select(User).order_by(User.created_at)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_role(self, user_id: UUID, role: str) -> User | None:
        user = await self.get(user_id)
        if not user:
            return None
        user.role = role
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update(
        self,
        user_id: UUID,
        name: str | None = None,
        role: str | None = None,
        password: str | None = None,
    ) -> User | None:
        user = await self.get(user_id)
        if not user:
            return None
        if name is not None and name.strip():
            user.name = name.strip()
        if role is not None and role.strip():
            user.role = role.strip()
        if password is not None and password.strip():
            user.password_hash = hash_password(password)
        await self.db.commit()
        await self.db.refresh(user)
        return user
