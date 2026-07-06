import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIKI_ROOT = PROJECT_ROOT / "wiki"
RAW_ROOT = PROJECT_ROOT / "raw"
SCHEMA_PATH = PROJECT_ROOT / "SCHEMA.md"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

# Mirrors VALID_CATEGORY / VALID_DOC_TYPE from SCHEMA.md — keep these two
# in sync any time the schema changes.
VALID_CATEGORY = {
    "installation",
    "chemistry",
    "products",
    "complaints",
    "logistics",
    "business",
    "general",
    "pricing",
    "internal_process",
}

VALID_DOC_TYPE = {
    "guide",
    "tech_sheet",
    "faq",
    "catalog",
    "policy",
    "certificate",
}

VALID_ACCESS = {"public", "internal", "restricted"}

# Files allowed to live at the wiki root (outside category folders)
TOP_LEVEL_FILES = {"index.md", "log.md", "lessons.md", "feedback_log.md", "lint-report.md"}
