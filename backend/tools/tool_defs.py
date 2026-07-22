"""
Anthropic tool-use schemas. Each agent gets a different subset — this is
what actually enforces "query agent can't write" (and "classify agent can't
write at all") at the API level, not just by convention.
"""
from backend.config import VALID_CATEGORY, VALID_DOC_TYPE, VALID_ACCESS

READ_FILE = {
    "name": "read_file",
    "description": (
        "Read the full content of one markdown file in the wiki, by its path "
        "relative to the wiki root, e.g. 'products/verona-basalt-tile.md', "
        "'products/_index.md', or 'index.md'."
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
        "category (or category/topic) subfolder, e.g. 'products' or "
        "'products/kamen'. Leave subdir empty to list the whole wiki."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "subdir": {"type": "string", "description": "Optional category/topic subfolder."}
        },
    },
}

LIST_DIRS = {
    "name": "list_dirs",
    "description": (
        "List immediate subfolders under a wiki path. Use this to check "
        "whether a category is already split into topic subfolders (Layer "
        "3) before proposing a destination or a new topic."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "subdir": {"type": "string", "description": "Category folder, or empty for wiki root."}
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
        "Create or overwrite one markdown page or index file. Path must be "
        "either a top-level file (index.md, lessons.md), or "
        "'<category>/[topic/]<slug-or-_index>.md'. Always pass the FULL file "
        "content — this overwrites the entire file, not a diff."
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

MOVE_FILE = {
    "name": "move_file",
    "description": (
        "Move an existing page (and its paired raw source file, if any) to "
        "a new path within the wiki. Used only when reorganizing a category "
        "into topic subfolders — never during normal ingestion."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "Current path, relative to wiki root."},
            "dst": {"type": "string", "description": "New path, relative to wiki root."},
        },
        "required": ["src", "dst"],
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

PROPOSE_CLASSIFICATION = {
    "name": "propose_classification",
    "description": (
        "Report your final decision about where a new document belongs. "
        "Call this exactly once, after you've read enough context to decide. "
        "You do not write anything yourself — a different agent acts on this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": sorted(VALID_CATEGORY)},
            "topic": {
                "type": "string",
                "description": (
                    "Existing topic subfolder slug within the category, if the "
                    "category is already split and one clearly fits. Empty "
                    "string if not applicable — never invent a new topic here."
                ),
            },
            "doc_type": {"type": "string", "enum": sorted(VALID_DOC_TYPE)},
            "title": {"type": "string", "description": "Human-readable page title, in Czech."},
            "access": {"type": "string", "enum": sorted(VALID_ACCESS)},
            "is_update_to": {
                "type": "string",
                "description": (
                    "Path of an existing page this document updates, if any "
                    "(same product/subject, new source). Empty string if new."
                ),
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "low"],
                "description": "Default to 'low' whenever unsure — it routes to human review instead of guessing.",
            },
            "reasoning": {
                "type": "string",
                "description": "One or two sentences explaining the decision, in Czech.",
            },
        },
        "required": ["category", "doc_type", "title", "access", "confidence", "reasoning"],
    },
}

# Tool sets per agent — mirrors SCHEMA.md §8 permissions exactly.
CLASSIFY_TOOLS = [READ_FILE, LIST_FILES, LIST_DIRS, GREP, PROPOSE_CLASSIFICATION]
INGEST_TOOLS = [READ_FILE, LIST_FILES, LIST_DIRS, GREP, WRITE_FILE, APPEND_LOG]
QUERY_TOOLS = [READ_FILE, LIST_FILES, GREP]              # read-only, no write access
DISTILL_TOOLS = [READ_FILE, LIST_FILES, WRITE_FILE]        # no append_log — see distill_agent.py
LINT_TOOLS = [READ_FILE, LIST_FILES, GREP, WRITE_FILE]      # write restricted to lint-report.md, enforced in lint_agent.py
SPLIT_TOOLS = [READ_FILE, LIST_FILES, LIST_DIRS, WRITE_FILE, MOVE_FILE]  # manual trigger only
