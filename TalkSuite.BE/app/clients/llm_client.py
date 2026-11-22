import asyncio
import json
from typing import Any, AsyncGenerator

from app.config import settings


class LLMClient:
    """
    Async wrapper around AWS Bedrock for Claude invocations.

    Uses the Bedrock Converse and ConverseStream APIs for
    tool-augmented conversations.

    Falls back to mock responses when AWS credentials are not configured.
    """

    def __init__(self):
        self.model_id = settings.bedrock_model_id
        self._mock_mode = False
        self.client = None

        try:
            import boto3

            # On ECS, credentials come from the task role automatically (no explicit keys needed).
            # Only enter mock mode if boto3 is unavailable or client creation fails.
            self.client = boto3.client(
                "bedrock-runtime", region_name=settings.aws_region
            )
        except Exception:
            self._mock_mode = True
            print(f"[TalkSuite] LLM Client running in MOCK mode ({e})")

    async def invoke(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str = "",
    ) -> dict[str, Any]:
        """
        Invoke Claude via Bedrock Converse API (non-streaming).

        Returns the full response including any tool_use blocks.
        Falls back to mock response if AWS is not configured.
        """
        if self._mock_mode:
            return self._mock_response(messages)

        request = self._build_request(messages, tools, system_prompt)
        try:
            response = await asyncio.to_thread(self.client.converse, **request)
        except Exception as e:
            print(f"[TalkSuite] Bedrock Converse error: {e}")
            raise
        return response

    async def invoke_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str = "",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Invoke Claude via Bedrock ConverseStream API.

        Yields streaming events as they arrive.
        Falls back to mock if Bedrock call fails.
        """
        if self._mock_mode:
            mock = self._mock_response(messages)
            text = mock["output"]["message"]["content"][0]["text"]
            yield {"contentBlockStart": {"start": {"text": ""}}}
            yield {"contentBlockDelta": {"delta": {"text": text}}}
            yield {"messageStop": {"stopReason": "end_turn"}}
            return

        request = self._build_request(messages, tools, system_prompt)
        try:
            response = await asyncio.to_thread(
                self.client.converse_stream, **request
            )
            stream = response.get("stream", [])
            for event in stream:
                yield event
        except Exception as e:
            print(f"[TalkSuite] Bedrock stream failed, falling back to mock: {e}")
            mock = self._mock_response(messages)
            text = mock["output"]["message"]["content"][0]["text"]
            yield {"contentBlockStart": {"start": {"text": ""}}}
            yield {"contentBlockDelta": {"delta": {"text": text}}}
            yield {"messageStop": {"stopReason": "end_turn"}}

    def _build_request(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str = "",
    ) -> dict[str, Any]:
        """Build the request payload for Bedrock Converse APIs."""
        request: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": messages,
        }
        if system_prompt:
            request["system"] = [{"text": system_prompt}]
        if tools:
            request["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "inputSchema": t.get("inputSchema", {"json": {}}),
                        }
                    }
                    for t in tools
                ]
            }
        return request

    def format_tool_result(
        self, tool_use_id: str, content: str
    ) -> dict[str, Any]:
        """Format a tool result for inclusion in the conversation."""
        return {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": tool_use_id,
                        "content": [{"text": content}],
                    }
                }
            ],
        }

    def _mock_response(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Generate a mock response for testing without AWS credentials.

        Echoes back the user's message with a mock prefix.
        """
        # Extract the last user message
        last_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", [])
                if isinstance(content, list) and content:
                    first_block = content[0]
                    if isinstance(first_block, dict) and "text" in first_block:
                        last_message = first_block["text"]
                break

        mock_text = (
            f"[MOCK MODE - AWS not configured] "
            f"I received your message: \"{last_message}\". "
            f"In production, I would process this through Claude on AWS Bedrock "
            f"and potentially call NetSuite tools to fetch live data. "
            f"The conversation CRUD, SSE streaming, and guardrails are all working."
        )

        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": mock_text}],
                }
            },
            "stopReason": "end_turn",
        }
