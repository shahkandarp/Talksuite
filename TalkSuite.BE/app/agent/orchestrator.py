"""
LangGraph-based agent orchestrator for TalkSuite.

Defines the StateGraph with the execution loop:
  reason → guardrail_check → execute → reason (loop)
  reason → respond (when no tool calls needed)
"""

import asyncio
from typing import Any
from uuid import UUID

from app.agent.nodes import reason_node, guardrail_node, execute_node, respond_node
from app.agent.state import AgentState
from app.agent.stream import SSEStream
from app.clients.llm_client import LLMClient
from app.clients.mcp_client import MCPClient
from app.clients.knowledge_base import KnowledgeBaseClient
from app.config import settings


MAX_ITERATIONS = settings.agent_max_iterations  # configurable via AGENT_MAX_ITERATIONS


class AgentOrchestrator:
    """
    Orchestrates the agent loop using a simple state machine pattern.

    While LangGraph provides the conceptual framework, this implementation
    uses a straightforward async loop for clarity and control over streaming.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        mcp_client: MCPClient,
        kb_client: KnowledgeBaseClient,
    ):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.kb_client = kb_client

    async def run(
        self,
        conversation_id: UUID,
        messages: list[dict[str, Any]],
        allowed_tools: list[str],
        user_role: str,
        stream: SSEStream,
    ) -> str:
        """
        Run the agent loop and return the final response text.

        The loop follows: reason → (guardrail_check → execute → reason)* → respond
        """
        # Get available tool definitions from NetSuite MCP
        all_tools = await self.mcp_client.get_tools()

        # Add the Knowledge Base tool (always available)
        kb_tool = {
            "name": "search_knowledge_base",
            "description": (
                "Search the company knowledge base for help documentation, "
                "process guides, how-to articles, and internal policies. "
                "Use this when the user asks about processes, documentation, "
                "how to do something, or needs help understanding a concept."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to find relevant documentation",
                        }
                    },
                    "required": ["query"],
                }
            },
        }

        # Filter tools by role — only show tools the user is allowed to call
        filtered_tools = [t for t in all_tools if t.get("name") in allowed_tools]
        # KB is always available
        if "search_knowledge_base" in allowed_tools:
            filtered_tools.append(kb_tool)

        # allowed_tools from DB contains tool names permitted for this role
        state = AgentState(
            conversation_id=conversation_id,
            messages=messages,
            allowed_tools=allowed_tools,
            user_role=user_role,
        )

        iterations = 0

        while not state.done and iterations < MAX_ITERATIONS:
            iterations += 1

            # Step 1: Reason — ask Claude what to do
            state = await reason_node(state, self.llm_client, filtered_tools, stream)

            # If Claude responded with text (no tool calls), we're done
            if state.final_response and not state.pending_tool_calls:
                state = await respond_node(state, stream)
                break

            # Step 2: Guardrail check on pending tool calls
            if state.pending_tool_calls:
                state = await guardrail_node(state, stream)

                # If all tool calls were blocked, loop back to reason
                if not state.guardrail_approved:
                    continue

                # Step 3: Execute approved tool calls
                state = await execute_node(
                    state, self.mcp_client, self.kb_client, stream
                )

                # Loop back to reason with tool results

        # If we hit max iterations without a final response
        if not state.final_response:
            state.final_response = (
                "I apologize, but I was unable to complete your request "
                "within the allowed number of steps. Please try rephrasing "
                "your question."
            )
            stream.emit_text_chunk(state.final_response)

        return state.final_response
