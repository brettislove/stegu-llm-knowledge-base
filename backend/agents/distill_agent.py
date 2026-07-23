"""
Distill agent — processes raw feedback_log.md entries into either direct
corrections to wiki pages, or merged/deduped standing rules in lessons.md.
Triggered manually (a "Review feedback" button in the dashboard for the
MVP — no cron job yet).

Note: when this agent edits a page's body directly (a factual correction),
its token_count frontmatter field goes stale until the next deterministic
refresh — main.py calls tools/postprocess.py:refresh_token_counts() right
after run_distillation() returns, so this agent doesn't need to worry about
it.
"""

from backend.agentic_loop import run_agent_loop
from backend.tools import file_tools
from backend.tools.tool_defs import DISTILL_TOOLS
from backend.config import SCHEMA_PATH

SYSTEM_PROMPT = """You are the distillation agent for a company knowledge base wiki.

You turn raw human feedback into permanent improvements, per SCHEMA.md §7.

Steps:
1. Read feedback_log.md and find entries marked 'status: unprocessed'.
2. Read the current lessons.md.
3. For each unprocessed entry, decide:
   - FACTUAL error (the wiki content itself is wrong or outdated): read the
     relevant page(s) with list_files/read_file, correct them directly, and
     update last_updated in that page's frontmatter.
   - BEHAVIORAL rule (tone, formatting, a standing correction like "always
     quote prices in CZK"): merge it into lessons.md. If it overlaps an
     existing lesson, tighten or edit that lesson rather than adding a
     near-duplicate line.
4. Rewrite feedback_log.md with the entries you processed marked
   'status: processed' instead of 'status: unprocessed' (use write_file with
   the FULL updated file content — you are editing existing entries in
   place, not appending, so append_log is not available to you here).
5. Reply with a short plain-text summary of what you changed and why.

Efficiency: reading feedback_log.md and lessons.md doesn't depend on either
result — request both in the same first turn rather than sequentially.

Rules:
- Never touch index.md, _index.md files, or log.md — those belong to the
  ingest/split agents only.
- write_file always takes the FULL file content, never a partial diff.
- Page corrections should stay in CZECH, matching the rest of the wiki.

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
    if tool_name == "write_file":
        path = tool_input["path"]
        if path == "index.md" or path.endswith("_index.md") or path == "log.md":
            raise PermissionError(
                "The distill agent is not permitted to write index.md, any "
                "_index.md file, or log.md."
            )
        return file_tools.write_file(path, tool_input["content"])
    raise ValueError(f"Unknown tool for distill agent: {tool_name}")


def run_distillation() -> dict:
    # SCHEMA_PATH is a OneDrive path string now, not a local Path — reading
    # it means a real Graph network call (see file_tools.read_project_file).
    schema_text = file_tools.read_project_file(SCHEMA_PATH)
    system_prompt = SYSTEM_PROMPT.format(schema=schema_text)
    user_message = "Process all unprocessed entries in feedback_log.md now."
    return run_agent_loop(system_prompt, user_message, DISTILL_TOOLS, _dispatch)
