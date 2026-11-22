from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.conversations import router as conversations_router
from app.api.messages import router as messages_router
from app.api.transcribe import router as transcribe_router
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.accounts import router as accounts_router
from app.clients.llm_client import LLMClient
from app.clients.mcp_manager import MCPManager
from app.clients.knowledge_base import KnowledgeBaseClient
from app.clients.transcribe_client import TranscribeClient
from app.config import settings
from app.utils.exceptions import (
    DatabaseUnavailableError,
    AuthenticationError,
    database_unavailable_handler,
    authentication_error_handler,
)

# Global clients (initialized during lifespan)
mcp_manager = MCPManager()  # per-account MCP clients
llm_client = LLMClient()
kb_client = KnowledgeBaseClient()
transcribe_client = TranscribeClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle — startup and shutdown."""
    print(f"[TalkSuite] Starting in {settings.app_env} mode")
    print(f"[TalkSuite] Database: {settings.database_url.split('@')[-1]}")
    print("[TalkSuite] MCP clients are created per-account on demand")

    yield

    # Shutdown — close all cached MCP clients
    await mcp_manager.close_all()
    print("[TalkSuite] Shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="TalkSuite Backend",
        description="AI-powered NetSuite assistant for the Opus team",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    cors_origins = (
        [settings.frontend_url]
        if settings.frontend_url
        else ["*"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    app.add_exception_handler(DatabaseUnavailableError, database_unavailable_handler)
    app.add_exception_handler(AuthenticationError, authentication_error_handler)

    # Routers
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(accounts_router)
    app.include_router(conversations_router)
    app.include_router(messages_router)
    app.include_router(transcribe_router)

    # Health check
    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "healthy", "service": "talksuite-backend"}

    return app


app = create_app()
