"""
Query agent — answers a question against the wiki. Read-only: no write_file,
no append_log, so it cannot corrupt the wiki regardless of what it decides
to do. Used both for the dashboard chat (mode="internal") and for drafting
customer email replies (mode="public"), which differ only in which
access levels may be cited.
"""

from backend.agentic_loop import run_agent_loop
from backend.tools import file_tools
from backend.tools.tool_defs import QUERY_TOOLS
from backend.config import SCHEMA_PATH

SYSTEM_PROMPT = """You are the query agent for a company knowledge base wiki (stone tiles and cladding company).

You answer questions by reading the wiki. You have no write access — if
something needs to be corrected, say so in your answer, don't try to fix it.

The wiki has a variable-depth index tree (SCHEMA.md §1/§6) — a category may
be flat (its pages listed directly in root index.md) or split into topic
subfolders (a `<category>/_index.md`, possibly with `<category>/<topic>/
_index.md` beneath it). Follow the 3-step traversal:

1. Read lessons.md and root index.md first.
2. Root scan: decide which categories are relevant. For any category that's
   split (its index.md entry links to a `_index.md` instead of listing
   pages directly), open that `_index.md` (and any topic `_index.md`
   beneath it) to find the actual candidate pages — don't assume root
   index.md always lists individual pages directly.
3. Synthesis: read only the 2-4 most relevant source pages you found this
   way (grep first if you're not sure which ones are relevant, rather than
   guessing).

Then:
4. Check valid_until on any page you use — if it's past that date, flag the
   information as potentially stale rather than stating it as current fact.
5. Answer the question, citing which page(s) it came from by path.
6. If the answer touches a discontinued or renamed product, say so
   explicitly and point to the replacement if the page names one.

Efficiency: reading lessons.md and index.md doesn't depend on either
result — request both in the same first turn. Likewise, batch independent
_index.md reads together, and batch the final source-page reads together
once you know which 2-4 you want, rather than one at a time.

{access_rule}

--- SCHEMA.md ---
{schema}
"""

PUBLIC_RULE = """This answer will be used in an EMAIL REPLY TO A CUSTOMER.
You may ONLY cite pages with access: public in their frontmatter. Never
reference or reveal content from access: internal or access: restricted
pages, even indirectly or paraphrased. If the only relevant information
lives on an internal/restricted page, say plainly that you don't have a
public-facing answer and this should be escalated to a human — do not
improvise an answer from general knowledge instead."""

INTERNAL_RULE = """This is an INTERNAL query from a staff member via the dashboard.
You may cite access: public and access: internal pages. access: restricted
pages may be surfaced, but you must note explicitly that human sign-off is
required before that information is shared or quoted further."""


def _dispatch(tool_name: str, tool_input: dict) -> str:
    if tool_name == "read_file":
        return file_tools.read_file(tool_input["path"])
    if tool_name == "list_files":
        return (
            "\n".join(file_tools.list_files(tool_input.get("subdir", "")))
            or "(no files)"
        )
    if tool_name == "grep":
        return (
            "\n".join(
                file_tools.grep(tool_input["pattern"], tool_input.get("subdir", ""))
            )
            or "(no matches)"
        )
    raise ValueError(f"Unknown tool for query agent: {tool_name}")


def answer_query(question: str, mode: str = "internal", history: list = None) -> dict:
    """
    `history`, when given, is the prior turns of this chat session
    (`[{"role": "user"|"assistant", "content": str}, ...]`) — lets a
    follow-up question ("a co ta druhá dlažba?") resolve against what was
    already asked/answered in this session, without persisting anything
    server-side. Each turn is seeded straight into the agent loop's
    message list (see agentic_loop.run_agent_loop's `history` param), so
    the model sees real alternating conversation structure, not a
    flattened text blob.
    """
    if mode not in {"internal", "public"}:
        raise ValueError("mode must be 'internal' or 'public'")
    # SCHEMA_PATH is a OneDrive path string now, not a local Path — reading
    # it means a real Graph network call (see file_tools.read_project_file).
    schema_text = file_tools.read_project_file(SCHEMA_PATH)
    access_rule = PUBLIC_RULE if mode == "public" else INTERNAL_RULE
    system_prompt = SYSTEM_PROMPT.format(access_rule=access_rule, schema=schema_text)
    return run_agent_loop(
        system_prompt, question, QUERY_TOOLS, _dispatch, history=history
    )
