"""
Deterministic post-processing, applied AFTER an agent writes or moves a
page. Injects/refreshes system frontmatter fields (id, layer, parent,
token_count, content_hash) and the matching manifest.json entry. Nothing
here ever calls the model — this is exactly the "deterministic script, not
LLM judgment" maintenance the Design Notes call for.
"""
from datetime import date
from typing import Optional

from backend.tools import file_tools, frontmatter, hashing


def _parent_id_for(governing_index_path: str) -> str:
    if governing_index_path == "index.md":
        return "root"
    prefix = governing_index_path[: -len("/_index.md")]
    return prefix.replace("/", "-") + "-index"


def _split_path(rel_path: str):
    parts = rel_path.split("/")
    category = parts[0]
    topic = parts[1] if len(parts) == 3 else None
    slug = parts[-1]
    if slug.endswith(".md"):
        slug = slug[:-3]
    return category, topic, slug


def finalize_page(destination_path: str, category: str, topic: Optional[str], content_hash: str) -> dict:
    """
    Call right after the writer agent has written destination_path. Reads
    it back, computes id/layer/parent/token_count, patches the frontmatter
    with the system fields (content_hash is passed in — it's the RAW
    SOURCE's hash, computed by main.py, not the page body's), and records
    the manifest entry.
    """
    content = file_tools.read_file(destination_path)
    fields, body = frontmatter.parse(content)

    _, _, slug = _split_path(destination_path)
    entry_id = f"{category}-{(topic + '-') if topic else ''}{slug}"
    governing_index = file_tools.governing_index_path(category, topic)
    parent = _parent_id_for(governing_index)
    token_count = hashing.estimate_tokens(body)

    fields.update({
        "id": entry_id,
        "layer": "source",
        "parent": parent,
        "token_count": token_count,
        "content_hash": content_hash,
        "last_updated": date.today().isoformat(),
    })

    file_tools.write_file(destination_path, frontmatter.serialize(fields, body))

    hashing.upsert_entry(
        destination_path,
        id=entry_id,
        layer="source",
        category=category,
        topic=topic or "",
        parent=parent,
        token_count=token_count,
        content_hash=content_hash,
        title=fields.get("title", ""),
    )
    return fields


def refresh_token_counts() -> int:
    """
    Recompute token_count for every page — cheap and idempotent. Run after
    distillation, since a factual correction edits a page's body directly
    (outside the normal ingest -> finalize_page path) and its token_count
    would otherwise go stale. Returns how many pages were updated.
    """
    updated = 0
    for rel_path in file_tools.list_files():
        if rel_path == "index.md" or rel_path.endswith("_index.md"):
            continue
        content = file_tools.read_file(rel_path)
        fields, body = frontmatter.parse(content)
        if "id" not in fields:
            continue
        new_count = hashing.estimate_tokens(body)
        if fields.get("token_count") != new_count:
            fields["token_count"] = new_count
            file_tools.write_file(rel_path, frontmatter.serialize(fields, body))
            hashing.upsert_entry(rel_path, token_count=new_count)
            updated += 1
    return updated
