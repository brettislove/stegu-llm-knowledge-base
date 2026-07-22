import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIKI_ROOT = PROJECT_ROOT / "wiki"
RAW_ROOT = PROJECT_ROOT / "raw"
SCHEMA_PATH = PROJECT_ROOT / "SCHEMA.md"

# New for the layered-index design:
PENDING_REVIEW_ROOT = PROJECT_ROOT / "pending_review"
ARCHIVE_ROOT = PROJECT_ROOT / "archive"
MANIFEST_PATH = WIKI_ROOT / "manifest.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

# Mirrors VALID_CATEGORY / VALID_DOC_TYPE from SCHEMA.md — keep these two
# in sync any time the schema changes.
VALID_CATEGORY = {
    "system",
    "firma",
    "produkty",
    "ceniky-a-kalkulace",
    "certifikace",
    "montaz-a-navody",
    "logistika",
    "marketing",
    "data-a-analyzy",
    "nastroje",
    "pravo-a-admin",
}

# "index" added for domain/topic index files introduced by the layered
# structure — a deliberate schema change, flagged per SCHEMA.md §1.
VALID_DOC_TYPE = {
    "guide",
    "tech_sheet",
    "faq",
    "catalog",
    "policy",
    "certificate",
    "index",
}

VALID_ACCESS = {"public", "internal", "restricted"}

# Files allowed to live at the wiki root (outside category folders)
TOP_LEVEL_FILES = {"index.md", "log.md", "lessons.md", "feedback_log.md", "lint-report.md"}

# --- Layered-index / token-budget settings (Design Notes §1a) ---
# Approximate — see tools/hashing.py:estimate_tokens. A category/topic is
# flagged for splitting only once it crosses BOTH thresholds, so a folder
# with many tiny files or one with a few huge ones doesn't get flagged
# prematurely.
TOKEN_BUDGET = 3000
FILE_COUNT_THRESHOLD = 45

for _dir in (WIKI_ROOT, RAW_ROOT, PENDING_REVIEW_ROOT, ARCHIVE_ROOT):
    _dir.mkdir(parents=True, exist_ok=True)
