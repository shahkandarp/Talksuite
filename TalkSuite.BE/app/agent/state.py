from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class ToolCallItem:
    """Represents a single tool call proposed by the LLM."""

    name: str
    input: dict[str, Any]
    id: str


@dataclass
class ToolResultItem:
    """Represents the result of an executed tool call."""

    tool_call_id: str
    name: str
    content: str


@dataclass
class AgentState:
    """
    State managed by the LangGraph agent across the orchestration loop.

    Tracks conversation context, pending tool calls, results,
    and the final response.
    """

    conversation_id: UUID
    messages: list[dict[str, Any]] = field(default_factory=list)
    pending_tool_calls: list[ToolCallItem] = field(default_factory=list)
    tool_results: list[ToolResultItem] = field(default_factory=list)
    guardrail_approved: bool = False
    guardrail_error: str | None = None
    final_response: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    user_role: str = ""
    done: bool = False
