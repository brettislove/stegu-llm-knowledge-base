"""
Query agent — answers a question against the wiki. Read-only: no write_file,
no append_log, so it cannot corrupt the wiki regardless of what it decides
to do. Used both for the dashboard chat (mode="internal") and for drafting
customer email replies (mode="customer_email"), which differ only in which
access levels may be cited.
"""
from backend.agentic_loop import run_agent_loop
from backend.tools import file_tools
from backend.tools.tool_defs import QUERY_TOOLS
from backend.config import SCHEMA_PATH

SYSTEM_PROMPT = """You are the query agent for a company knowledge base wiki (stone tiles and apparel company).

You answer questions by reading the wiki. You have no write access — if
something needs to be corrected, say so in your answer, don't try to fix it.

Steps:
1. Read lessons.md and index.md first.
2. Pick the 2-4 most relevant pages and read them (grep first if you're not
   sure which pages are relevant, rather than guessing).
3. Check valid_until on any page you use — if it's past that date, flag the
   information as potentially stale rather than stating it as current fact.
4. Answer the question, citing which page(s) it came from by path.
5. If the answer touches a discontinued or renamed product, say so explicitly
   and point to the replacement if the page names one.

Efficiency: reading lessons.md and index.md doesn't depend on either result —
request both in the same first turn. If you already know which 2-4 pages you
want after reading the index, request all of those read_file calls together
in one turn rather than one at a time.

{access_rule}

--- SCHEMA.md ---
{schema}
"""

CUSTOMER_EMAIL_RULE = """This answer will be used in an EMAIL REPLY TO A CUSTOMER.
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
        return "\n".join(file_tools.list_files(tool_input.get("subdir", ""))) or "(no files)"
    if tool_name == "grep":
        return "\n".join(file_tools.grep(tool_input["pattern"], tool_input.get("subdir", ""))) or "(no matches)"
    raise ValueError(f"Unknown tool for query agent: {tool_name}")


def answer_query(question: str, mode: str = "internal") -> dict:
    if mode not in {"internal", "customer_email"}:
        raise ValueError("mode must be 'internal' or 'customer_email'")
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    access_rule = CUSTOMER_EMAIL_RULE if mode == "customer_email" else INTERNAL_RULE
    system_prompt = SYSTEM_PROMPT.format(access_rule=access_rule, schema=schema_text)
    return run_agent_loop(system_prompt, question, QUERY_TOOLS, _dispatch)
