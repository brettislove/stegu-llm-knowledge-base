"""
Shared agentic tool-use loop.

This is the piece Claude Code gives you for free and which we have to build
ourselves when driving the raw Anthropic API. Each agent supplies a system
prompt, a tool schema list, and a dispatch function; this loop handles the
send -> tool_use -> execute -> tool_result -> repeat cycle until Claude
returns a final text answer.
"""
import json
from typing import Callable, List, Optional, Union

import anthropic

from backend.config import ANTHROPIC_API_KEY, MODEL

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Safety cap so a confused/looping agent can't run indefinitely (and rack up
# API cost). 12 turns is generous for a <200-document wiki; raise if agents
# are legitimately hitting the ceiling on complex ingests.
MAX_TURNS = 12


def run_agent_loop(
    system_prompt: str,
    user_message: Union[str, list],
    tools: List[dict],
    dispatch: Callable[[str, dict], str],
    max_turns: int = MAX_TURNS,
    history: Optional[List[dict]] = None,
) -> dict:
    """
    Returns {"final_text": str, "transcript": list, "turns": int,
    "usage": {"input_tokens", "output_tokens", "cache_creation_tokens",
    "cache_read_tokens"}} — the usage totals feed the Náklady dashboard's
    cost estimate (see tools/pricing.py).

    `dispatch(tool_name, tool_input)` executes one tool call and returns a
    string result. Exceptions are caught and surfaced back to Claude as a
    tool error (is_error=True) so it can recover or explain, rather than
    crashing the whole request.

    `history`, when given, is a list of prior `{"role": "user"|"assistant",
    "content": ...}` turns prepended before `user_message` — this is how a
    caller (currently only query_agent, for in-session chat follow-ups)
    seeds multi-turn context. Every other caller leaves it at the default,
    which reproduces the exact single-turn behavior this loop always had.

    Both the system prompt (which embeds the full SCHEMA.md, ~9KB) and the
    tool definitions are marked cacheable. They're identical across every
    turn of a single ingest/query run, AND across separate runs until
    SCHEMA.md changes — so this turns "resend ~9KB every turn" into
    "pay for it once, then reuse."
    """
    messages = list(history) if history else []
    messages.append({"role": "user", "content": user_message})
    transcript = []

    # Cache breakpoint: everything up to and including this block is cached.
    cached_system = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
    # Cache breakpoint on the last tool: caches the whole tool list, since
    # it never changes within an agent.
    cached_tools = [dict(t) for t in tools]
    if cached_tools:
        cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}

    total_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
    }

    for turn in range(max_turns):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=cached_system,
            tools=cached_tools,
            messages=messages,
        )

        total_usage["input_tokens"] += getattr(response.usage, "input_tokens", 0) or 0
        total_usage["output_tokens"] += getattr(response.usage, "output_tokens", 0) or 0
        total_usage["cache_creation_tokens"] += (
            getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        )
        total_usage["cache_read_tokens"] += (
            getattr(response.usage, "cache_read_input_tokens", 0) or 0
        )

        assistant_content = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": assistant_content})
        transcript.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            return {
                "final_text": final_text,
                "transcript": transcript,
                "turns": turn + 1,
                "usage": total_usage,
            }

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = dispatch(block.name, block.input)
                content = result if isinstance(result, str) else json.dumps(result)
                is_error = False
            except Exception as e:
                content = f"Error: {e}"
                is_error = True
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content,
                "is_error": is_error,
            })

        messages.append({"role": "user", "content": tool_results})
        transcript.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"Agent exceeded max_turns ({max_turns}) without producing a final answer.")
