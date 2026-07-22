"""
Lint agent — runs a structural + semantic health check over the wiki and
writes a report. Deliberately report-only: it can write to lint-report.md
and NOTHING else. It never touches an actual wiki page, index.md, log.md,
lessons.md, or feedback_log.md — a human reads the report and decides what,
if anything, to fix (likely via a normal ingest/distill run, a manual edit,
or POST /split/{category}).

Triggered manually (a button in the dashboard), same MVP philosophy as
distillation — no scheduled/cron execution yet.
"""
from backend.agentic_loop import run_agent_loop
from backend.tools import file_tools, hashing
from backend.tools.tool_defs import LINT_TOOLS
from backend.config import SCHEMA_PATH, VALID_CATEGORY, TOKEN_BUDGET, FILE_COUNT_THRESHOLD

SYSTEM_PROMPT = """You are the lint agent for a company knowledge base wiki.

You run a health check over the wiki and produce a report. You do NOT fix
anything yourself — you only read and report. This keeps lint low-risk: a
wrong judgment call here is a wrong line in a report a human reads, not a
silently corrupted wiki page.

Run these checks:

1. ORPHAN PAGES — pages that exist as files under a category (or topic)
   folder but have no corresponding entry in their governing index (root
   index.md, or the closest _index.md — see SCHEMA.md §1/§6).
2. BROKEN REFERENCES — entries in an index file that point to a page which
   doesn't exist, e.g. a renamed or deleted slug.
3. STALE CLAIMS — pages whose valid_until date has passed, or whose
   last_updated is suspiciously old relative to other pages covering the
   same product/topic.
4. MISSING PROVENANCE — pages missing required frontmatter fields per
   SCHEMA.md §2 (category, doc_type, access, valid_from, source_docs).
5. CONTRADICTIONS — two or more pages asserting conflicting facts about the
   same subject. This is the check that most needs real judgment, not just
   file listing — take your time on it.
6. TOKEN BUDGET — a precomputed, deterministic check is included below
   (you do not need to calculate it yourself). List any flagged
   category/topic and note it should be split via POST /split/{{category}}.

Process:
1. Read index.md first for an overview of what should exist, and any
   _index.md files for categories that are already split.
2. Use list_files to see what actually exists in each category/topic
   folder, and compare against the governing index to find orphans/broken
   references.
3. Read pages as needed (batch independent read_file calls together in one
   turn rather than one at a time) to check frontmatter completeness,
   staleness, and cross-page contradictions.
4. Write your findings to lint-report.md using write_file — this OVERWRITES
   the previous report each run, so include the full report, not a diff.
   Structure it with a heading per check category (six headings total),
   and under each, either "No issues found" or a bullet list of specific
   pages/problems. Write descriptions in CZECH; headings can stay as the
   English section names above for consistency with prior reports.
5. Reply with a short plain-text summary: how many issues found, and
   whether anything looks urgent enough to flag prominently.

You have no other write access. Do not attempt to fix any issue you find —
report it and stop there.

--- SCHEMA.md ---
{schema}
"""


def _dispatch(tool_name: str, tool_input: dict) -> str:
    if tool_name == "read_file":
        return file_tools.read_file(tool_input["path"])
    if tool_name == "list_files":
        return "\n".join(file_tools.list_files(tool_input.get("subdir", ""))) or "(no files)"
    if tool_name == "grep":
        return "\n".join(file_tools.grep(tool_input["pattern"], tool_input.get("subdir", ""))) or "(no matches)"
    if tool_name == "write_file":
        path = tool_input["path"]
        if path != "lint-report.md":
            raise PermissionError(
                "The lint agent may only write to lint-report.md. It does not fix "
                "issues directly — report them and stop."
            )
        return file_tools.write_file(path, tool_input["content"])
    raise ValueError(f"Unknown tool for lint agent: {tool_name}")


def _budget_report() -> str:
    lines = []
    for category in sorted(VALID_CATEGORY):
        totals = hashing.folder_totals(category)
        if totals["file_count"] == 0:
            continue
        flag = " ⚠ EXCEEDED — needs split" if hashing.needs_split(category) else ""
        lines.append(
            f"- {category}: {totals['file_count']} files, "
            f"~{totals['total_tokens']} tokens{flag}"
        )
    return "\n".join(lines) or "(no data yet)"


def run_lint() -> dict:
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    system_prompt = SYSTEM_PROMPT.format(schema=schema_text)
    user_message = (
        "Run a full lint pass over the wiki now and write the report.\n\n"
        "--- Precomputed token-budget check (deterministic — do not recalculate) ---\n"
        f"Threshold: more than {FILE_COUNT_THRESHOLD} files AND more than "
        f"{TOKEN_BUDGET} tokens triggers a split flag.\n"
        f"{_budget_report()}"
    )
    return run_agent_loop(system_prompt, user_message, LINT_TOOLS, _dispatch)
