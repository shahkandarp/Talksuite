# Requirements Document

## Introduction

TalkSuite Backend is a Python/FastAPI application that provides a conversational AI interface for querying NetSuite business data and help documentation. The system supports multi-conversation chat (similar to ChatGPT's sidebar), orchestrates an agentic LLM loop via LangGraph, and enforces read-only security guardrails on all tool interactions. Claude (via AWS Bedrock) handles intent understanding and response generation, routing queries to either a NetSuite MCP Server for live data or an AWS Bedrock Knowledge Base for help/docs answers. Responses are streamed to clients via Server-Sent Events (SSE).

## Glossary

- **Chat_API**: The FastAPI-based REST API layer that exposes conversation and message endpoints to clients.
- **Agent_Orchestrator**: The LangGraph-based agentic loop responsible for reasoning, tool calling, guardrail checking, execution, observation, and response generation.
- **LLM_Client**: The component that communicates with Claude via the AWS Bedrock API for intent understanding and response generation.
- **MCP_Client**: The LangChain MCP adapter that connects the Agent_Orchestrator to the NetSuite MCP Server for live data queries.
- **Knowledge_Base**: The AWS Bedrock Knowledge Bases service used for retrieval-augmented generation (RAG) to answer help and documentation questions.
- **Guardrail_Engine**: The security layer that validates every MCP tool call before execution, blocking any write operations.
- **Role_Filter**: The component that filters tool definitions based on the current user's role before presenting them to the LLM.
- **Conversation_Store**: The PostgreSQL-backed persistence layer for users, conversations, and messages using asyncpg and SQLAlchemy.
- **SSE_Stream**: The Server-Sent Events transport layer that streams structured response events to the client.
- **User_Provider**: The dependency injection component that resolves the current user identity, initially hardcoded for development and structured for future auth integration.
- **Allowed_Tools**: The set of MCP tools a user's role is permitted to invoke, as defined in the role_tool_map table.

## Requirements

### Requirement 1: Conversation Creation

**User Story:** As a user, I want to create a new conversation so that I can start a fresh chat session with its own history.

#### Acceptance Criteria

1. WHEN a POST request is received at /conversations, THE Chat_API SHALL create a new conversation record in the Conversation_Store associated with the current user.
2. WHEN a conversation is created successfully, THE Chat_API SHALL return the conversation identifier, title, and creation timestamp in the response body with HTTP status 201.
3. IF the Conversation_Store is unreachable, THEN THE Chat_API SHALL return an HTTP 503 response with an error message indicating the service is temporarily unavailable.

### Requirement 2: Conversation Listing

**User Story:** As a user, I want to list all my conversations so that I can see my chat history and switch between sessions.

#### Acceptance Criteria

1. WHEN a GET request is received at /conversations, THE Chat_API SHALL return all conversations belonging to the current user ordered by updated_at descending.
2. THE Chat_API SHALL include the conversation identifier, title, created_at, and updated_at fields for each conversation in the list response.
3. WHEN no conversations exist for the current user, THE Chat_API SHALL return an empty list with HTTP status 200.

### Requirement 3: Conversation Retrieval

**User Story:** As a user, I want to retrieve a specific conversation with its full message history so that I can review previous interactions.

#### Acceptance Criteria

1. WHEN a GET request is received at /conversations/{id}, THE Chat_API SHALL return the conversation record along with all associated messages ordered by created_at ascending.
2. THE Chat_API SHALL include the role, content, tool_calls, and created_at fields for each message in the response.
3. IF the requested conversation does not belong to the current user, THEN THE Chat_API SHALL return an HTTP 404 response.
4. IF the requested conversation identifier does not exist, THEN THE Chat_API SHALL return an HTTP 404 response.

### Requirement 4: Conversation Deletion

**User Story:** As a user, I want to delete a conversation so that I can remove chat sessions I no longer need.

#### Acceptance Criteria

1. WHEN a DELETE request is received at /conversations/{id}, THE Chat_API SHALL remove the conversation and all associated messages from the Conversation_Store.
2. WHEN a conversation is deleted successfully, THE Chat_API SHALL return an HTTP 204 response with no body.
3. IF the requested conversation does not belong to the current user, THEN THE Chat_API SHALL return an HTTP 404 response.
4. IF the requested conversation identifier does not exist, THEN THE Chat_API SHALL return an HTTP 404 response.

### Requirement 5: Message Submission and Agent Processing

**User Story:** As a user, I want to send a message in a conversation so that the AI agent processes my query and returns a relevant response.

#### Acceptance Criteria

1. WHEN a POST request is received at /conversations/{id}/messages with a text content body, THE Chat_API SHALL persist the user message in the Conversation_Store and invoke the Agent_Orchestrator.
2. THE Agent_Orchestrator SHALL load the full message history for the conversation and pass the history along with the new user message to the LLM_Client.
3. WHEN the Agent_Orchestrator completes processing, THE Chat_API SHALL persist the assistant response message (including any tool_calls metadata) in the Conversation_Store.
4. IF the requested conversation does not belong to the current user, THEN THE Chat_API SHALL return an HTTP 404 response.
5. IF the requested conversation identifier does not exist, THEN THE Chat_API SHALL return an HTTP 404 response.

### Requirement 6: SSE Response Streaming

**User Story:** As a user, I want to receive streamed responses with structured events so that the frontend can render progressive status indicators and partial results.

#### Acceptance Criteria

1. WHEN the Agent_Orchestrator begins processing a user message, THE SSE_Stream SHALL emit a stream of structured events to the client with content-type text/event-stream.
2. THE SSE_Stream SHALL emit events of type "thinking" when the LLM_Client is reasoning, "tool_call" when a tool invocation is initiated, "tool_result" when a tool invocation completes, "text_chunk" for each incremental text segment of the response, and "done" when processing is complete.
3. WHEN a "tool_call" event is emitted, THE SSE_Stream SHALL include the tool name and input parameters in the event data.
4. WHEN a "tool_result" event is emitted, THE SSE_Stream SHALL include the tool name and a summary of the result in the event data.
5. IF the SSE connection is interrupted by the client, THEN THE Agent_Orchestrator SHALL cancel the in-progress processing within 5 seconds.

### Requirement 7: Agent Orchestration Loop

**User Story:** As a developer, I want the agent to follow a structured reasoning loop so that tool calls are executed safely and responses are grounded in retrieved data.

#### Acceptance Criteria

1. THE Agent_Orchestrator SHALL execute a loop of: reason → tool_call → guardrail_check → execute → observe → respond.
2. WHEN the LLM_Client determines that a tool call is needed, THE Agent_Orchestrator SHALL pass the proposed tool call to the Guardrail_Engine before execution.
3. WHEN the Guardrail_Engine approves a tool call, THE Agent_Orchestrator SHALL execute the tool call via the MCP_Client or Knowledge_Base and pass the result back to the LLM_Client.
4. WHEN the LLM_Client determines that no further tool calls are needed, THE Agent_Orchestrator SHALL emit the final text response to the SSE_Stream.
5. IF the LLM_Client produces multiple sequential tool calls, THEN THE Agent_Orchestrator SHALL process each tool call through the guardrail_check and execute steps individually.

### Requirement 8: Intent Routing to NetSuite MCP

**User Story:** As a user, I want to ask questions about live business data so that I can get real-time answers from NetSuite.

#### Acceptance Criteria

1. WHEN the LLM_Client identifies a user query as requiring live business data, THE Agent_Orchestrator SHALL route the tool call to the MCP_Client connected to the NetSuite MCP Server.
2. THE MCP_Client SHALL use the LangChain MCP adapter to communicate with the NetSuite MCP Server.
3. WHEN the MCP_Client receives a response from the NetSuite MCP Server, THE Agent_Orchestrator SHALL pass the response data to the LLM_Client for answer synthesis.

### Requirement 9: Intent Routing to Knowledge Base

**User Story:** As a user, I want to ask help and documentation questions so that I can get answers grounded in company knowledge.

#### Acceptance Criteria

1. WHEN the LLM_Client identifies a user query as requiring help or documentation content, THE Agent_Orchestrator SHALL route the query to the Knowledge_Base via AWS Bedrock Knowledge Bases retrieval.
2. WHEN the Knowledge_Base returns retrieved passages, THE Agent_Orchestrator SHALL pass the retrieved passages to the LLM_Client for answer synthesis.
3. IF the Knowledge_Base returns no relevant passages, THEN THE LLM_Client SHALL generate a response indicating that no relevant documentation was found.

### Requirement 10: Read-Only Guardrail Enforcement

**User Story:** As a system administrator, I want all MCP tool calls validated for read-only access so that no write operations can be executed against NetSuite.

#### Acceptance Criteria

1. WHEN the Agent_Orchestrator receives a tool call from the LLM_Client, THE Guardrail_Engine SHALL validate the tool call against a read-only policy before execution.
2. IF the Guardrail_Engine determines a tool call would perform a write operation, THEN THE Guardrail_Engine SHALL block the tool call and return an error indicating the operation is not permitted.
3. WHEN the Guardrail_Engine blocks a tool call, THE Agent_Orchestrator SHALL pass the blocked status back to the LLM_Client so the LLM_Client can generate an appropriate user-facing explanation.
4. THE Guardrail_Engine SHALL evaluate every MCP tool call without exception, regardless of the tool name or parameters.

### Requirement 11: Role-Based Tool Filtering

**User Story:** As a system administrator, I want tool visibility restricted by user role so that users only see and invoke tools appropriate to their access level.

#### Acceptance Criteria

1. WHEN the Agent_Orchestrator prepares a tool list for the LLM_Client, THE Role_Filter SHALL retrieve the Allowed_Tools for the current user's role from the role_tool_map table.
2. THE Role_Filter SHALL remove any tools not in the user's Allowed_Tools list before presenting the tool definitions to the LLM_Client.
3. WHEN a user's role has no entries in the role_tool_map table, THE Role_Filter SHALL present an empty tool list to the LLM_Client.
4. IF a tool call references a tool not in the user's Allowed_Tools, THEN THE Guardrail_Engine SHALL block the tool call and return an error indicating insufficient permissions.

### Requirement 12: User Identity Resolution

**User Story:** As a developer, I want user identity resolved via a swappable dependency so that the system works with a hardcoded test user now and can integrate real authentication later.

#### Acceptance Criteria

1. THE User_Provider SHALL resolve the current user identity for every incoming API request.
2. THE User_Provider SHALL return the user's identifier, email, name, and role from the users table in the Conversation_Store.
3. THE User_Provider SHALL be implemented as a FastAPI dependency that can be replaced with an authentication-based implementation without modifying endpoint code.
4. WHILE in development mode, THE User_Provider SHALL return a hardcoded test user record for all requests.

### Requirement 13: Database Schema and Migrations

**User Story:** As a developer, I want the database schema managed through migrations so that schema changes are versioned and reproducible.

#### Acceptance Criteria

1. THE Conversation_Store SHALL define tables for users, conversations, messages, and role_tool_map using SQLAlchemy async models.
2. THE Conversation_Store SHALL enforce a foreign key relationship from conversations.user_id to users.id.
3. THE Conversation_Store SHALL enforce a foreign key relationship from messages.conversation_id to conversations.id.
4. THE Conversation_Store SHALL store tool_calls in the messages table as a JSON column.
5. WHEN a schema change is introduced, THE Conversation_Store SHALL provide an Alembic migration script that applies the change.
6. THE Conversation_Store SHALL use asyncpg as the async PostgreSQL driver.

### Requirement 14: Local Development Environment

**User Story:** As a developer, I want flexible local development options so that I can run the full stack with one command or run components individually.

#### Acceptance Criteria

1. THE Chat_API SHALL provide a Docker Compose configuration that starts PostgreSQL and the application together with a single command.
2. THE Chat_API SHALL support running with a local PostgreSQL instance and uvicorn as an alternative to Docker Compose.
3. THE Chat_API SHALL load configuration from environment variables, supporting a .env file for local development.
4. WHEN the application starts, THE Chat_API SHALL run pending Alembic migrations automatically or provide a documented command to apply them.

### Requirement 15: Async Request Handling

**User Story:** As a developer, I want the entire request pipeline to be async so that the server handles concurrent users efficiently without blocking.

#### Acceptance Criteria

1. THE Chat_API SHALL handle all HTTP requests using async FastAPI route handlers.
2. THE Conversation_Store SHALL execute all database operations using async SQLAlchemy sessions with the asyncpg driver.
3. THE LLM_Client SHALL invoke AWS Bedrock APIs using async HTTP calls.
4. THE MCP_Client SHALL communicate with the NetSuite MCP Server using async operations.
