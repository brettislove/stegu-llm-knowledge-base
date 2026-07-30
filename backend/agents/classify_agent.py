"""
Classify agent — decides WHERE a new document belongs (category, topic,
doc_type, access, title, and whether it updates an existing page) BEFORE
anything is written. Read-only: it only has read_file/list_files/list_dirs/
grep, plus the propose_classification tool it must call to report its
decision. It never writes to the wiki.

Confidence gating happens here: if the agent isn't confident, main.py routes
the document to a pending-review queue instead of guessing. Silent
misfiling is worse than a manual step at this scale (Design Notes).
"""

from backend.agentic_loop import client
from backend.config import MODEL, SCHEMA_PATH
from backend.tools import file_tools
from backend.tools.tool_defs import CLASSIFY_TOOLS

MAX_TURNS = 8

SYSTEM_PROMPT = """You are the classification agent for a company knowledge base wiki (stone tiles and cladding company).

Your ONLY job is to propose WHERE a new document belongs — you never write
anything to the wiki; a different agent does that after your decision.

Steps:
1. Read lessons.md and index.md first, for context.
2. Check (list_files/list_dirs/grep) whether the target category is already
   split into topic subfolders — if so, verify whether this document fits
   an EXISTING topic. Never invent a new topic; that only happens via the
   dedicated split process.
3. Check whether this document updates an existing page (same product or
   subject, new source) rather than being new.
4. Once you have enough context, call propose_classification EXACTLY ONCE
   with your final decision.

Set confidence to "low" whenever you're unsure about the category, possible
duplication, or the document doesn't clearly fit an existing
category/topic — in that case the document is routed to a human review
queue, which is the correct, desired outcome here, not a failure. Don't
guess; default to "low" when in doubt.

The `title` and `reasoning` fields must be written in CZECH (the wiki and
its human reviewers are Czech-speaking). `doc_type`, `access`
stay as their fixed English enum values.

Efficiency: independent read steps (lessons.md, index.md, list_dirs) should
be requested in the SAME turn, not sequentially.

--- SCHEMA.md ---
{schema}
"""


def _dispatch(tool_name: str, tool_input: dict) -> str:
    if tool_name == "read_file":
        return file_tools.read_file(tool_input["path"])
    if tool_name == "list_files":
        return (
            "\n".join(file_tools.list_files(tool_input.get("subdir", "")))
            or "(no files)"
        )
    if tool_name == "list_dirs":
        return (
            "\n".join(file_tools.list_dirs(tool_input.get("subdir", "")))
            or "(no subfolders)"
        )
    if tool_name == "grep":
        return (
            "\n".join(
                file_tools.grep(tool_input["pattern"], tool_input.get("subdir", ""))
            )
            or "(no matches)"
        )
    raise ValueError(f"Unknown tool for classify agent: {tool_name}")


def classify_document(filename: str, content_for_llm) -> tuple:
    """
    content_for_llm: either a list of content blocks (e.g. a PDF document
    block, for native Claude reading) or a plain markdown string — same
    shape the ingest/writer agent expects.

    Returns (classification, usage):
    - classification: the propose_classification tool's input dict, e.g.
      {"category": "produkty", "topic": "", "doc_type": "catalog",
       "title": "...", "access": "public", "is_update_to": "",
       "confidence": "high", "reasoning": "..."}
    - usage: {"input_tokens", "output_tokens", "cache_creation_tokens",
      "cache_read_tokens"} — same shape agentic_loop.run_agent_loop
      returns, for the Náklady dashboard's cost estimate. This agent has
      its own loop (it exits on a specific tool call, not "no more tool
      calls", so it can't just delegate to run_agent_loop) but tracks
      usage the same way.
    """
    # SCHEMA_PATH is a OneDrive path string (Graph-backed), not a local
    # Path — reading it means a real network call via graph_client, done
    # here through file_tools.read_project_file (SCHEMA.md lives at the
    # project root, one level above WIKI_ROOT, so it can't go through
    # read_file()'s wiki-relative path handling).
    schema_text = file_tools.read_project_file(SCHEMA_PATH)
    system_prompt = SYSTEM_PROMPT.format(schema=schema_text)

    if isinstance(content_for_llm, list):
        user_content = content_for_llm + [
            {
                "type": "text",
                "text": f"New source document: {filename}\n\nDecide where it belongs.",
            }
        ]
    else:
        user_content = (
            f"New source document: {filename}\n\n"
            f"--- Document content (already converted to markdown) ---\n{content_for_llm}\n\n"
            f"Decide where it belongs."
        )

    messages = [{"role": "user", "content": user_content}]

    cached_system = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
    ]
    cached_tools = [dict(t) for t in CLASSIFY_TOOLS]
    cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}

    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
    }

    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=cached_system,
            tools=cached_tools,
            messages=messages,
        )
        usage["input_tokens"] += getattr(response.usage, "input_tokens", 0) or 0
        usage["output_tokens"] += getattr(response.usage, "output_tokens", 0) or 0
        usage["cache_creation_tokens"] += (
            getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        )
        usage["cache_read_tokens"] += (
            getattr(response.usage, "cache_read_input_tokens", 0) or 0
        )

        assistant_content = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": assistant_content})

        classification_block = next(
            (
                b
                for b in response.content
                if b.type == "tool_use" and b.name == "propose_classification"
            ),
            None,
        )
        if classification_block:
            return classification_block.input, usage

        if response.stop_reason != "tool_use":
            final_text = "".join(b.text for b in response.content if b.type == "text")
            raise RuntimeError(
                "Classify agent finished without calling propose_classification: "
                + final_text
            )

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = _dispatch(block.name, block.input)
                is_error = False
            except Exception as e:
                result = f"Error: {e}"
                is_error = True
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError("Classify agent exceeded max turns without a decision.")
