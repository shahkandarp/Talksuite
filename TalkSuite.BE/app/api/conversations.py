from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_current_account
from app.models.database import get_db_session
from app.models.user import User
from app.models.netsuite_account import NetSuiteAccount
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    ConversationDetailResponse,
    ConversationResponse,
)
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConversationResponse)
async def create_conversation(
    body: ConversationCreate,
    user: User = Depends(get_current_user),
    account: NetSuiteAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        service = ConversationService(db)
        conversation = await service.create(user, body.title, account_id=account.id)
        return conversation
    except OperationalError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    user: User = Depends(get_current_user),
    account: NetSuiteAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        service = ConversationService(db)
        return await service.list_for_user(user, account_id=account.id)
    except OperationalError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        service = ConversationService(db)
        conversation = await service.get_with_messages(conversation_id, user)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation
    except OperationalError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: UUID,
    body: ConversationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        service = ConversationService(db)
        conversation = await service.get_with_messages(conversation_id, user)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        await service.update_title(conversation_id, body.title)
        await db.refresh(conversation)
        return conversation
    except OperationalError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        service = ConversationService(db)
        deleted = await service.delete(conversation_id, user)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
    except OperationalError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )
