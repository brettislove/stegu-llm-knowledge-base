"""
Ingest agent (writer) — given an already-decided classification (from
classify_agent.py) and an explicit destination path (resolved
deterministically by main.py), writes the page content, updates the
correct governing index (root / domain / topic — also resolved
beforehand), and appends a log entry. Has write access.

System bookkeeping fields (id, layer, parent, token_count, content_hash,
last_updated) are NOT this agent's job — main.py patches those into the
frontmatter automatically after this returns (see tools/postprocess.py),
using deterministic hash/token-count logic. This agent only needs to get
the CONTENT right.
"""
from backend.agentic_loop import run_agent_loop
from backend.tools import file_tools
from backend.tools.tool_defs import INGEST_TOOLS
from backend.config import SCHEMA_PATH

SYSTEM_PROMPT = """You are the ingest agent (writer) for a company knowledge base wiki (stone tiles and cladding company).

Classification has already been decided (category, topic, doc_type, access,
title — given below, along with the exact path to write to). Your job is
only to write the page CONTENT and update the correct index — you do not
re-decide where this belongs.

Steps:
1. Write the page at the EXACT destination path given below (write_file).
   Required frontmatter: title, category, doc_type, access, valid_from,
   source_docs (see SCHEMA.md §2). Do NOT set id, layer, parent,
   token_count, content_hash, or last_updated — those are filled in
   automatically after you finish.
2. Update the given "governing index" file — add or update the one-line
   entry for this page under the right heading (create the heading if it
   doesn't exist yet).
3. Append one entry to log.md summarizing what changed (same style as
   existing entries: "Created:"/"Updated:" bullets).

All USER-FACING CONTENT — page title, page body, index entries, and log
descriptions — must be written in CZECH. Code-level values (doc_type,
access, file paths) stay as their fixed English enum values.

Efficiency: once you know the page content, the index update, and the log
entry, request all three write/append calls in the SAME turn rather than
one at a time.

Rules:
- write_file always takes the FULL file content — never a partial diff.
- Never delete a page. If a product is discontinued, set
  status: discontinued and add a redirect note instead of removing it.
- If lessons.md contains a rule relevant to this document, apply it.
- When finished, reply with a short summary IN CZECH of what you did — this
  is shown to a human operator, not stored in the wiki.

--- SCHEMA.md ---
{schema}
"""


def _dispatch(tool_name: str, tool_input: dict) -> str:
    if tool_name == "read_file":
        return file_tools.read_file(tool_input["path"])
    if tool_name == "list_files":
        return "\n".join(file_tools.list_files(tool_input.get("subdir", ""))) or "(no files)"
    if tool_name == "list_dirs":
        return "\n".join(file_tools.list_dirs(tool_input.get("subdir", ""))) or "(no subfolders)"
    if tool_name == "grep":
        return "\n".join(file_tools.grep(tool_input["pattern"], tool_input.get("subdir", ""))) or "(no matches)"
    if tool_name == "write_file":
        return file_tools.write_file(tool_input["path"], tool_input["content"])
    if tool_name == "append_log":
        return file_tools.append_log(tool_input["path"], tool_input["entry"])
    raise ValueError(f"Unknown tool for ingest agent: {tool_name}")


def write_page(
    filename: str,
    content_for_llm,
    destination_path: str,
    governing_index_path: str,
    classification: dict,
) -> dict:
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    system_prompt = SYSTEM_PROMPT.format(schema=schema_text)

    instructions = (
        f"New source document: {filename}\n\n"
        f"Decided classification (already approved, do not change it):\n"
        f"- category: {classification['category']}\n"
        f"- topic: {classification.get('topic') or '(none)'}\n"
        f"- doc_type: {classification['doc_type']}\n"
        f"- title: {classification['title']}\n"
        f"- access: {classification['access']}\n"
        f"- is_update_to: {classification.get('is_update_to') or '(new page)'}\n\n"
        f"Exact path to write the page to: {destination_path}\n"
        f"Index file to update: {governing_index_path}\n\n"
    )

    if isinstance(content_for_llm, list):
        user_content = content_for_llm + [{"type": "text", "text": instructions}]
    else:
        user_content = instructions + f"--- Document content ---\n{content_for_llm}"

    return run_agent_loop(system_prompt, user_content, INGEST_TOOLS, _dispatch)
