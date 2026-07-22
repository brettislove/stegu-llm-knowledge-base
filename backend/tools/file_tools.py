"""
Low-level, sandboxed file operations against wiki/.

All paths passed in by agents are relative to WIKI_ROOT and are validated to
prevent escaping it. These functions are what the tool-use loop actually
calls when Claude invokes read_file / write_file / list_files / list_dirs /
grep / append_log / move_file (see tool_defs.py for the schemas Claude
sees). Deletion, archiving, and index-reference cleanup are deliberately
NOT exposed as agent tools — they're deterministic operations triggered
directly by main.py, never by model judgment.
"""
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from backend.config import WIKI_ROOT, VALID_CATEGORY, TOP_LEVEL_FILES, ARCHIVE_ROOT


class PathError(ValueError):
    pass


def _resolve(relative_path: str, root: Path = WIKI_ROOT) -> Path:
    if not relative_path or relative_path.startswith("/") or ".." in Path(relative_path).parts:
        raise PathError(f"Invalid or unsafe path: {relative_path!r}")
    resolved = (root / relative_path).resolve()
    if resolved != root and root not in resolved.parents:
        raise PathError(f"Path escapes wiki root: {relative_path!r}")
    return resolved


def slugify(text: str) -> str:
    """Lowercase, hyphenated, ASCII slug — strips Czech diacritics rather
    than failing on them (e.g. 'Žula' -> 'zula')."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "page"


def list_files(subdir: str = "") -> List[str]:
    """List all wiki pages, optionally scoped to one category/topic folder.
    Excludes manifest.json (not a page) but includes _index.md files."""
    base = _resolve(subdir) if subdir else WIKI_ROOT
    if not base.exists():
        return []
    return sorted(
        str(p.relative_to(WIKI_ROOT))
        for p in base.rglob("*.md")
        if p.is_file()
    )


def list_dirs(subdir: str = "") -> List[str]:
    """List immediate subfolders — used to discover existing topic splits
    before proposing a new one."""
    base = _resolve(subdir) if subdir else WIKI_ROOT
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def read_file(relative_path: str) -> str:
    path = _resolve(relative_path)
    if not path.exists():
        raise FileNotFoundError(f"No such file in wiki: {relative_path}")
    return path.read_text(encoding="utf-8")


def _validate_write_path(relative_path: str) -> None:
    """
    Enforces SCHEMA.md §1: a write must target either a known top-level
    file, or '<category>/[topic/]<slug-or-_index>.md' where <category> is
    valid and the path is at most 3 levels deep (variable-depth tree).
    """
    parts = Path(relative_path).parts
    if len(parts) == 1:
        if relative_path not in TOP_LEVEL_FILES:
            raise PathError(
                f"Top-level writes are only allowed to {sorted(TOP_LEVEL_FILES)}, "
                f"got {relative_path!r}"
            )
        return
    if parts[0] not in VALID_CATEGORY:
        raise PathError(
            f"{parts[0]!r} is not a valid category folder. "
            f"Must be one of {sorted(VALID_CATEGORY)}."
        )
    if len(parts) > 3:
        raise PathError(
            f"Path too deep — the variable-depth tree allows at most "
            f"category/topic/file.md, got {relative_path!r}"
        )


def write_file(relative_path: str, content: str) -> str:
    _validate_write_path(relative_path)
    path = _resolve(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {relative_path}"


def move_file(src: str, dst: str) -> str:
    """Move a page (and its paired raw source, if any) within the wiki
    tree. Used only by the split agent to reorganize a category into
    topics — never during normal ingestion."""
    _validate_write_path(dst)
    src_path = _resolve(src)
    if not src_path.exists():
        raise FileNotFoundError(f"No such file in wiki: {src}")
    dst_path = _resolve(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_path), str(dst_path))

    moved_sibling = None
    for sibling in src_path.parent.glob(f"{src_path.stem}.*"):
        if sibling.suffix == ".md":
            continue
        target = dst_path.parent / sibling.name
        shutil.move(str(sibling), str(target))
        moved_sibling = sibling.name

    msg = f"Moved {src} -> {dst}"
    if moved_sibling:
        msg += f" (and paired source file {moved_sibling})"
    return msg


def delete_file(relative_path: str, archive: bool = True) -> str:
    """
    Removes a page (and its paired raw source, if present) from the wiki.
    Archives to archive/{timestamp}/... by default rather than destroying
    data outright, and deterministically strips any now-dead reference to
    this path from every index file (see remove_index_references).
    """
    path = _resolve(relative_path)
    if not path.exists():
        raise FileNotFoundError(f"No such file in wiki: {relative_path}")

    siblings = [
        sib for sib in path.parent.glob(f"{path.stem}.*")
        if sib != path and sib.suffix != ".md"
    ]

    if archive:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        for target_file in [path] + siblings:
            rel = target_file.relative_to(WIKI_ROOT)
            archive_path = ARCHIVE_ROOT / stamp / rel
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target_file), str(archive_path))
    else:
        for target_file in [path] + siblings:
            target_file.unlink()

    remove_index_references(relative_path)
    return f"Deleted {relative_path}" + (" (archived)" if archive else "")


def _all_index_files() -> List[Path]:
    indexes = [WIKI_ROOT / "index.md"]
    indexes += list(WIKI_ROOT.glob("*/_index.md"))
    indexes += list(WIKI_ROOT.glob("*/*/_index.md"))
    return [p for p in indexes if p.exists()]


def remove_index_references(deleted_rel_path: str) -> List[str]:
    """
    Deterministic cleanup: strip any markdown list line linking to
    deleted_rel_path from every index file in the tree. No LLM involved —
    this is exactly the kind of mechanical maintenance the Design Notes
    call for on deletion.
    """
    touched = []
    for index_path in _all_index_files():
        text = index_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        kept = [ln for ln in lines if f"]({deleted_rel_path})" not in ln]
        if len(kept) != len(lines):
            index_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
            touched.append(str(index_path.relative_to(WIKI_ROOT)))
    return touched


def has_domain_index(category: str) -> bool:
    return (WIKI_ROOT / category / "_index.md").exists()


def has_topic_index(category: str, topic: str) -> bool:
    return (WIKI_ROOT / category / topic / "_index.md").exists()


def governing_index_path(category: str, topic: Optional[str] = None) -> str:
    """
    Which index file currently governs entries for this category/topic, per
    the variable-depth rule: use the most specific split that exists,
    otherwise fall back up to root index.md.
    """
    if topic and has_topic_index(category, topic):
        return f"{category}/{topic}/_index.md"
    if has_domain_index(category):
        return f"{category}/_index.md"
    return "index.md"


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
