import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_current_account
from app.models.database import get_db_session
from app.models.user import User
from app.models.netsuite_account import NetSuiteAccount
from app.schemas.message import MessageCreate
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.agent.orchestrator import AgentOrchestrator
from app.agent.role_filter import RoleFilter
from app.agent.stream import SSEStream
from app.agent.input_guard import validate_input

router = APIRouter(
    prefix="/conversations/{conversation_id}/messages", tags=["messages"]
)


@router.post("")
async def send_message(
    conversation_id: UUID,
    body: MessageCreate,
    request: Request,
    user: User = Depends(get_current_user),
    account: NetSuiteAccount = Depends(get_current_account),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Send a message in a conversation and stream the agent's response via SSE.

    The response is streamed as Server-Sent Events with event types:
    - thinking: agent is reasoning
    - tool_call: a tool invocation started
    - tool_result: a tool invocation completed
    - text_chunk: partial text response
    - done: processing complete
    - error: an error occurred (e.g., tool blocked)
    """
    # Verify conversation ownership
    conv_service = ConversationService(db)
    conversation = await conv_service.get_with_messages(conversation_id, user)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Input sanitization — prevent prompt injection
    validation = validate_input(body.content)
    if not validation.is_safe:
        # Return an SSE stream with just an error event (don't persist or process)
        sse_stream = SSEStream()

        async def blocked_stream():
            sse_stream.emit_error(validation.reason or "Message blocked by safety filter.")
            sse_stream.emit_done("")
            sse_stream.close()
            async for event in sse_stream.generate():
                yield event

        return StreamingResponse(
            blocked_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Persist user message (using sanitized text)
    msg_service = MessageService(db)
    await msg_service.create_user_message(conversation_id, validation.sanitized_text)

    # Get allowed tools for the user's role
    role_filter = RoleFilter(db)
    allowed_tools = await role_filter.get_allowed_tools(user.role)

    # Build message history for the agent (Bedrock Converse format)
    messages = _build_message_history(conversation, validation.sanitized_text)

    # Create SSE stream
    sse_stream = SSEStream()

    async def process_and_stream():
        """Background task: run agent and emit events to the stream."""
        try:
            # Resolve the per-account MCP client and shared clients
            from app.main import mcp_manager, llm_client, kb_client

            mcp_client = await mcp_manager.get_client(account)

            orchestrator = AgentOrchestrator(llm_client, mcp_client, kb_client)

            final_response = await orchestrator.run(
                conversation_id=conversation_id,
                messages=messages,
                allowed_tools=allowed_tools,
                user_role=user.role,
                stream=sse_stream,
            )

            # Persist assistant response
            assistant_msg = await msg_service.create_assistant_message(
                conversation_id, final_response
            )

            # Generate title if this is the first message in the conversation
            is_first_message = len(conversation.messages) == 0
            if is_first_message:
                title = await _generate_title(llm_client, body.content, final_response)
                await conv_service.update_title(conversation_id, title)
                sse_stream.emit_title_generated(title)

            # Emit done event
            sse_stream.emit_done(str(assistant_msg.id))

        except asyncio.CancelledError:
            sse_stream.emit_error("Request was cancelled")
        except Exception as e:
            sse_stream.emit_error(f"Internal error: {str(e)}")
        finally:
            sse_stream.close()

    async def event_generator():
        """Yield SSE events, checking for client disconnect."""
        # Start the processing task
        task = asyncio.create_task(process_and_stream())

        try:
            async for event in sse_stream.generate():
                # Check if client disconnected
                if await request.is_disconnected():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=5.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
                    break
                yield event
        except asyncio.CancelledError:
            task.cancel()
            raise

        # Ensure the task is completed
        if not task.done():
            await task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _build_message_history(conversation, new_content: str) -> list[dict]:
    """
    Convert stored messages to Bedrock Converse API format.
    Uses a sliding window of the last MAX_HISTORY_MESSAGES to prevent
    hitting token limits on long conversations.

    Format: [{"role": "user"|"assistant", "content": [{"text": "..."}]}]
    """
    MAX_HISTORY_MESSAGES = 20  # Last 20 messages (10 user + 10 assistant turns)

    messages = []

    # Take only the most recent messages within the window
    recent_messages = conversation.messages[-MAX_HISTORY_MESSAGES:]

    for msg in recent_messages:
        messages.append(
            {"role": msg.role, "content": [{"text": msg.content}]}
        )

    # Add the new user message
    messages.append({"role": "user", "content": [{"text": new_content}]})

    return messages


async def _generate_title(llm_client, user_message: str, assistant_response: str) -> str:
    """
    Generate a short conversation title based on the first message exchange.
    Uses the LLM to create a concise 3-6 word title.
    Falls back to truncating the user message if LLM is unavailable.
    """
    try:
        response = await llm_client.invoke(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                f"Generate a very short title (3-6 words, no quotes) for a conversation "
                                f"that starts with this question: \"{user_message}\"\n\n"
                                f"The assistant replied about: \"{assistant_response[:100]}\"\n\n"
                                f"Reply with ONLY the title, nothing else."
                            )
                        }
                    ],
                }
            ],
            system_prompt="You generate short conversation titles. Reply with only the title, 3-6 words, no quotes, no punctuation at the end.",
        )

        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])

        for block in content_blocks:
            if "text" in block:
                title = block["text"].strip().strip('"').strip("'")
                # Ensure reasonable length
                if 2 < len(title) < 60:
                    return title

    except Exception:
        pass

    # Fallback: use first few words of the user message
    words = user_message.split()
    return " ".join(words[:6]) + ("..." if len(words) > 6 else "")
