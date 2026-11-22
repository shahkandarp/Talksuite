import asyncio
import json
from typing import Any, AsyncGenerator


class SSEStream:
    """
    Accumulates and yields SSE events during agent processing.

    Events are emitted by the agent nodes and consumed by the
    streaming response generator.
    """

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._closed = False

    def emit_thinking(self):
        """Emit a thinking/reasoning event."""
        self._put_event("thinking", {"status": "reasoning"})

    def emit_tool_call(self, tool_name: str, input_params: dict[str, Any]):
        """Emit a tool call initiation event."""
        self._put_event("tool_call", {"tool_name": tool_name, "input": input_params})

    def emit_tool_result(self, tool_name: str, result_summary: str):
        """Emit a tool result event."""
        self._put_event(
            "tool_result",
            {"tool_name": tool_name, "result_summary": result_summary},
        )

    def emit_text_chunk(self, text: str):
        """Emit a partial text response chunk."""
        self._put_event("text_chunk", {"text": text})

    def emit_data_block(self, chart_data: dict[str, Any]):
        """
        Emit a structured data block for chart rendering.

        The chart_data should follow Chart.js format:
        {
            "chart_type": "bar|pie|line|doughnut|polarArea",
            "title": "Chart Title",
            "data": {
                "labels": [...],
                "datasets": [{"label": "...", "data": [...], "backgroundColor": [...]}]
            },
            "options": {"x_axis_label": "...", "y_axis_label": "...", "currency": "..."}
        }
        """
        self._put_event("data_block", chart_data)

    def emit_done(self, message_id: str):
        """Emit the done event signaling completion."""
        self._put_event("done", {"message_id": message_id})
        self._closed = True

    def emit_follow_ups(self, questions: list[str]):
        """Emit suggested follow-up questions for the frontend to render as clickable chips."""
        self._put_event("follow_ups", {"questions": questions})

    def emit_title_generated(self, title: str):
        """Emit a generated conversation title for the frontend to update the chat name."""
        self._put_event("title_generated", {"title": title})

    def emit_error(self, error: str):
        """Emit an error event."""
        self._put_event("error", {"message": error})

    def close(self):
        """Close the stream (signals the generator to stop)."""
        self._closed = True
        # Put a sentinel to unblock the queue
        self._queue.put_nowait(None)

    async def generate(self) -> AsyncGenerator[str, None]:
        """
        Async generator that yields SSE-formatted strings.

        Blocks waiting for events from the queue until the stream is closed.
        """
        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=30.0)
                if item is None:
                    # Sentinel value — stream is done
                    break
                yield item
            except asyncio.TimeoutError:
                # Send a keep-alive comment to prevent connection timeout
                yield ": keep-alive\n\n"

    def _put_event(self, event_type: str, data: dict[str, Any]):
        """Format and enqueue an SSE event."""
        formatted = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        self._queue.put_nowait(formatted)
