# Design Document: TalkSuite Backend

## Architecture Overview

TalkSuite Backend is a layered async Python application built on FastAPI. The architecture separates concerns into four primary layers:

1. **API Layer** — FastAPI route handlers exposing REST + SSE endpoints
2. **Orchestration Layer** — LangGraph-based agent loop handling reasoning, tool routing, and guardrails
3. **Integration Layer** — Clients for AWS Bedrock (LLM + Knowledge Base) and NetSuite MCP Server
4. **Persistence Layer** — PostgreSQL via async SQLAlchemy + asyncpg

```
┌─────────────────────────────────────────────────────────────┐
│                       Client (Frontend)                       │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / SSE
┌──────────────────────────────▼──────────────────────────────┐
│                     API Layer (FastAPI)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Conversations│  │   Messages   │  │  User_Provider   │   │
│  │   Router     │  │    Router    │  │  (Dependency)    │   │
│  └──────────────┘  └──────┬───────┘  └──────────────────┘   │
└────────────────────────────┼─────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│                Orchestration Layer (LangGraph)                 │
│  ┌────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │ Agent Loop │  │ Guardrail_Eng. │  │  Role_Filter     │   │
│  │ (StateGraph)│  │ (read-only)   │  │ (tool filtering) │   │
│  └──────┬─────┘  └────────────────┘  └──────────────────┘   │
│         │                                                     │
│  ┌──────▼──────────────────────────────────────────────────┐ │
│  │              SSE_Stream (event emitter)                   │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────┬─────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│                    Integration Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  LLM_Client  │  │  MCP_Client  │  │  Knowledge_Base  │   │
│  │  (Bedrock)   │  │ (LangChain)  │  │  (Bedrock KB)    │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└──────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│                   Persistence Layer                            │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Conversation_Store (SQLAlchemy async + asyncpg + PG)    │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## Project Structure

```
talksuite-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, lifespan, CORS
│   ├── config.py                # Pydantic Settings (env-based config)
│   ├── dependencies.py          # User_Provider and DB session deps
│   ├── api/
│   │   ├── __init__.py
│   │   ├── conversations.py     # Conversation CRUD router
│   │   └── messages.py          # Message submission + SSE router
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py          # Engine, session factory
│   │   ├── base.py              # Declarative base
│   │   ├── user.py              # User model
│   │   ├── conversation.py      # Conversation model
│   │   ├── message.py           # Message model
│   │   └── role_tool_map.py     # Role-to-tool mapping model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── conversation.py      # Pydantic request/response schemas
│   │   ├── message.py           # Message schemas
│   │   └── events.py            # SSE event schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── conversation_service.py  # Conversation CRUD logic
│   │   └── message_service.py       # Message persistence logic
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── orchestrator.py      # LangGraph StateGraph definition
│   │   ├── state.py             # Agent state schema
│   │   ├── nodes.py             # Graph node functions
│   │   ├── guardrails.py        # Guardrail_Engine
│   │   ├── role_filter.py       # Role-based tool filtering
│   │   └── stream.py            # SSE_Stream event emitter
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── llm_client.py        # AWS Bedrock Claude client
│   │   ├── mcp_client.py        # LangChain MCP adapter
│   │   └── knowledge_base.py    # Bedrock Knowledge Base client
│   └── utils/
│       ├── __init__.py
│       └── exceptions.py        # Custom exception classes
├── alembic/
│   ├── env.py
│   └── versions/
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
└── tests/
    ├── conftest.py
    ├── test_conversations.py
    ├── test_messages.py
    ├── test_guardrails.py
    ├── test_role_filter.py
    └── test_agent.py
```

## Component Design

### 1. Configuration (`app/config.py`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/talksuite"

    # AWS Bedrock
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    bedrock_knowledge_base_id: str = ""

    # MCP
    netsuite_mcp_url: str = "http://localhost:8080"

    # App
    app_env: str = "development"
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

### 2. Database Models (`app/models/`)

```python
# app/models/base.py
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })

# app/models/user.py
import uuid
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False, default="viewer")

# app/models/conversation.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False, default="New Conversation")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

# app/models/message.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from app.models.base import Base

class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(String, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    conversation = relationship("Conversation", back_populates="messages")

# app/models/role_tool_map.py
import uuid
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base

class RoleToolMap(Base):
    __tablename__ = "role_tool_map"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String, nullable=False, index=True)
    tool_name = Column(String, nullable=False)
```

### 3. Database Session (`app/models/database.py`)

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
```

### 4. Pydantic Schemas (`app/schemas/`)

```python
# app/schemas/conversation.py
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

class ConversationCreate(BaseModel):
    title: str = "New Conversation"

class ConversationResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

class ConversationDetailResponse(ConversationResponse):
    messages: list["MessageResponse"]

# app/schemas/message.py
from datetime import datetime
from uuid import UUID
from typing import Any
from pydantic import BaseModel

class MessageCreate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    created_at: datetime

# app/schemas/events.py
from typing import Any
from pydantic import BaseModel

class SSEEvent(BaseModel):
    event: str  # "thinking" | "tool_call" | "tool_result" | "text_chunk" | "done"
    data: dict[str, Any]

class ToolCallEvent(BaseModel):
    tool_name: str
    input: dict[str, Any]

class ToolResultEvent(BaseModel):
    tool_name: str
    result_summary: str

class TextChunkEvent(BaseModel):
    text: str

class DoneEvent(BaseModel):
    message_id: str
```

### 5. User Provider (`app/dependencies.py`)

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db_session
from app.models.user import User
from app.config import settings
import uuid

HARDCODED_TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

class UserProvider:
    """Resolves user identity. Swappable dependency for future auth."""

    async def __call__(self, db: AsyncSession = Depends(get_db_session)) -> User:
        if settings.app_env == "development":
            return User(
                id=HARDCODED_TEST_USER_ID,
                email="test@talksuite.dev",
                name="Test User",
                role="admin",
            )
        # Future: extract from JWT/session
        raise NotImplementedError("Auth not implemented")

get_current_user = UserProvider()
```

### 6. Conversation Service (`app/services/conversation_service.py`)

```python
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from app.models.conversation import Conversation
from app.models.user import User

class ConversationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user: User, title: str = "New Conversation") -> Conversation:
        conversation = Conversation(user_id=user.id, title=title)
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def list_for_user(self, user: User) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(desc(Conversation.updated_at))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_with_messages(self, conversation_id: UUID, user: User) -> Conversation | None:
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id, Conversation.user_id == user.id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, conversation_id: UUID, user: User) -> bool:
        conversation = await self.get_with_messages(conversation_id, user)
        if not conversation:
            return False
        await self.db.delete(conversation)
        await self.db.commit()
        return True
```

### 7. API Router — Conversations (`app/api/conversations.py`)

```python
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user
from app.models.database import get_db_session
from app.models.user import User
from app.schemas.conversation import ConversationCreate, ConversationResponse, ConversationDetailResponse
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])

@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConversationResponse)
async def create_conversation(
    body: ConversationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = ConversationService(db)
    conversation = await service.create(user, body.title)
    return conversation

@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = ConversationService(db)
    return await service.list_for_user(user)

@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = ConversationService(db)
    conversation = await service.get_with_messages(conversation_id, user)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation

@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = ConversationService(db)
    deleted = await service.delete(conversation_id, user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
```

### 8. Agent Orchestrator (`app/agent/orchestrator.py`)

The agent uses LangGraph's StateGraph to define the execution loop:

```python
from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.nodes import reason_node, guardrail_node, execute_node, respond_node

def build_agent_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("reason", reason_node)
    graph.add_node("guardrail_check", guardrail_node)
    graph.add_node("execute", execute_node)
    graph.add_node("respond", respond_node)

    graph.set_entry_point("reason")

    graph.add_conditional_edges(
        "reason",
        lambda state: "guardrail_check" if state.pending_tool_calls else "respond",
    )
    graph.add_conditional_edges(
        "guardrail_check",
        lambda state: "execute" if state.guardrail_approved else "reason",
    )
    graph.add_edge("execute", "reason")
    graph.add_edge("respond", END)

    return graph.compile()
```

### 9. Agent State (`app/agent/state.py`)

```python
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    id: str

@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    content: str

@dataclass
class AgentState:
    conversation_id: UUID
    messages: list[dict[str, Any]] = field(default_factory=list)
    pending_tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    guardrail_approved: bool = False
    guardrail_error: str | None = None
    final_response: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    user_role: str = ""
```

### 10. Guardrail Engine (`app/agent/guardrails.py`)

```python
from app.agent.state import ToolCall

# Tools known to perform write operations
WRITE_TOOL_PATTERNS = [
    "create", "update", "delete", "insert", "modify", "remove",
    "post", "put", "patch", "write", "set", "add",
]

class GuardrailEngine:
    """Validates all tool calls against read-only policy and role permissions."""

    def __init__(self, allowed_tools: list[str]):
        self.allowed_tools = allowed_tools

    def validate(self, tool_call: ToolCall) -> tuple[bool, str | None]:
        """
        Returns (approved, error_message).
        Checks: 1) role permission, 2) read-only policy.
        """
        # Check role-based permission
        if tool_call.name not in self.allowed_tools:
            return False, f"Tool '{tool_call.name}' is not permitted for your role."

        # Check read-only policy
        if self._is_write_operation(tool_call):
            return False, f"Write operation '{tool_call.name}' is blocked by read-only policy."

        return True, None

    def _is_write_operation(self, tool_call: ToolCall) -> bool:
        tool_lower = tool_call.name.lower()
        return any(pattern in tool_lower for pattern in WRITE_TOOL_PATTERNS)
```

### 11. Role Filter (`app/agent/role_filter.py`)

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.role_tool_map import RoleToolMap

class RoleFilter:
    """Filters tool definitions based on user role."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_allowed_tools(self, role: str) -> list[str]:
        stmt = select(RoleToolMap.tool_name).where(RoleToolMap.role == role)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def filter_tools(self, all_tools: list[dict], allowed_tool_names: list[str]) -> list[dict]:
        """Return only tools whose name is in the allowed set."""
        if not allowed_tool_names:
            return []
        return [t for t in all_tools if t.get("name") in allowed_tool_names]
```

### 12. SSE Stream (`app/agent/stream.py`)

```python
import json
from typing import Any, AsyncGenerator
from app.schemas.events import SSEEvent

class SSEStream:
    """Accumulates and yields SSE events during agent processing."""

    def __init__(self):
        self._events: list[SSEEvent] = []
        self._closed = False

    def emit_thinking(self):
        self._events.append(SSEEvent(event="thinking", data={"status": "reasoning"}))

    def emit_tool_call(self, tool_name: str, input_params: dict[str, Any]):
        self._events.append(SSEEvent(
            event="tool_call",
            data={"tool_name": tool_name, "input": input_params},
        ))

    def emit_tool_result(self, tool_name: str, result_summary: str):
        self._events.append(SSEEvent(
            event="tool_result",
            data={"tool_name": tool_name, "result_summary": result_summary},
        ))

    def emit_text_chunk(self, text: str):
        self._events.append(SSEEvent(event="text_chunk", data={"text": text}))

    def emit_done(self, message_id: str):
        self._events.append(SSEEvent(event="done", data={"message_id": message_id}))
        self._closed = True

    def close(self):
        self._closed = True

    async def generate(self) -> AsyncGenerator[str, None]:
        """Yields SSE-formatted strings for streaming."""
        sent = 0
        while not self._closed or sent < len(self._events):
            while sent < len(self._events):
                event = self._events[sent]
                yield f"event: {event.event}\ndata: {json.dumps(event.data)}\n\n"
                sent += 1
```

### 13. Messages Router with SSE (`app/api/messages.py`)

```python
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user
from app.models.database import get_db_session
from app.models.user import User
from app.schemas.message import MessageCreate
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.agent.orchestrator import build_agent_graph
from app.agent.stream import SSEStream
from app.agent.role_filter import RoleFilter
from app.agent.guardrails import GuardrailEngine

router = APIRouter(prefix="/conversations/{conversation_id}/messages", tags=["messages"])

@router.post("")
async def send_message(
    conversation_id: UUID,
    body: MessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # Verify conversation ownership
    conv_service = ConversationService(db)
    conversation = await conv_service.get_with_messages(conversation_id, user)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Persist user message
    msg_service = MessageService(db)
    await msg_service.create_user_message(conversation_id, body.content)

    # Get allowed tools for role
    role_filter = RoleFilter(db)
    allowed_tools = await role_filter.get_allowed_tools(user.role)

    # Build agent and stream
    sse_stream = SSEStream()

    async def process_and_stream():
        agent = build_agent_graph()
        # Run agent with conversation history + new message
        # Agent emits events to sse_stream during processing
        # ... (agent invocation with streaming)
        async for chunk in sse_stream.generate():
            yield chunk

    return StreamingResponse(
        process_and_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

### 14. LLM Client (`app/clients/llm_client.py`)

```python
from typing import Any
import boto3
from app.config import settings

class LLMClient:
    """Async wrapper around AWS Bedrock for Claude invocations."""

    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        self.model_id = settings.bedrock_model_id

    async def invoke(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str = "",
    ) -> dict[str, Any]:
        """Invoke Claude via Bedrock Converse API with optional tools."""
        request = {
            "modelId": self.model_id,
            "messages": messages,
        }
        if system_prompt:
            request["system"] = [{"text": system_prompt}]
        if tools:
            request["toolConfig"] = {"tools": tools}

        # Use async invocation (aioboto3 or run_in_executor)
        response = await self._async_invoke(request)
        return response

    async def invoke_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str = "",
    ):
        """Stream Claude response via Bedrock Converse Stream API."""
        request = {
            "modelId": self.model_id,
            "messages": messages,
        }
        if system_prompt:
            request["system"] = [{"text": system_prompt}]
        if tools:
            request["toolConfig"] = {"tools": tools}

        async for event in self._async_invoke_stream(request):
            yield event

    async def _async_invoke(self, request: dict) -> dict:
        # Implementation using aioboto3 or asyncio.to_thread
        ...

    async def _async_invoke_stream(self, request: dict):
        # Implementation using Bedrock ConverseStream
        ...
```

### 15. MCP Client (`app/clients/mcp_client.py`)

```python
from typing import Any
from langchain_mcp_adapters.client import MultiServerMCPClient
from app.config import settings

class MCPClient:
    """LangChain MCP adapter for NetSuite MCP Server communication."""

    def __init__(self):
        self.mcp_url = settings.netsuite_mcp_url
        self._client: MultiServerMCPClient | None = None

    async def initialize(self):
        """Initialize MCP connection."""
        self._client = MultiServerMCPClient(
            {"netsuite": {"url": self.mcp_url, "transport": "sse"}}
        )
        await self._client.__aenter__()

    async def get_tools(self) -> list[dict[str, Any]]:
        """Retrieve available tool definitions from MCP server."""
        if not self._client:
            await self.initialize()
        tools = self._client.get_tools()
        return [self._to_tool_def(t) for t in tools]

    async def execute_tool(self, tool_name: str, input_params: dict[str, Any]) -> str:
        """Execute a tool on the MCP server and return the result."""
        if not self._client:
            await self.initialize()
        result = await self._client.invoke_tool(tool_name, input_params)
        return str(result)

    def _to_tool_def(self, tool) -> dict[str, Any]:
        """Convert LangChain tool to Bedrock tool definition format."""
        return {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": {"json": tool.args_schema.schema() if tool.args_schema else {}},
        }

    async def close(self):
        if self._client:
            await self._client.__aexit__(None, None, None)
```

### 16. Knowledge Base Client (`app/clients/knowledge_base.py`)

```python
from typing import Any
import boto3
from app.config import settings

class KnowledgeBaseClient:
    """AWS Bedrock Knowledge Base retrieval client."""

    def __init__(self):
        self.client = boto3.client("bedrock-agent-runtime", region_name=settings.aws_region)
        self.knowledge_base_id = settings.bedrock_knowledge_base_id

    async def retrieve(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Retrieve relevant passages from the knowledge base."""
        response = await self._async_retrieve({
            "knowledgeBaseId": self.knowledge_base_id,
            "retrievalQuery": {"text": query},
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {"numberOfResults": max_results}
            },
        })

        passages = []
        for result in response.get("retrievalResults", []):
            passages.append({
                "text": result["content"]["text"],
                "score": result.get("score", 0.0),
                "source": result.get("location", {}).get("s3Location", {}).get("uri", ""),
            })
        return passages

    async def _async_retrieve(self, request: dict) -> dict:
        # Implementation using aioboto3 or asyncio.to_thread
        ...
```

### 17. Application Factory (`app/main.py`)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.conversations import router as conversations_router
from app.api.messages import router as messages_router
from app.clients.mcp_client import MCPClient
from app.config import settings

mcp_client = MCPClient()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await mcp_client.initialize()
    yield
    # Shutdown
    await mcp_client.close()

def create_app() -> FastAPI:
    app = FastAPI(
        title="TalkSuite Backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(conversations_router)
    app.include_router(messages_router)

    return app

app = create_app()
```

## Data Models

### Entity Relationship Diagram

```
┌──────────────┐       ┌───────────────────┐       ┌──────────────────┐
│    users     │       │   conversations   │       │     messages     │
├──────────────┤       ├───────────────────┤       ├──────────────────┤
│ id (PK, UUID)│◄──────│ user_id (FK)      │       │ id (PK, UUID)    │
│ email        │       │ id (PK, UUID)     │◄──────│ conversation_id  │
│ name         │       │ title             │       │   (FK)           │
│ role         │       │ created_at        │       │ role             │
└──────────────┘       │ updated_at        │       │ content          │
                       └───────────────────┘       │ tool_calls (JSON)│
                                                   │ created_at       │
┌──────────────────┐                               └──────────────────┘
│  role_tool_map   │
├──────────────────┤
│ id (PK, UUID)    │
│ role             │
│ tool_name        │
└──────────────────┘
```

### Data Constraints

- `users.email` — unique, not null
- `users.role` — not null, default "viewer"
- `conversations.user_id` — FK to `users.id`, not null, CASCADE on delete
- `messages.conversation_id` — FK to `conversations.id`, not null, CASCADE on delete
- `messages.role` — one of "user", "assistant"
- `messages.tool_calls` — nullable JSON array
- `role_tool_map` — composite uniqueness on (role, tool_name)

## Interface Contracts

### REST API Endpoints

| Method | Path | Request Body | Response | Status |
|--------|------|-------------|----------|--------|
| POST | /conversations | `{title?: string}` | `ConversationResponse` | 201 |
| GET | /conversations | — | `ConversationResponse[]` | 200 |
| GET | /conversations/{id} | — | `ConversationDetailResponse` | 200 |
| DELETE | /conversations/{id} | — | — | 204 |
| POST | /conversations/{id}/messages | `{content: string}` | SSE stream | 200 |

### SSE Event Schema

```
event: thinking
data: {"status": "reasoning"}

event: tool_call
data: {"tool_name": "netsuite_get_invoices", "input": {"customer_id": "123"}}

event: tool_result
data: {"tool_name": "netsuite_get_invoices", "result_summary": "Found 5 invoices totaling $12,450"}

event: text_chunk
data: {"text": "Based on the invoice data, "}

event: done
data: {"message_id": "uuid-here"}
```

## Error Handling

| Scenario | HTTP Status | Response Body |
|----------|------------|---------------|
| Conversation not found / not owned | 404 | `{"detail": "Conversation not found"}` |
| Database unreachable | 503 | `{"detail": "Service temporarily unavailable"}` |
| Invalid request body | 422 | FastAPI validation error format |
| Write operation blocked | 403 (in SSE) | Emitted as error event in stream |
| Tool not permitted for role | 403 (in SSE) | Emitted as error event in stream |
| No KB results found | 200 | Normal text response indicating no docs found |

## Cancellation Handling

When the SSE client disconnects:
1. FastAPI detects the closed connection via `Request.is_disconnected()`
2. The streaming generator checks disconnection state between events
3. The agent graph is cancelled via `asyncio.Task.cancel()`
4. Cleanup occurs within 5 seconds timeout

## Docker Compose Configuration

```yaml
version: "3.9"
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: talksuite
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/talksuite
    depends_on:
      - db
    env_file:
      - .env

volumes:
  pgdata:
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Conversation ownership isolation

*For any* two distinct users A and B, and *for any* conversation owned by user A, when user B attempts to retrieve, delete, or post a message to that conversation, the system SHALL return a 404 response.

**Validates: Requirements 3.3, 4.3, 5.4**

### Property 2: Conversation listing order

*For any* user with multiple conversations having distinct `updated_at` timestamps, the list response SHALL return conversations in strictly descending order of `updated_at`.

**Validates: Requirements 2.1**

### Property 3: Message ordering in conversation retrieval

*For any* conversation containing multiple messages with distinct `created_at` timestamps, retrieving that conversation SHALL return messages in strictly ascending order of `created_at`.

**Validates: Requirements 3.1**

### Property 4: Conversation creation response completeness

*For any* valid conversation creation request, the response SHALL contain a non-null `id`, `title`, and `created_at` field, and the HTTP status SHALL be 201.

**Validates: Requirements 1.2**

### Property 5: Deletion completeness

*For any* conversation with associated messages, after successful deletion the system SHALL return 204 with no body, and subsequent retrieval of that conversation or its messages SHALL return 404 or empty.

**Validates: Requirements 4.1, 4.2**

### Property 6: Message persistence before agent invocation

*For any* valid message submission to an existing conversation, the user message SHALL be persisted in the Conversation_Store before the Agent_Orchestrator begins processing.

**Validates: Requirements 5.1**

### Property 7: Complete message history passed to agent

*For any* conversation with N existing messages, when a new message is submitted, the Agent_Orchestrator SHALL receive exactly N+1 messages (full history plus the new user message).

**Validates: Requirements 5.2**

### Property 8: SSE event type validity

*For any* SSE stream emitted during agent processing, every event type SHALL be one of: "thinking", "tool_call", "tool_result", "text_chunk", or "done".

**Validates: Requirements 6.2**

### Property 9: SSE event payload completeness

*For any* "tool_call" event, the data SHALL contain `tool_name` and `input` fields. *For any* "tool_result" event, the data SHALL contain `tool_name` and `result_summary` fields.

**Validates: Requirements 6.3, 6.4**

### Property 10: Universal guardrail evaluation

*For any* tool call produced by the LLM_Client, regardless of tool name or parameters, the Guardrail_Engine SHALL evaluate that tool call before execution occurs.

**Validates: Requirements 7.2, 10.1, 10.4**

### Property 11: Write operation blocking

*For any* tool call whose name or semantics indicate a write operation, the Guardrail_Engine SHALL block execution and return an error message indicating the operation is not permitted.

**Validates: Requirements 10.2**

### Property 12: Blocked tool call feedback

*For any* tool call blocked by the Guardrail_Engine, the blocked status and error message SHALL be passed back to the LLM_Client for generating a user-facing explanation.

**Validates: Requirements 10.3**

### Property 13: Role-based tool filtering is a subset operation

*For any* user role and the full set of available tools, the tools presented to the LLM_Client SHALL be a subset of (or equal to) the Allowed_Tools defined in role_tool_map for that role.

**Validates: Requirements 11.1, 11.2**

### Property 14: Unauthorized tool call blocking

*For any* tool call referencing a tool name that is not in the current user's Allowed_Tools set, the Guardrail_Engine SHALL block the call and return an insufficient permissions error.

**Validates: Requirements 11.4**

### Property 15: User identity resolution completeness

*For any* resolved user object, it SHALL contain non-null values for `id`, `email`, `name`, and `role`.

**Validates: Requirements 12.1, 12.2**

### Property 16: Tool calls JSON round-trip

*For any* valid `tool_calls` data structure (list of objects with name, input, and id fields), storing it in the messages table and subsequently retrieving it SHALL produce an equivalent data structure.

**Validates: Requirements 13.4**

### Property 17: Configuration loading from environment

*For any* valid set of environment variables matching the Settings schema, the configuration loader SHALL produce a Settings object with values corresponding to those environment variables.

**Validates: Requirements 14.3**

### Property 18: Sequential tool call individual guardrail processing

*For any* agent turn producing N > 1 tool calls, each tool call SHALL be individually processed through the guardrail check step (N separate validations, not a batch).

**Validates: Requirements 7.5**
