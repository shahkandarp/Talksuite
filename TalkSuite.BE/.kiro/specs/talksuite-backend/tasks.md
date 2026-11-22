# Implementation Plan: TalkSuite Backend

## Overview

Implement a FastAPI-based conversational AI backend with LangGraph agent orchestration, PostgreSQL persistence, SSE streaming, and integration with AWS Bedrock (Claude LLM + Knowledge Bases) and a NetSuite MCP Server. The implementation follows a bottom-up approach: infrastructure and models first, then services and API layer, followed by the agent orchestration layer, and finally integration wiring and Docker configuration.

## Tasks

- [x] 1. Project scaffolding and configuration
  - [x] 1.1 Create project structure and install dependencies
    - Create `requirements.txt` with: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, boto3, aioboto3, langgraph, langchain-mcp-adapters, python-dotenv, sse-starlette
    - Create the directory structure: `app/`, `app/api/`, `app/models/`, `app/schemas/`, `app/services/`, `app/agent/`, `app/clients/`, `app/utils/`, `alembic/`, `tests/`
    - Add `__init__.py` files to all packages
    - _Requirements: 14.1, 14.2, 14.3_

  - [ ] 1.2 Implement configuration module (`app/config.py`)
    - Create `Settings` class using `pydantic_settings.BaseSettings`
    - Define fields: `database_url`, `aws_region`, `bedrock_model_id`, `bedrock_knowledge_base_id`, `netsuite_mcp_url`, `app_env`, `debug`
    - Configure `.env` file loading
    - Create `.env.example` with all required variables documented
    - _Requirements: 14.3_

  - [ ]* 1.3 Write property test for configuration loading
    - **Property 17: Configuration loading from environment**
    - **Validates: Requirements 14.3**

- [ ] 2. Database models and migrations
  - [ ] 2.1 Implement SQLAlchemy base and models
    - Create `app/models/base.py` with `DeclarativeBase` and naming conventions
    - Create `app/models/user.py` with `User` model (id UUID PK, email unique, name, role)
    - Create `app/models/conversation.py` with `Conversation` model (id UUID PK, user_id FK, title, created_at, updated_at) and relationships
    - Create `app/models/message.py` with `Message` model (id UUID PK, conversation_id FK, role, content, tool_calls JSON, created_at) and relationships
    - Create `app/models/role_tool_map.py` with `RoleToolMap` model (id UUID PK, role, tool_name) with composite uniqueness
    - Create `app/models/__init__.py` exporting all models
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ] 2.2 Implement database session factory (`app/models/database.py`)
    - Create async engine with `create_async_engine` using config `database_url`
    - Create `async_sessionmaker` factory
    - Implement `get_db_session` async generator for dependency injection
    - _Requirements: 13.6, 15.2_

  - [ ] 2.3 Set up Alembic for async migrations
    - Initialize Alembic with `alembic init alembic`
    - Configure `alembic/env.py` for async SQLAlchemy engine
    - Import all models in env.py for autogenerate support
    - Generate initial migration with all tables (users, conversations, messages, role_tool_map)
    - Add seed data migration for hardcoded test user and default role_tool_map entries
    - _Requirements: 13.5, 14.4_

  - [ ]* 2.4 Write property test for tool_calls JSON round-trip
    - **Property 16: Tool calls JSON round-trip**
    - **Validates: Requirements 13.4**

- [ ] 3. Pydantic schemas
  - [ ] 3.1 Implement request/response schemas
    - Create `app/schemas/conversation.py` with `ConversationCreate`, `ConversationResponse`, `ConversationDetailResponse`
    - Create `app/schemas/message.py` with `MessageCreate`, `MessageResponse`
    - Create `app/schemas/events.py` with `SSEEvent`, `ToolCallEvent`, `ToolResultEvent`, `TextChunkEvent`, `DoneEvent`
    - _Requirements: 1.2, 2.2, 3.2, 6.2, 6.3, 6.4_

- [ ] 4. User provider and dependencies
  - [ ] 4.1 Implement User Provider (`app/dependencies.py`)
    - Create `UserProvider` class as a FastAPI callable dependency
    - Implement hardcoded test user return for `app_env == "development"`
    - Structure for future auth replacement (raise `NotImplementedError` for non-dev)
    - Define `get_current_user` instance
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [ ]* 4.2 Write property test for user identity resolution completeness
    - **Property 15: User identity resolution completeness**
    - **Validates: Requirements 12.1, 12.2**

- [ ] 5. Conversation service and API
  - [ ] 5.1 Implement conversation service (`app/services/conversation_service.py`)
    - Implement `create()` — create conversation record for user
    - Implement `list_for_user()` — query conversations ordered by `updated_at` descending
    - Implement `get_with_messages()` — load conversation with messages (selectinload), verify user ownership
    - Implement `delete()` — cascade delete conversation and messages
    - _Requirements: 1.1, 2.1, 3.1, 4.1_

  - [ ] 5.2 Implement conversations API router (`app/api/conversations.py`)
    - POST `/conversations` — create conversation, return 201
    - GET `/conversations` — list conversations for current user
    - GET `/conversations/{id}` — get conversation with messages, return 404 if not found/owned
    - DELETE `/conversations/{id}` — delete conversation, return 204, or 404
    - Handle database unreachable with 503 error
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4_

  - [ ]* 5.3 Write property tests for conversation operations
    - **Property 1: Conversation ownership isolation**
    - **Property 2: Conversation listing order**
    - **Property 3: Message ordering in conversation retrieval**
    - **Property 4: Conversation creation response completeness**
    - **Property 5: Deletion completeness**
    - **Validates: Requirements 1.2, 2.1, 3.1, 3.3, 4.1, 4.2, 4.3, 5.4**

- [ ] 6. Checkpoint - Persistence layer and CRUD API
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Guardrail engine and role filter
  - [ ] 7.1 Implement guardrail engine (`app/agent/guardrails.py`)
    - Define `WRITE_TOOL_PATTERNS` list (create, update, delete, insert, modify, remove, post, put, patch, write, set, add)
    - Implement `GuardrailEngine` class with `validate(tool_call)` method
    - Check role-based permission (tool in allowed_tools)
    - Check read-only policy (pattern match on tool name)
    - Return tuple `(approved: bool, error_message: str | None)`
    - _Requirements: 10.1, 10.2, 10.4, 11.4_

  - [ ] 7.2 Implement role filter (`app/agent/role_filter.py`)
    - Implement `RoleFilter` class with async `get_allowed_tools(role)` querying `role_tool_map`
    - Implement `filter_tools(all_tools, allowed_tool_names)` to subset tool definitions
    - Return empty list when no entries exist for a role
    - _Requirements: 11.1, 11.2, 11.3_

  - [ ]* 7.3 Write property tests for guardrails
    - **Property 10: Universal guardrail evaluation**
    - **Property 11: Write operation blocking**
    - **Property 12: Blocked tool call feedback**
    - **Property 14: Unauthorized tool call blocking**
    - **Validates: Requirements 7.2, 10.1, 10.2, 10.3, 10.4, 11.4**

  - [ ]* 7.4 Write property test for role-based tool filtering
    - **Property 13: Role-based tool filtering is a subset operation**
    - **Validates: Requirements 11.1, 11.2**

- [ ] 8. Integration clients
  - [ ] 8.1 Implement LLM client (`app/clients/llm_client.py`)
    - Create `LLMClient` class with async `invoke()` and `invoke_stream()` methods
    - Use `aioboto3` or `asyncio.to_thread` for async Bedrock calls
    - Format messages for Bedrock Converse API
    - Support tool configuration and system prompt
    - _Requirements: 15.3, 8.1_

  - [ ] 8.2 Implement MCP client (`app/clients/mcp_client.py`)
    - Create `MCPClient` class using `langchain-mcp-adapters` `MultiServerMCPClient`
    - Implement `initialize()` for MCP connection setup
    - Implement `get_tools()` to retrieve tool definitions and convert to Bedrock format
    - Implement `execute_tool(tool_name, input_params)` for tool invocation
    - Implement `close()` for cleanup
    - _Requirements: 8.2, 15.4_

  - [ ] 8.3 Implement Knowledge Base client (`app/clients/knowledge_base.py`)
    - Create `KnowledgeBaseClient` class with async `retrieve(query, max_results)` method
    - Call Bedrock Agent Runtime `Retrieve` API
    - Parse and return passages with text, score, and source
    - _Requirements: 9.1, 9.2_

- [ ] 9. Agent orchestration
  - [ ] 9.1 Implement agent state (`app/agent/state.py`)
    - Define `ToolCall` dataclass (name, input, id)
    - Define `ToolResult` dataclass (tool_call_id, name, content)
    - Define `AgentState` dataclass with all fields: conversation_id, messages, pending_tool_calls, tool_results, guardrail_approved, guardrail_error, final_response, allowed_tools, user_role
    - _Requirements: 7.1_

  - [ ] 9.2 Implement SSE stream emitter (`app/agent/stream.py`)
    - Create `SSEStream` class with event emission methods: `emit_thinking()`, `emit_tool_call()`, `emit_tool_result()`, `emit_text_chunk()`, `emit_done()`
    - Implement `generate()` async generator that yields SSE-formatted strings
    - Implement `close()` for cancellation support
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 9.3 Write property tests for SSE events
    - **Property 8: SSE event type validity**
    - **Property 9: SSE event payload completeness**
    - **Validates: Requirements 6.2, 6.3, 6.4**

  - [ ] 9.4 Implement agent graph nodes (`app/agent/nodes.py`)
    - Implement `reason_node` — call LLM with messages and filtered tools, emit "thinking" event
    - Implement `guardrail_node` — validate each pending tool call via GuardrailEngine, emit blocked feedback to LLM
    - Implement `execute_node` — execute approved tool calls via MCP or KB client, emit "tool_call" and "tool_result" events
    - Implement `respond_node` — emit text chunks and "done" event, set final_response
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.3, 9.1, 9.2, 10.1, 10.2, 10.3_

  - [ ] 9.5 Implement LangGraph orchestrator (`app/agent/orchestrator.py`)
    - Build `StateGraph` with nodes: reason, guardrail_check, execute, respond
    - Set entry point to "reason"
    - Add conditional edges: reason → guardrail_check (if pending_tool_calls) or respond
    - Add conditional edges: guardrail_check → execute (if approved) or reason (if blocked)
    - Add edge: execute → reason (loop for multi-step)
    - Add edge: respond → END
    - Compile and return the graph
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 9.6 Write property test for sequential tool call processing
    - **Property 18: Sequential tool call individual guardrail processing**
    - **Validates: Requirements 7.5**

- [ ] 10. Message submission and streaming endpoint
  - [ ] 10.1 Implement message service (`app/services/message_service.py`)
    - Implement `create_user_message(conversation_id, content)` — persist user message
    - Implement `create_assistant_message(conversation_id, content, tool_calls)` — persist assistant response
    - Implement `get_conversation_messages(conversation_id)` — load full history ordered by created_at
    - _Requirements: 5.1, 5.3_

  - [ ] 10.2 Implement messages API router (`app/api/messages.py`)
    - POST `/conversations/{id}/messages` — verify ownership, persist user message, invoke agent, stream SSE response
    - Return `StreamingResponse` with `text/event-stream` content type
    - Include `Cache-Control: no-cache` and `X-Accel-Buffering: no` headers
    - Handle client disconnect — cancel agent processing within 5 seconds
    - Persist assistant response after completion
    - Return 404 for non-existent or non-owned conversations
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.5_

  - [ ]* 10.3 Write property tests for message submission
    - **Property 6: Message persistence before agent invocation**
    - **Property 7: Complete message history passed to agent**
    - **Validates: Requirements 5.1, 5.2**

- [ ] 11. Checkpoint - Agent orchestration and streaming
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Application wiring and Docker setup
  - [ ] 12.1 Implement application factory (`app/main.py`)
    - Create `create_app()` factory function
    - Configure CORS middleware (allow all origins for dev)
    - Register conversation and message routers
    - Implement `lifespan` context manager for MCP client startup/shutdown
    - _Requirements: 14.1, 14.2, 15.1_

  - [ ] 12.2 Implement custom exception handlers (`app/utils/exceptions.py`)
    - Define custom exception classes for database unavailable, auth errors
    - Register FastAPI exception handlers for 503 (DB unreachable) and standard errors
    - _Requirements: 1.3_

  - [ ] 12.3 Create Docker and Docker Compose configuration
    - Create `Dockerfile` — Python 3.11 base, install deps, copy app, run uvicorn
    - Create `docker-compose.yml` — PostgreSQL 16 + app services with proper networking
    - Configure environment variable pass-through and `.env` file support
    - Add health checks for PostgreSQL readiness
    - _Requirements: 14.1, 14.2, 14.3_

  - [ ] 12.4 Wire all components and verify startup
    - Ensure all imports resolve correctly in `app/main.py`
    - Verify lifespan manages MCP client lifecycle
    - Add startup log confirming database connectivity and MCP connection
    - Create a simple healthcheck endpoint (GET `/health`)
    - _Requirements: 14.1, 14.2, 15.1_

- [ ] 13. Final checkpoint - Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation uses Python 3.11+ with FastAPI async throughout
- All database operations use async SQLAlchemy with asyncpg driver
- AWS Bedrock is accessed via aioboto3 for true async support
- LangGraph StateGraph defines the agent loop with conditional edges

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "4.1"] },
    { "id": 3, "tasks": ["2.4", "4.2", "5.1"] },
    { "id": 4, "tasks": ["5.2", "7.1", "7.2"] },
    { "id": 5, "tasks": ["5.3", "7.3", "7.4", "8.1", "8.2", "8.3"] },
    { "id": 6, "tasks": ["9.1", "9.2"] },
    { "id": 7, "tasks": ["9.3", "9.4", "10.1"] },
    { "id": 8, "tasks": ["9.5", "9.6", "10.2"] },
    { "id": 9, "tasks": ["10.3", "12.1", "12.2"] },
    { "id": 10, "tasks": ["12.3", "12.4"] }
  ]
}
```
