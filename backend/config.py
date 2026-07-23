"""
Config for the OneDrive-backed backend.

Local-disk version used pathlib.Path objects as roots and pre-created
directories with .mkdir() at import time. There's no real filesystem here,
so the roots below are plain path *strings*, relative to the root of one
shared OneDrive drive (see GraphClient / DRIVE_USER). Folder creation is
no longer eager at import time — Graph folders are created on demand by
graph_client.ensure_folder() the first time something is written under
them (see file_tools.write_file/write_binary), since there's no cheap
local equivalent of "just mkdir it, it's practically free."

SCHEMA_PATH and CLAUDE_MD_PATH live at the OneDrive project root
(ONEDRIVE_PROJECT_ROOT, i.e. "STEGU_WIKI/"), one level *above* wiki/ —
not inside it. This mirrors the old local layout exactly: PROJECT_ROOT
used to be the parent of wiki/, raw/, pending_review/, and archive/, and
held SCHEMA.md as a sibling of wiki/, not a child of it. Moving to
OneDrive just renames that same parent folder to STEGU_WIKI/ instead of
a local directory; the parent/child relationships are unchanged.

(An earlier version of this file put SCHEMA_PATH under WIKI_ROOT itself
— e.g. wiki/SCHEMA.md — which was wrong; corrected here to match the
confirmed real structure: STEGU_WIKI/SCHEMA.md, STEGU_WIKI/CLAUDE.md,
STEGU_WIKI/wiki/, STEGU_WIKI/raw/, STEGU_WIKI/pending_review/,
STEGU_WIKI/archive/.)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from backend.graph_client import GraphClient

load_dotenv()

LOCAL_PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent
)  # local code checkout, not OneDrive

# OneDrive path strings, all relative to the drive root. No leading/
# trailing slashes — file_tools.py and hashing.py join onto these
# directly. ONEDRIVE_PROJECT_ROOT is the project folder itself (its real
# name has a space — "STEGU WIKI" — and it lives inside a "Claude Cowork"
# folder in a colleague's OneDrive, not the drive-root top-level folder
# the name might suggest); every other root is a child of it.
#
# GRAPH_DRIVE_USER must be set to the UPN of whoever's OneDrive actually
# contains this folder — not necessarily the same person running the
# backend. Files.ReadWrite.All (app-only) is what makes cross-user access
# like this possible at all; a narrower Sites.Selected-style grant would
# not reach another user's personal drive.
ONEDRIVE_PROJECT_ROOT = os.environ.get("ONEDRIVE_PROJECT_ROOT", "STEGU_WIKI")
WIKI_ROOT = f"{ONEDRIVE_PROJECT_ROOT}/wiki"
RAW_ROOT = f"{ONEDRIVE_PROJECT_ROOT}/raw"
PENDING_REVIEW_ROOT = f"{ONEDRIVE_PROJECT_ROOT}/pending_review"
ARCHIVE_ROOT = f"{ONEDRIVE_PROJECT_ROOT}/archive"
MANIFEST_PATH = f"{WIKI_ROOT}/manifest.json"
SCHEMA_PATH = f"{ONEDRIVE_PROJECT_ROOT}/SCHEMA.md"
CLAUDE_MD_PATH = f"{ONEDRIVE_PROJECT_ROOT}/CLAUDE.md"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

# --- Graph API / OneDrive auth ---
# Client-credentials (app-only) flow — see the Phase 1 setup guide for how
# these are obtained (Azure AD app registration + admin consent for
# Files.ReadWrite.All). Required at import time: if any of these are
# missing, every Graph call will fail immediately and loudly rather than
# quietly falling back to some other behavior.
GRAPH_TENANT_ID = os.environ["GRAPH_TENANT_ID"]
GRAPH_CLIENT_ID = os.environ["GRAPH_CLIENT_ID"]
GRAPH_CLIENT_SECRET = os.environ["GRAPH_CLIENT_SECRET"]
GRAPH_DRIVE_USER = os.environ["GRAPH_DRIVE_USER"]  # UPN of the OneDrive owner

# Single shared client instance — file_tools.py, hashing.py, and main.py
# all import this rather than constructing their own, so there's one
# token cache for the whole process (see GraphClient._get_token).
graph_client = GraphClient(
    tenant_id=GRAPH_TENANT_ID,
    client_id=GRAPH_CLIENT_ID,
    client_secret=GRAPH_CLIENT_SECRET,
    drive_user=GRAPH_DRIVE_USER,
)

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
TOP_LEVEL_FILES = {
    "index.md",
    "log.md",
    "lessons.md",
    "feedback_log.md",
    "lint-report.md",
}

# --- Layered-index / token-budget settings (Design Notes §1a) ---
# Approximate — see tools/hashing.py:estimate_tokens. A category/topic is
# flagged for splitting only once it crosses BOTH thresholds, so a folder
# with many tiny files or one with a few huge ones doesn't get flagged
# prematurely.
TOKEN_BUDGET = 3000
FILE_COUNT_THRESHOLD = 45

# NOTE: the old eager `for _dir in (...): _dir.mkdir(parents=True, exist_ok=True)`
# is gone. Root-folder creation for wiki/, raw/, pending_review/, archive/
# now happens explicitly once, during the Phase 1 "create OneDrive folder
# structure" step (see setup script) — not on every process start. If you
# need it idempotent on every startup too, call:
#   for _root in (WIKI_ROOT, RAW_ROOT, PENDING_REVIEW_ROOT, ARCHIVE_ROOT):
#       graph_client.ensure_folder(_root)
# from main.py's startup, but note each call is a real HTTP round-trip,
# unlike the old free local mkdir.
