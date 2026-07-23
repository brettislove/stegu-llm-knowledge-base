"""
Split agent — manually triggered (POST /split/{category}) reorganization of
an over-budget category into topic subfolders, per SCHEMA.md §1a. The
decision of WHETHER a split is needed is deterministic
(hashing.needs_split, computed from manifest.json token counts) — this
agent only handles the semantic part: grouping existing pages into sensible
topics and creating index files for them.

Manually triggered rather than automatic, matching this MVP's existing
philosophy for higher-risk maintenance actions (same as lint/distill — no
cron, a human decides when to run it).
"""

from backend.agentic_loop import run_agent_loop
from backend.tools import file_tools, frontmatter
from backend.tools.tool_defs import SPLIT_TOOLS
from backend.tools.postprocess import finalize_page
from backend.config import SCHEMA_PATH

SYSTEM_PROMPT = """You are the split agent for a company knowledge base wiki.

Category '{category}' has crossed the index size threshold (too many pages
or too many tokens for a single flat index). Your job is to reorganize it
into topic subfolders (Layer 3), per SCHEMA.md §1a's variable-depth rule:

1. Read index.md and every page under '{category}/'.
2. Propose 2-5 sensible topics to group the pages by. Topic names must be
   lowercase, hyphenated slugs (e.g. `kamen`, `stavebni-chemie`).
3. Move each page (move_file) into '{category}/<topic>/<slug>.md' — its
   paired raw source file, if any, moves automatically with it.
4. Create '{category}/<topic>/_index.md' for each topic, with a short
   (1-2 sentence) abstract per page.
5. Create/update '{category}/_index.md' — replace the full page list with
   short 1-2 sentence links to each topic instead.
6. Update the root index.md — this category's section now shows only a
   short category abstract plus a link to '{category}/_index.md', not
   individual pages.

All page titles, abstracts, and index text must be written in CZECH.

Efficiency: request independent read_file calls for all pages in the
category in a single turn rather than one at a time.

Rules:
- move_file only relocates files, it never alters content.
- write_file always takes the FULL file content.
- Don't set id/parent/token_count/content_hash/last_updated in frontmatter —
  those are refreshed automatically after you finish.
- When finished, reply with a short CZECH summary: how many topics you
  created and which pages moved where.

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
    if tool_name == "write_file":
        return file_tools.write_file(tool_input["path"], tool_input["content"])
    if tool_name == "move_file":
        return file_tools.move_file(tool_input["src"], tool_input["dst"])
    raise ValueError(f"Unknown tool for split agent: {tool_name}")


def split_category(category: str) -> dict:
    # SCHEMA_PATH is a OneDrive path string now, not a local Path — reading
    # it means a real Graph network call (see file_tools.read_project_file).
    schema_text = file_tools.read_project_file(SCHEMA_PATH)
    system_prompt = SYSTEM_PROMPT.format(category=category, schema=schema_text)
    user_message = (
        f"Split category '{category}' into topic subfolders per the instructions above."
    )
    result = run_agent_loop(system_prompt, user_message, SPLIT_TOOLS, _dispatch)
    _refresh_manifest_for_category(category)
    return result


def _refresh_manifest_for_category(category: str) -> None:
    """
    After a split moves pages around, recompute their manifest entries (new
    path, new parent) — deterministic, no LLM involved. Content itself
    didn't change, so the original content_hash is preserved.
    """
    for rel_path in file_tools.list_files(category):
        if rel_path.endswith("_index.md"):
            continue
        content = file_tools.read_file(rel_path)
        fields, _ = frontmatter.parse(content)
        old_hash = fields.get("content_hash")
        if not old_hash:
            continue
        parts = rel_path.split("/")
        topic = parts[1] if len(parts) == 3 else None
        finalize_page(rel_path, category, topic, old_hash)
