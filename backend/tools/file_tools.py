"""
Low-level, sandboxed file operations against wiki/.

All paths passed in by agents are relative to WIKI_ROOT and are validated to
prevent escaping it. These functions are what the tool-use loop actually
calls when Claude invokes read_file / write_file / list_files / grep /
append_log (see tool_defs.py for the schemas Claude sees).
"""
import re
from pathlib import Path
from typing import List

from backend.config import WIKI_ROOT, VALID_CATEGORY, TOP_LEVEL_FILES


class PathError(ValueError):
    pass


def _resolve(relative_path: str) -> Path:
    if not relative_path or relative_path.startswith("/") or ".." in Path(relative_path).parts:
        raise PathError(f"Invalid or unsafe path: {relative_path!r}")
    resolved = (WIKI_ROOT / relative_path).resolve()
    if resolved != WIKI_ROOT and WIKI_ROOT not in resolved.parents:
        raise PathError(f"Path escapes wiki root: {relative_path!r}")
    return resolved


def list_files(subdir: str = "") -> List[str]:
    """List all markdown files under wiki/, optionally scoped to one category folder."""
    base = _resolve(subdir) if subdir else WIKI_ROOT
    if not base.exists():
        return []
    return sorted(
        str(p.relative_to(WIKI_ROOT))
        for p in base.rglob("*.md")
        if p.is_file()
    )


def read_file(relative_path: str) -> str:
    path = _resolve(relative_path)
    if not path.exists():
        raise FileNotFoundError(f"No such file in wiki: {relative_path}")
    return path.read_text(encoding="utf-8")


def write_file(relative_path: str, content: str) -> str:
    """
    Create or overwrite a page. Enforces SCHEMA.md §1: writes must target
    either a known top-level file or '<valid_category>/<slug>.md'.
    """
    parts = Path(relative_path).parts
    if len(parts) == 1:
        if relative_path not in TOP_LEVEL_FILES:
            raise PathError(
                f"Top-level writes are only allowed to {sorted(TOP_LEVEL_FILES)}, "
                f"got {relative_path!r}"
            )
    else:
        if parts[0] not in VALID_CATEGORY:
            raise PathError(
                f"{parts[0]!r} is not a valid category folder. "
                f"Must be one of {sorted(VALID_CATEGORY)}."
            )
    path = _resolve(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {relative_path}"


def append_log(relative_path: str, entry: str) -> str:
    """Append-only write. Only valid for log.md and feedback_log.md."""
    if relative_path not in {"log.md", "feedback_log.md"}:
        raise PathError("append_log may only target log.md or feedback_log.md")
    path = _resolve(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_separator = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8") as f:
        if needs_separator:
            f.write("\n\n")
        f.write(entry.strip() + "\n")
    return f"Appended entry to {relative_path}"


def grep(pattern: str, subdir: str = "") -> List[str]:
    """Case-insensitive regex search across wiki markdown files."""
    base = _resolve(subdir) if subdir else WIKI_ROOT
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")
    matches = []
    for path in base.rglob("*.md"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(WIKI_ROOT))
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{rel}:{i}: {line.strip()}")
    return matches
