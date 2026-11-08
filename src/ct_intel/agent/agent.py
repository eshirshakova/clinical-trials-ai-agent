"""LangChain Gemini agent with one read-only DuckDB tool."""

from __future__ import annotations

import json
from typing import Any

from ct_intel.agent.sql_tool import GOLD_SCHEMA, execute_readonly
from ct_intel.config import Settings

SYSTEM_PROMPT = f"""You answer questions about clinical trials stored in a local DuckDB warehouse.
Use the query_gold tool to run SQL. Base counts, lists, and dates only on tool results.
When the user asks about eligibility, select eligibility_criteria and summarize that text.
Do not invent study counts or NCT IDs.

{GOLD_SCHEMA}
"""


def _call_parts(call: Any) -> tuple[str, dict[str, Any], str]:
    if isinstance(call, dict):
        name = str(call.get("name", ""))
        args = call.get("args") or {}
        call_id = str(call.get("id", ""))
    else:
        name = str(getattr(call, "name", ""))
        args = getattr(call, "args", {}) or {}
        call_id = str(getattr(call, "id", ""))
    if isinstance(args, str):
        args = json.loads(args)
    return name, args, call_id


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return str(content)


def ask(settings: Settings, question: str, *, max_turns: int = 5) -> dict[str, Any]:
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set. Add it to .env before using ask.")

    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
    from langchain_core.tools import tool
    from langchain_google_genai import ChatGoogleGenerativeAI

    @tool
    def query_gold(sql: str) -> str:
        """Run one read-only SELECT or WITH query against the Gold clinical-trial views."""
        return execute_readonly(sql, settings.warehouse_path)

    model = ChatGoogleGenerativeAI(
        model=settings.google_model,
        google_api_key=settings.google_api_key,
    )
    bound = model.bind_tools([query_gold])
    messages: list[Any] = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=question)]
    sql_ran: list[str] = []

    for _ in range(max_turns):
        ai_message = bound.invoke(messages)
        messages.append(ai_message)
        tool_calls = getattr(ai_message, "tool_calls", None) or []
        if not tool_calls:
            return {"answer": _message_text(ai_message.content).strip(), "sql": sql_ran}
        for call in tool_calls:
            name, args, call_id = _call_parts(call)
            statement = str(args.get("sql", ""))
            if statement:
                sql_ran.append(statement)
            if name != "query_gold":
                result = f"Unknown tool: {name}"
            else:
                try:
                    result = query_gold.invoke({"sql": statement})
                except Exception as exc:
                    result = f"Error: {exc}"
            messages.append(ToolMessage(content=str(result), tool_call_id=call_id))

    return {
        "answer": "Stopped after too many SQL attempts. Narrow the question and try again.",
        "sql": sql_ran,
    }
