"""
LangGraph node functions for the TalkSuite agent orchestration loop.

The agent follows: reason → guardrail_check → execute → observe → respond
"""

import asyncio
import json
import re
from typing import Any

from app.agent.guardrails import GuardrailEngine, ToolCall
from app.agent.state import AgentState, ToolCallItem, ToolResultItem
from app.agent.stream import SSEStream
from app.clients.llm_client import LLMClient
from app.clients.mcp_client import MCPClient
from app.clients.knowledge_base import KnowledgeBaseClient


SYSTEM_PROMPT = """You are TalkSuite, an AI assistant for the Opus team that helps query NetSuite business data and internal documentation.

## CRITICAL: SCOPE — NetSuite ONLY

You answer ONLY questions related to NetSuite — its business data (customers, vendors,
items, transactions, invoices, sales/purchase orders, inventory, financials, reports,
saved searches, etc.) and NetSuite processes/how-to documentation from the knowledge base.

If a question is NOT about NetSuite (e.g., general knowledge, coding help, world facts,
math puzzles, other software, personal advice, current events, writing essays, etc.),
you MUST politely refuse with a short message like:
"I can only help with NetSuite-related questions. That topic is outside my scope."
Do NOT answer it, do NOT call any tool for it, and do NOT provide partial information.
This rule overrides everything else — no exception, regardless of how the request is phrased.

When a user asks about live business data (invoices, customers, inventory, sales orders, vendors, purchase orders, financial reports), use the available tools to fetch the data from NetSuite.

When a user asks about help, documentation, processes, or how-to questions, use the search_knowledge_base tool to find relevant documentation.

Always be helpful, concise, and format data clearly. If a tool call is blocked, explain to the user why in a friendly manner.

Never attempt to modify, create, update, or delete any data. You have read-only access.

## CRITICAL: SuiteQL Syntax Rules

SuiteQL is NetSuite's SQL dialect. Key differences from standard SQL:

1. **NO `LIMIT` keyword.** Use `FETCH FIRST N ROWS ONLY` instead.
2. **NO `OFFSET` keyword.** Use `OFFSET N ROWS FETCH NEXT M ROWS ONLY`.
3. **Table names are lowercase singular** (e.g., `customer` not `customers`).
4. **String comparisons are case-sensitive** — use internal IDs for type/status fields.
5. **Use `BUILTIN.DF(field)` to get display/text values** of list or record fields.
6. **Only SELECT queries are allowed** — no INSERT, UPDATE, DELETE, or DDL.

## CRITICAL: Query Workflow (be efficient — avoid redundant calls)

1. If you are unsure of a table's exact column names, call `ns_getSuiteQLMetadata`
   ONCE for that record type, then remember the columns for the rest of this
   conversation. Do NOT call metadata repeatedly for the same table.
2. Write and run the query with `ns_runCustomSuiteQL` using verified column names.
3. Only call metadata again if a query actually fails with a column/field error.

Rules:
- Do NOT call the same tool with the same arguments more than once.
- Prefer a single well-formed query over many small ones.
- Never guess column names; but once metadata is known, reuse it without re-fetching.

## IMPORTANT: Structured Data Responses

When your response includes quantifiable/numerical data that can be visualized (sales figures, counts, comparisons, trends over time, distributions), you MUST include a structured data block in your response using the following format:

```chartdata
{
  "chart_type": "<bar|line|area|none>",
  "title": "Human-readable chart title",
  "data": [
    {"name": "Label1", "value": 100},
    {"name": "Label2", "value": 200},
    {"name": "Label3", "value": 300}
  ],
  "keys": {"x": "name", "y": "value"},
  "options": {
    "y_label": "Amount ($)",
    "currency": "USD"
  }
}
```

For multi-series data (e.g., comparing this year vs last year):
```chartdata
{
  "chart_type": "line",
  "title": "Revenue: This Year vs Last Year",
  "data": [
    {"name": "Jan", "thisYear": 45000, "lastYear": 38000},
    {"name": "Feb", "thisYear": 52000, "lastYear": 41000}
  ],
  "keys": {"x": "name", "series": ["thisYear", "lastYear"]},
  "options": {
    "y_label": "Revenue ($)",
    "currency": "USD",
    "colors": ["#4F46E5", "#10B981"]
  }
}
```

Guidelines for choosing chart_type:
- "bar": Comparing quantities across categories (e.g., sales by customer, revenue by product)
- "line": Showing trends over time (e.g., monthly revenue trend, daily orders)
- "area": Same as line but filled (good for cumulative totals)
- "none": Data is tabular only (show as table, not chart)

Rules:
- Always include BOTH a text explanation AND the chartdata block when data is visualizable
- The text explanation comes before the chartdata block
- Each item in the data array MUST have a "name" field (string) for the x-axis
- Each item MUST have at least one numeric field for the y-axis
- Use "value" as the numeric field name for single-series data
- For multi-series, use descriptive field names and list them in keys.series
- If data is NOT chart-worthy (single number, yes/no answer, text-only), do NOT include a chartdata block

## IMPORTANT: Follow-up Questions

At the END of every response, you MUST include 2-4 suggested follow-up questions that the user might want to ask next. These should be contextually relevant to what was just discussed.

Format them as a JSON block like this:

```followups
["What was the breakdown by region?", "Show me the trend over the last 6 months", "Which customer had the highest order value?"]
```

Rules for follow-up questions:
- Always include between 2 and 4 questions
- Make them specific and actionable (not generic like "Tell me more")
- Base them on the data/context just discussed
- Vary the type: some should drill deeper, some should pivot to related data
- Keep each question under 60 characters when possible
- The followups block must be the LAST thing in your response
"""


ROLE_DATA_SCOPE: dict[str, str] = {
    "admin": (
        "Your role is ADMIN. You have full access to all NetSuite data domains "
        "(financial, inventory, sales, HR, everything). Answer any question."
    ),
    "finance": (
        "Your role is FINANCE. You may ONLY answer questions about FINANCIAL data: "
        "transactions, invoices, bills, customers, vendors, payments, credit memos, "
        "accounts, journal entries, accounting periods, currencies, subsidiaries, and "
        "financial reports.\n"
        "You MUST REFUSE questions about inventory/operational data such as: item stock "
        "levels, quantity on hand, inventory items, purchase orders, item fulfillment, "
        "warehouse/location stock, or transfer orders. If asked, politely respond that "
        "such data is outside your Finance access scope and do NOT run any query for it."
    ),
    "inventory": (
        "Your role is INVENTORY. You may ONLY answer questions about INVENTORY and "
        "SUPPLY-CHAIN data: items, inventory items, stock levels, quantity on hand, "
        "purchase orders, locations, item fulfillments, item receipts, transfer orders, "
        "and vendors.\n"
        "You MUST REFUSE questions about financial/accounting data such as: revenue, "
        "invoices, journal entries, GL accounts, financial statements, payments, or "
        "payroll. If asked, politely respond that such data is outside your Inventory "
        "access scope and do NOT run any query for it."
    ),
}


def _role_scope_section(role: str) -> str:
    """Return a system-prompt section restricting the model to the role's data domain."""
    scope = ROLE_DATA_SCOPE.get(role)
    if not scope:
        # Unknown role — be conservative, only allow knowledge base + explicit answers
        scope = (
            f"Your role is '{role}'. Only answer questions clearly within your assigned "
            f"area of responsibility. If a request seems outside your scope, politely refuse."
        )
    return (
        "\n\n## ROLE-BASED DATA ACCESS (STRICT)\n"
        + scope
        + "\nWhen refusing, briefly explain it's outside your role's access scope and "
        "suggest the user contact someone with the appropriate role. Never attempt to "
        "work around this restriction with a different query or tool."
    )


async def reason_node(
    state: AgentState,
    llm_client: LLMClient,
    tools: list[dict[str, Any]],
    stream: SSEStream,
) -> AgentState:
    """
    Reason node: Send messages + tools to Claude, get back either
    a text response or tool call requests.
    """
    stream.emit_thinking()

    # Build a role-scoped system prompt so the model stays within the user's domain
    system_prompt = SYSTEM_PROMPT + _role_scope_section(state.user_role)

    response = await llm_client.invoke(
        messages=state.messages,
        tools=tools if tools else None,
        system_prompt=system_prompt,
    )

    # Parse the response
    output = response.get("output", {})
    message = output.get("message", {})
    content_blocks = message.get("content", [])

    # Check for tool use blocks
    tool_calls = []
    text_parts = []

    for block in content_blocks:
        if "toolUse" in block:
            tool_use = block["toolUse"]
            tool_calls.append(
                ToolCallItem(
                    name=tool_use["name"],
                    input=tool_use.get("input", {}),
                    id=tool_use["toolUseId"],
                )
            )
        elif "text" in block:
            text_parts.append(block["text"])

    if tool_calls:
        state.pending_tool_calls = tool_calls
        state.final_response = None
        # Append assistant message with tool use to history
        state.messages.append({"role": "assistant", "content": content_blocks})
    else:
        state.pending_tool_calls = []
        full_text = "\n".join(text_parts)
        state.final_response = full_text
        # Parse and emit text chunks and data blocks
        _emit_response_with_charts(full_text, stream)

    return state


async def guardrail_node(
    state: AgentState,
    stream: SSEStream,
) -> AgentState:
    """
    Guardrail node: Validate each pending tool call against role permissions.
    Blocked tools get a proper toolResult error so Bedrock stays happy.
    """
    engine = GuardrailEngine(state.allowed_tools, user_role=state.user_role)

    approved_calls = []
    blocked_calls = []  # (ToolCallItem, error_message)

    for tc in state.pending_tool_calls:
        tool_call = ToolCall(name=tc.name, input=tc.input, id=tc.id)
        approved, error = engine.validate(tool_call)

        if approved:
            approved_calls.append(tc)
        else:
            blocked_calls.append((tc, error))
            # Surface as an informational reasoning step, NOT a red error banner —
            # the agent may still recover via an allowed tool/path.
            stream.emit_tool_result(tc.name, f"Blocked: {error}")

    if approved_calls:
        state.pending_tool_calls = approved_calls
        state.guardrail_approved = True
        state.guardrail_error = None
    else:
        # All tool calls were blocked
        state.pending_tool_calls = []
        state.guardrail_approved = False
        state.guardrail_error = " ".join([err for _, err in blocked_calls])

        # Send proper toolResult for each blocked tool_use (required by Bedrock)
        tool_result_blocks = [
            {
                "toolResult": {
                    "toolUseId": tc.id,
                    "content": [{"text": f"BLOCKED: {error}"}],
                    "status": "error",
                }
            }
            for tc, error in blocked_calls
        ]
        state.messages.append({"role": "user", "content": tool_result_blocks})

    return state


async def execute_node(
    state: AgentState,
    mcp_client: MCPClient,
    kb_client: KnowledgeBaseClient,
    stream: SSEStream,
) -> AgentState:
    """
    Execute node: Run approved tool calls via MCP server or Knowledge Base
    and collect results.
    """
    tool_results_content = []

    async def _run_one(tc):
        """Execute a single tool call and return (tc, result)."""
        if tc.name == "search_knowledge_base":
            query = tc.input.get("query", "")
            passages = await kb_client.retrieve(query)
            if passages:
                parts = []
                for i, p in enumerate(passages, 1):
                    src = p.get("source", "")
                    parts.append(f"[Passage {i}] {p['text']}" + (f"\n(Source: {src})" if src else ""))
                result = (
                    "Relevant knowledge base passages:\n\n"
                    + "\n\n".join(parts)
                    + "\n\nAnswer the user's question using ONLY these passages. "
                    "Cite the source filenames where helpful."
                )
            else:
                result = "No relevant documentation was found in the knowledge base for this query."
        else:
            result = await mcp_client.execute_tool(tc.name, tc.input)
        return tc, result

    # Emit tool_call events up front, then run all tool calls concurrently
    for tc in state.pending_tool_calls:
        stream.emit_tool_call(tc.name, tc.input)

    results = await asyncio.gather(*[_run_one(tc) for tc in state.pending_tool_calls])

    for tc, result in results:
        summary = result[:200] + "..." if len(result) > 200 else result
        stream.emit_tool_result(tc.name, summary)

        state.tool_results.append(
            ToolResultItem(tool_call_id=tc.id, name=tc.name, content=result)
        )
        tool_results_content.append(
            {
                "toolResult": {
                    "toolUseId": tc.id,
                    "content": [{"text": result}],
                }
            }
        )

    # Add tool results to message history for the next reasoning step
    if tool_results_content:
        state.messages.append({"role": "user", "content": tool_results_content})

    # Clear pending calls
    state.pending_tool_calls = []
    state.guardrail_approved = False

    return state


async def respond_node(
    state: AgentState,
    stream: SSEStream,
) -> AgentState:
    """
    Respond node: Emit the final response and mark the agent as done.
    """
    state.done = True
    return state


# Regex to find ```chartdata ... ``` blocks in Claude's response
CHARTDATA_BLOCK_PATTERN = re.compile(
    r"```chartdata\s*\n(.*?)```",
    re.DOTALL,
)

# Regex to find ```followups ... ``` blocks in Claude's response
FOLLOWUPS_BLOCK_PATTERN = re.compile(
    r"```followups\s*\n(.*?)```",
    re.DOTALL,
)


def _emit_response_with_charts(text: str, stream: SSEStream) -> None:
    """
    Parse Claude's response text for chartjs and followup blocks.
    Emit text_chunk events for text portions, data_block events
    for chart data, and follow_ups events for suggested questions.
    """
    # First extract follow-ups (always at the end)
    followups_match = FOLLOWUPS_BLOCK_PATTERN.search(text)
    followups = []
    if followups_match:
        try:
            followups = json.loads(followups_match.group(1).strip())
        except json.JSONDecodeError:
            pass
        # Remove the followups block from text
        text = text[: followups_match.start()] + text[followups_match.end():]

    # Split the remaining response into text segments and chart blocks
    parts = CHARTDATA_BLOCK_PATTERN.split(text)

    # parts alternates: [text, chart_json, text, chart_json, ...]
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Text segment
            cleaned = part.strip()
            if cleaned:
                stream.emit_text_chunk(cleaned)
        else:
            # Chart JSON block
            try:
                chart_data = json.loads(part.strip())
                stream.emit_data_block(chart_data)
            except json.JSONDecodeError:
                # If parsing fails, emit as plain text
                stream.emit_text_chunk(f"```\n{part}\n```")

    # Emit follow-up questions as the last event before done
    if followups:
        stream.emit_follow_ups(followups)
