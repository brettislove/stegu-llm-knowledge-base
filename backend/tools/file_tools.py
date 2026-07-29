"""
Low-level, sandboxed file operations against wiki/ — OneDrive-backed version.

All paths passed in by agents are relative to the wiki root *within the
configured OneDrive drive* and are validated to prevent escaping it. These
functions are what the tool-use loop actually calls when Claude invokes
read_file / write_file / list_files / list_dirs / grep / append_log /
move_file (see tool_defs.py for the schemas Claude sees). Deletion,
archiving, and index-reference cleanup are deliberately NOT exposed as
agent tools — they're deterministic operations triggered directly by
main.py, never by model judgment.

This is a drop-in replacement for the local-disk file_tools.py: every
public function keeps the same name, signature, and return semantics.
The difference is entirely internal — instead of pathlib.Path operations
against a local WIKI_ROOT directory, everything goes through a shared
GraphClient instance (backend.config.graph_client) against a
WIKI_ROOT-relative path prefix inside one OneDrive drive.
"""

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import List, Optional

from backend.config import (
    graph_client,
    WIKI_ROOT,
    VALID_CATEGORY,
    TOP_LEVEL_FILES,
    ARCHIVE_ROOT,
    PENDING_REVIEW_ROOT,
    INGEST_LOCK_PATH,
    INGEST_LOCK_STALE_SECONDS,
)
from backend.graph_client import (
    GraphNotFound,
    sanitize_filename,
)  # noqa: F401 (re-exported)


class PathError(ValueError):
    pass


class IngestLockedError(RuntimeError):
    """Raised when another ingestion run already holds ingest.lock."""

    pass


# ---------------------------------------------------------------------------
# Path handling
#
# There's no real filesystem here, so there's no Path.resolve() to lean on
# for escape-detection. Instead we do it purely lexically: reject absolute
# paths and any '..' segment, then join onto WIKI_ROOT as a OneDrive path
# string. This is equivalent in effect to the old _resolve() — both exist
# only to stop a path like "../../secrets.md" from being honored — but
# there's no symlink risk to worry about the way there can be on a real
# filesystem, since OneDrive item paths aren't symlink-traversable.
# ---------------------------------------------------------------------------


def _wiki_path(relative_path: str) -> str:
    """Validates relative_path and returns the full OneDrive-relative path
    (WIKI_ROOT joined with it), as a forward-slash string suitable for
    GraphClient calls.

    Every path segment is run through sanitize_filename() here — this is
    the one chokepoint every wiki read/write already funnels through
    (write_file, write_binary, store_raw_sibling, delete_file, move_file,
    append_log, every agent tool dispatch), so it's the natural single
    shared place to enforce OneDrive-safe names per the Design Notes,
    rather than sanitizing ad hoc at each call site. A no-op for the
    common case (slugify() already produces OneDrive-safe names); the real
    guard is for names that reach here without going through slugify first
    — e.g. an LLM-proposed topic folder name."""
    if not relative_path or relative_path.startswith("/"):
        raise PathError(f"Invalid or unsafe path: {relative_path!r}")
    parts = PurePosixPath(relative_path).parts
    if ".." in parts:
        raise PathError(f"Invalid or unsafe path: {relative_path!r}")
    sanitized = "/".join(sanitize_filename(part) for part in parts)
    return f"{WIKI_ROOT}/{sanitized}"


def slugify(text: str) -> str:
    """Lowercase, hyphenated, ASCII slug — strips Czech diacritics rather
    than failing on them (e.g. 'Žula' -> 'zula')."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "page"


def list_files(subdir: str = "") -> List[str]:
    """List all wiki pages, optionally scoped to one category/topic folder.
    Excludes manifest.json (not a page) but includes _index.md files."""
    base = _wiki_path(subdir) if subdir else WIKI_ROOT
    items = graph_client.list_all_files_recursive(base, name_filter=".md")
    # _path is WIKI_ROOT-relative already includes WIKI_ROOT prefix, since
    # list_all_files_recursive was called with `base` as the starting
    # point; strip WIKI_ROOT back off to match the old relative-to-root
    # return values.
    prefix = f"{WIKI_ROOT}/"
    return sorted(
        (
            item["_path"][len(prefix) :]
            if item["_path"].startswith(prefix)
            else item["_path"]
        )
        for item in items
    )


def list_dirs(subdir: str = "") -> List[str]:
    """List immediate subfolders — used to discover existing topic splits
    before proposing a new one."""
    base = _wiki_path(subdir) if subdir else WIKI_ROOT
    children = graph_client.list_children(base)
    return sorted(c["name"] for c in children if "folder" in c)


def read_file(relative_path: str) -> str:
    path = _wiki_path(relative_path)
    try:
        content = graph_client.read_file(path)
    except GraphNotFound:
        raise FileNotFoundError(f"No such file in wiki: {relative_path}")
    return content.decode("utf-8")


def read_project_file(absolute_onedrive_path: str) -> str:
    """Reads a file by its full OneDrive path (already relative to the
    drive root, NOT wiki-relative) — for files like SCHEMA_PATH and
    CLAUDE_MD_PATH that live at the project root (STEGU WIKI/...) rather
    than under WIKI_ROOT. Unlike read_file(), this does NOT join onto
    WIKI_ROOT or run _wiki_path's escape validation, since the caller is
    passing an already-fully-qualified config constant, not user/agent
    input.

    This replaces the old classify_agent.py pattern of
    SCHEMA_PATH.read_text(encoding="utf-8") — SCHEMA_PATH is now a Graph
    path string, not a local Path, so reading it means a real network
    call. Same reasoning applies to any other code reading CLAUDE_MD_PATH."""
    try:
        content = graph_client.read_file(absolute_onedrive_path)
    except GraphNotFound:
        raise FileNotFoundError(f"No such file in OneDrive: {absolute_onedrive_path}")
    return content.decode("utf-8")


def _validate_write_path(relative_path: str) -> None:
    """
    Enforces SCHEMA.md §1: a write must target either a known top-level
    file, or '<category>/[topic/]<slug-or-_index>.md' where <category> is
    valid and the path is at most 3 levels deep (variable-depth tree).
    """
    parts = PurePosixPath(relative_path).parts
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
    path = _wiki_path(relative_path)
    parent = str(PurePosixPath(path).parent)
    if parent and parent != ".":
        graph_client.ensure_folder(parent)
    graph_client.write_file(path, content.encode("utf-8"))
    return f"Wrote {len(content)} chars to {relative_path}"


def write_binary(relative_path: str, data: bytes) -> str:
    """Binary-content counterpart to write_file, used by _store_raw_sibling
    to persist non-markdown source files (PDFs, images, etc.) alongside a
    page. Not exposed as an agent tool, same as move_file/delete_file
    territory — only called directly by ingestion code in main.py."""
    path = _wiki_path(relative_path)
    parent = str(PurePosixPath(path).parent)
    if parent and parent != ".":
        graph_client.ensure_folder(parent)
    graph_client.write_file(path, data)
    return f"Wrote {len(data)} bytes to {relative_path}"


def store_raw_sibling(destination_path: str, filename: str, raw_bytes: bytes) -> dict:
    """Writes the original uploaded file next to its rendered .md page,
    same stem, using the upload's own extension (e.g. produkty/foo.md gets
    a paired produkty/foo.pdf). Replaces any stale sibling with a
    *different* extension first — this happens when a re-ingested update
    switches source format (e.g. .docx -> .pdf for the same page).

    Returns the driveItem metadata Graph gives back for the written
    sibling (includes file.hashes.sha256Hash when Graph populates it) —
    callers use this to source content_hash from Graph itself rather than
    a redundant local re-hash (see graph_client.extract_content_hash).

    This is the direct replacement for main.py's old _store_raw_sibling,
    which did the same thing with Path.glob()/.unlink()/.write_bytes()
    against local disk. Moved into file_tools.py so main.py has one call
    site per filesystem-shaped operation instead of its own graph_client
    calls living alongside file_tools.py's."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    dest_path = _wiki_path(destination_path)
    dest_parent = str(PurePosixPath(dest_path).parent)
    stem = PurePosixPath(dest_path).stem
    if dest_parent and dest_parent != ".":
        graph_client.ensure_folder(dest_parent)

    for child in graph_client.list_children(dest_parent):
        if "folder" in child:
            continue
        name = child["name"]
        if PurePosixPath(name).stem == stem and not name.endswith(".md"):
            item_path = f"{dest_parent}/{name}" if dest_parent else name
            graph_client.delete_item(item_path)

    sibling_path = f"{dest_parent}/{stem}.{ext}" if dest_parent else f"{stem}.{ext}"
    return graph_client.write_file(sibling_path, raw_bytes)


def move_file(src: str, dst: str) -> str:
    """Move a page (and its paired raw source, if any) within the wiki
    tree. Used only by the split agent to reorganize a category into
    topics — never during normal ingestion."""
    _validate_write_path(dst)
    src_path = _wiki_path(src)
    if not graph_client.exists(src_path):
        raise FileNotFoundError(f"No such file in wiki: {src}")
    dst_path = _wiki_path(dst)
    dst_parent = str(PurePosixPath(dst_path).parent)
    dst_name = PurePosixPath(dst_path).name
    if dst_parent and dst_parent != ".":
        graph_client.ensure_folder(dst_parent)
    graph_client.move_item(
        src_path, dst_parent if dst_parent != "." else "", new_name=dst_name
    )

    # Paired-sibling move: same stem, any non-.md extension, same source
    # folder — mirrors the old Path.glob(f"{stem}.*") filtered to non-.md.
    src_parent = str(PurePosixPath(src_path).parent)
    src_stem = PurePosixPath(src_path).stem
    moved_sibling = None
    for child in graph_client.list_children(src_parent):
        if "folder" in child:
            continue
        name = child["name"]
        if (
            PurePosixPath(name).stem == src_stem
            and not name.endswith(".md")
            and name != PurePosixPath(src_path).name
        ):
            sibling_path = f"{src_parent}/{name}" if src_parent else name
            graph_client.move_item(
                sibling_path, dst_parent if dst_parent != "." else "", new_name=name
            )
            moved_sibling = name

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
    path = _wiki_path(relative_path)
    if not graph_client.exists(path):
        raise FileNotFoundError(f"No such file in wiki: {relative_path}")

    parent = str(PurePosixPath(path).parent)
    stem = PurePosixPath(path).stem
    name = PurePosixPath(path).name
    siblings = [
        child["name"]
        for child in graph_client.list_children(parent)
        if "folder" not in child
        and PurePosixPath(child["name"]).stem == stem
        and not child["name"].endswith(".md")
        and child["name"] != name
    ]

    if archive:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        # Preserve the item's position relative to WIKI_ROOT under
        # archive/{stamp}/..., matching the old rel = path.relative_to(WIKI_ROOT).
        rel_parent = (
            parent[len(WIKI_ROOT) :].strip("/")
            if parent.startswith(WIKI_ROOT)
            else parent
        )
        archive_parent = f"{ARCHIVE_ROOT}/{stamp}/{rel_parent}".rstrip("/")
        graph_client.ensure_folder(archive_parent)
        for fname in [name] + siblings:
            src_item = f"{parent}/{fname}" if parent else fname
            graph_client.move_item(src_item, archive_parent, new_name=fname)
    else:
        for fname in [name] + siblings:
            item_path = f"{parent}/{fname}" if parent else fname
            graph_client.delete_item(item_path)

    remove_index_references(relative_path)
    return f"Deleted {relative_path}" + (" (archived)" if archive else "")


def _all_index_files() -> List[str]:
    """Returns WIKI_ROOT-relative paths (not full OneDrive paths) for
    index.md and every */_index.md and */*/_index.md, matching the old
    function's use of WIKI_ROOT-relative Path objects."""
    candidates = ["index.md"]
    for topic in list_dirs(""):
        candidates.append(f"{topic}/_index.md")
        for subtopic in list_dirs(topic):
            candidates.append(f"{topic}/{subtopic}/_index.md")
    return [c for c in candidates if graph_client.exists(_wiki_path(c))]


def remove_index_references(deleted_rel_path: str) -> List[str]:
    """
    Deterministic cleanup: strip any markdown list line linking to
    deleted_rel_path from every index file in the tree. No LLM involved —
    this is exactly the kind of mechanical maintenance the Design Notes
    call for on deletion.

    Writes directly via graph_client rather than write_file(), because
    write_file() enforces _validate_write_path's agent-facing rules
    (top-level allowlist, category allowlist). This is deterministic,
    system-triggered maintenance on files that were already validated
    when originally created — same as the original local-disk version,
    which wrote straight to the resolved Path without re-running
    _validate_write_path.
    """
    touched = []
    for index_rel_path in _all_index_files():
        text = read_file(index_rel_path)
        lines = text.splitlines()
        kept = [ln for ln in lines if f"]({deleted_rel_path})" not in ln]
        if len(kept) != len(lines):
            path = _wiki_path(index_rel_path)
            graph_client.write_file(path, ("\n".join(kept) + "\n").encode("utf-8"))
            touched.append(index_rel_path)
    return touched


def has_domain_index(category: str) -> bool:
    return graph_client.exists(_wiki_path(f"{category}/_index.md"))


def has_topic_index(category: str, topic: str) -> bool:
    return graph_client.exists(_wiki_path(f"{category}/{topic}/_index.md"))


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
    """Append-only write. Only valid for log.md and feedback_log.md.

    Graph has no native append-mode PUT (unlike a local file opened with
    "a"), so this is necessarily read-modify-write: fetch current content
    (if any), decide on a separator exactly as the original did, and PUT
    the whole new content back. This costs an extra round-trip per call
    versus the old open(...,"a") but preserves identical output.
    """
    if relative_path not in {"log.md", "feedback_log.md"}:
        raise PathError("append_log may only target log.md or feedback_log.md")
    path = _wiki_path(relative_path)
    existing = graph_client.item_metadata(path)
    needs_separator = existing is not None and existing.get("size", 0) > 0
    current = graph_client.read_file(path).decode("utf-8") if needs_separator else ""
    separator = "\n\n" if needs_separator else ""
    new_content = current + separator + entry.strip() + "\n"
    graph_client.write_file(path, new_content.encode("utf-8"))
    return f"Appended entry to {relative_path}"


def grep(pattern: str, subdir: str = "") -> List[str]:
    """Case-insensitive regex search across wiki markdown files."""
    base = _wiki_path(subdir) if subdir else WIKI_ROOT
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")
    matches = []
    prefix = f"{WIKI_ROOT}/"
    for item in graph_client.list_all_files_recursive(base, name_filter=".md"):
        full_path = item["_path"]
        rel = full_path[len(prefix) :] if full_path.startswith(prefix) else full_path
        content = graph_client.read_file(full_path).decode("utf-8")
        for i, line in enumerate(content.splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{rel}:{i}: {line.strip()}")
    return matches


# ---------------------------------------------------------------------------
# Ingest lock
#
# Cross-process guard on top of main.py's in-process asyncio.Lock — see
# Design Notes "Ingestion-level Locking". Not perfectly atomic (there's a
# small check-then-write race between item_metadata() and write_file()
# below), but Graph's simple content PUT has no confirmed fail-on-conflict
# primitive to close that gap; this is the same honest tradeoff as the
# asyncio.Lock it complements, just extended to cover multiple processes.
# ---------------------------------------------------------------------------


def acquire_ingest_lock() -> None:
    existing = graph_client.item_metadata(INGEST_LOCK_PATH)
    if existing is not None:
        held_since = None
        try:
            held_since = datetime.fromisoformat(
                graph_client.read_file(INGEST_LOCK_PATH).decode("utf-8").strip()
            )
        except (GraphNotFound, ValueError):
            pass
        age = (
            (datetime.now(timezone.utc) - held_since).total_seconds()
            if held_since is not None
            else None
        )
        if age is None or age < INGEST_LOCK_STALE_SECONDS:
            raise IngestLockedError(
                "Ingestion is already in progress (ingest.lock present)."
            )
        # Lock is older than the staleness window — assume it belongs to a
        # crashed/killed process and reclaim it rather than wedging the
        # pipeline forever.
    lock_parent = INGEST_LOCK_PATH.rsplit("/", 1)[0]
    graph_client.ensure_folder(lock_parent)
    graph_client.write_file(
        INGEST_LOCK_PATH, datetime.now(timezone.utc).isoformat().encode("utf-8")
    )


def release_ingest_lock() -> None:
    try:
        graph_client.delete_item(INGEST_LOCK_PATH)
    except GraphNotFound:
        pass


# ---------------------------------------------------------------------------
# Pending-review helpers
#
# These operate against PENDING_REVIEW_ROOT, not WIKI_ROOT, and hold a mix
# of raw uploaded bytes (any extension) plus JSON metadata sidecars — not
# wiki pages, so they deliberately don't go through _wiki_path/_validate_
# write_path. main.py's /pending-review routes used to do this with plain
# Path.mkdir()/.glob()/.read_text()/.write_bytes()/.unlink(); these give it
# the same operations against Graph instead, so main.py has one call site
# per operation rather than duplicating graph_client calls inline.
# ---------------------------------------------------------------------------


def _pending_path(name: str) -> str:
    return f"{PENDING_REVIEW_ROOT}/{name}"


def pending_review_write(name: str, data: bytes) -> None:
    """Writes one file (raw upload or .json metadata sidecar) into
    pending_review/. Creates the folder on first use."""
    graph_client.ensure_folder(PENDING_REVIEW_ROOT)
    graph_client.write_file(_pending_path(name), data)


def pending_review_read_text(name: str) -> str:
    return graph_client.read_file(_pending_path(name)).decode("utf-8")


def pending_review_read_bytes(name: str) -> bytes:
    return graph_client.read_file(_pending_path(name))


def pending_review_exists(name: str) -> bool:
    return graph_client.exists(_pending_path(name))


def pending_review_delete(name: str, missing_ok: bool = False) -> None:
    """Mirrors Path.unlink(missing_ok=...): by default raises if the item
    isn't there, but callers doing best-effort cleanup can pass
    missing_ok=True to silently no-op instead."""
    try:
        graph_client.delete_item(_pending_path(name))
    except GraphNotFound:
        if not missing_ok:
            raise FileNotFoundError(f"No such pending-review item: {name}")


def pending_review_list_json() -> List[str]:
    """Returns filenames (not full paths) of every *.json metadata sidecar
    in pending_review/, sorted — mirrors sorted(PENDING_REVIEW_ROOT.glob('*.json'))."""
    children = graph_client.list_children(PENDING_REVIEW_ROOT)
    return sorted(
        c["name"] for c in children if "folder" not in c and c["name"].endswith(".json")
    )
