"""
Anthropic tool-use schemas. Each agent gets a different subset — this is
what actually enforces "query agent can't write" at the API level, not just
by convention.
"""

READ_FILE = {
    "name": "read_file",
    "description": (
        "Read the full content of one markdown file in the wiki, by its path "
        "relative to the wiki root, e.g. 'products/verona-basalt-tile.md' or "
        "'index.md'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to wiki root."}
        },
        "required": ["path"],
    },
}

LIST_FILES = {
    "name": "list_files",
    "description": (
        "List all markdown files in the wiki, optionally restricted to one "
        "category subfolder (e.g. 'products'). Leave subdir empty to list "
        "the whole wiki."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "subdir": {"type": "string", "description": "Optional category subfolder."}
        },
    },
}

GREP = {
    "name": "grep",
    "description": (
        "Case-insensitive regex search across all wiki markdown files. Returns "
        "matching lines as 'path:line_number: line_text'. Use this to find "
        "where a keyword/product name appears before deciding which pages to read."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for."},
            "subdir": {"type": "string", "description": "Optional category subfolder to restrict to."},
        },
        "required": ["pattern"],
    },
}

WRITE_FILE = {
    "name": "write_file",
    "description": (
        "Create or overwrite one markdown page. Path must be either a "
        "top-level file (index.md, lessons.md) or '<category>/<slug>.md' "
        "where <category> is one of the VALID_CATEGORY folders. Always pass "
        "the FULL file content (frontmatter + body) — this overwrites the "
        "entire file, not a diff."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to wiki root."},
            "content": {"type": "string", "description": "Full file content, including YAML frontmatter."},
        },
        "required": ["path", "content"],
    },
}

APPEND_LOG = {
    "name": "append_log",
    "description": (
        "Append one new entry to log.md or feedback_log.md. Append-only — "
        "never use this to rewrite or remove existing entries."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "enum": ["log.md", "feedback_log.md"]},
            "entry": {"type": "string", "description": "The markdown entry to append."},
        },
        "required": ["path", "entry"],
    },
}

# Tool sets per agent — mirrors SCHEMA.md §8 permissions exactly.
INGEST_TOOLS = [READ_FILE, LIST_FILES, GREP, WRITE_FILE, APPEND_LOG]
QUERY_TOOLS = [READ_FILE, LIST_FILES, GREP]          # read-only, no write access
DISTILL_TOOLS = [READ_FILE, LIST_FILES, WRITE_FILE]   # no append_log — see distill_agent.py
LINT_TOOLS = [READ_FILE, LIST_FILES, GREP, WRITE_FILE]  # write restricted to lint-report.md only, enforced in lint_agent.py's dispatch
