"""
Deterministic, non-LLM bookkeeping: content hashing, token estimation, and
the manifest.json that tracks per-page system metadata (id, layer, parent,
token_count, content_hash). Nothing in this module ever calls the model —
per the Design Notes, size/hash/split-trigger decisions must be mechanical,
not an LLM judgment call.

OneDrive-backed version: manifest.json is still read-whole / write-whole
(no structural change from the original — it was always "load the whole
JSON blob, mutate in memory, save the whole blob back"), just via
graph_client instead of Path.read_text()/write_text(). Every public
function keeps its original name and signature.
"""

import hashlib
import json
from typing import Optional

from backend.config import (
    graph_client,
    MANIFEST_PATH,
    TOKEN_BUDGET,
    FILE_COUNT_THRESHOLD,
)
from backend.graph_client import GraphNotFound


def compute_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def estimate_tokens(content: str) -> int:
    """
    Rough approximation (~4 chars/token). Good enough for split-trigger
    decisions — this is a budget check, not a billing calculation, so it
    doesn't need to match a real tokenizer exactly.
    """
    return max(1, len(content) // 4)


def load_manifest() -> dict:
    try:
        content = graph_client.read_file(MANIFEST_PATH)
    except GraphNotFound:
        return {}
    return json.loads(content.decode("utf-8"))


def save_manifest(manifest: dict) -> None:
    # Old version did MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    # before writing — the Graph equivalent is ensure_folder on wiki/, in
    # case this is the very first write before the folder structure setup
    # step has run. Cheap no-op (one metadata check) once it already exists.
    parent = MANIFEST_PATH.rsplit("/", 1)[0] if "/" in MANIFEST_PATH else ""
    if parent:
        graph_client.ensure_folder(parent)
    body = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
    graph_client.write_file(MANIFEST_PATH, body.encode("utf-8"))


def get_entry(rel_path: str) -> Optional[dict]:
    return load_manifest().get(rel_path)


def upsert_entry(rel_path: str, **fields) -> dict:
    manifest = load_manifest()
    entry = manifest.get(rel_path, {})
    entry.update(fields)
    manifest[rel_path] = entry
    save_manifest(manifest)
    return entry


def remove_entry(rel_path: str) -> None:
    manifest = load_manifest()
    if rel_path in manifest:
        del manifest[rel_path]
        save_manifest(manifest)


def rename_entry(old_path: str, new_path: str) -> None:
    manifest = load_manifest()
    if old_path in manifest:
        manifest[new_path] = manifest.pop(old_path)
        save_manifest(manifest)


def find_by_hash(content_hash: str) -> Optional[str]:
    """Cheap dedup check: is a file with this exact content already in the
    wiki? Used to short-circuit re-ingestion of an unchanged upload before
    calling the model at all."""
    for path, entry in load_manifest().items():
        if entry.get("content_hash") == content_hash:
            return path
    return None


def folder_totals(prefix: str) -> dict:
    """
    Sum token_count and count source pages for every manifest entry whose
    path is under `prefix` (a category, or a category/topic). Used by the
    lint agent and the ingest flow's split-trigger check.
    """
    manifest = load_manifest()
    matching = [
        e
        for path, e in manifest.items()
        if path.startswith(prefix + "/") and e.get("layer") == "source"
    ]
    return {
        "file_count": len(matching),
        "total_tokens": sum(e.get("token_count", 0) for e in matching),
    }


def needs_split(prefix: str) -> bool:
    totals = folder_totals(prefix)
    return (
        totals["file_count"] > FILE_COUNT_THRESHOLD
        and totals["total_tokens"] > TOKEN_BUDGET
    )
