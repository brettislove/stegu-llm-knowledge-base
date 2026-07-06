"""
Ingest agent — takes an already-converted markdown source document (from
your existing PDF-to-markdown step) and folds it into the wiki, per
SCHEMA.md §8. Has write access.
"""
from typing import Optional

from backend.agentic_loop import run_agent_loop
from backend.tools import file_tools
from backend.tools.tool_defs import INGEST_TOOLS
from backend.config import SCHEMA_PATH

SYSTEM_PROMPT = """You are the ingest agent for a company knowledge base wiki (stone tiles and apparel company).

You will be given the content of one newly converted source document
(originally a PDF). Fold its content into the wiki, following SCHEMA.md
exactly (included below).

Steps:
1. Read lessons.md and index.md first, for context and standing rules.
2. Decide whether this document updates an existing page or requires a new
   one. Use list_files/grep on the relevant category folder to check before
   assuming it's new.
3. Write the page: full content, valid YAML frontmatter (category, doc_type,
   access, valid_from, source_docs are all required — see SCHEMA.md §2).
4. Update index.md to add or update the one-line entry for this page.
5. Append one entry to log.md summarizing what changed.

Efficiency: whenever multiple steps don't depend on each other's results,
request them as multiple tool calls in the SAME turn rather than one at a
time. For example, reading lessons.md, index.md, and listing the relevant
category folder are all independent — request all three together in your
first turn. Likewise, once you know the page content, index update, and log
entry, you can write all three in one turn rather than three separate ones.
Only sequence calls when a later one genuinely needs an earlier one's result
(e.g. you can't write the page before deciding what it should say).

Rules:
- category must be one of VALID_CATEGORY. doc_type must be one of VALID_DOC_TYPE.
- Never delete a page. If a product is discontinued, set status: discontinued
  on the products page and add a redirect note instead of removing it.
- write_file always takes the FULL file content — never a partial diff.
- If lessons.md contains a rule relevant to this document (e.g. a pricing
  correction, a discontinued product), apply it during ingestion.
- When finished, reply with a short plain-text summary of what you did. This
  summary is shown to a human operator, not stored in the wiki.

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
        return file_tools.write_file(tool_input["path"], tool_input["content"])
    if tool_name == "append_log":
        return file_tools.append_log(tool_input["path"], tool_input["entry"])
    raise ValueError(f"Unknown tool for ingest agent: {tool_name}")


def ingest_document(filename: str, pdf_base64: Optional[str] = None, markdown: Optional[str] = None) -> dict:
    """
    Exactly one of pdf_base64 / markdown should be provided.

    pdf_base64: raw PDF, base64-encoded — Claude reads it natively via the
    document content type, no separate conversion step needed.

    markdown: already-converted markdown (e.g. from an existing pipeline, or
    a source that was never a PDF to begin with). Sent as plain text.
    """
    if bool(pdf_base64) == bool(markdown):
        raise ValueError("Provide exactly one of pdf_base64 or markdown, not both/neither.")

    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    system_prompt = SYSTEM_PROMPT.format(schema=schema_text)

    if pdf_base64:
        user_message = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf_base64,
                },
            },
            {
                "type": "text",
                "text": (
                    f"New source document: {filename}\n\n"
                    f"Read this PDF and fold its content into the wiki, following "
                    f"the steps and SCHEMA.md above."
                ),
            },
        ]
    else:
        user_message = (
            f"New source document: {filename}\n\n"
            f"--- Document content (already converted to markdown) ---\n{markdown}"
        )

    return run_agent_loop(system_prompt, user_message, INGEST_TOOLS, _dispatch)
