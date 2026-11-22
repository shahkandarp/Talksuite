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
