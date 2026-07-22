"""
Minimal YAML-frontmatter parse/serialize for wiki pages. Deliberately not a
general-purpose YAML parser — SCHEMA.md fixes the field set (§2), so this
only needs to handle strings, dates, and simple lists (source_docs, tags)
in a stable, round-trippable order. Used by postprocess.py to inject system
fields (id/layer/parent/token_count/content_hash) without asking the LLM to
manage them.
"""
import re
from typing import Any, Dict, Tuple

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

# Preferred key order when serializing — system fields grouped first, then
# content fields, matching the example in SCHEMA.md §2.
FIELD_ORDER = [
    "id", "title", "layer", "category", "doc_type", "parent", "access",
    "version", "valid_from", "valid_until", "last_updated", "token_count",
    "content_hash", "status", "tags", "source_docs",
]


def parse(content: str) -> Tuple[Dict[str, Any], str]:
    match = FRONTMATTER_RE.match(content)
    if not match:
        return {}, content
    raw_yaml, body = match.group(1), match.group(2)
    fields: Dict[str, Any] = {}
    current_list_key = None
    for line in raw_yaml.splitlines():
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            if current_list_key:
                fields.setdefault(current_list_key, [])
                fields[current_list_key].append(stripped[2:].strip().strip('"'))
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            current_list_key = key
            fields[key] = []
            continue
        current_list_key = None
        fields[key] = _coerce(value)
    return fields, body


def _coerce(value: str) -> Any:
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value  # dates/numbers/bare strings kept as-is — good enough here


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if ":" in s:
        return f'"{s}"'
    return s


def serialize(fields: Dict[str, Any], body: str) -> str:
    lines = ["---"]
    seen = set()
    for key in FIELD_ORDER:
        value = fields.get(key)
        if value in (None, "", []):
            continue
        seen.add(key)
        _append_field(lines, key, value)
    for key, value in fields.items():
        if key in seen or value in (None, "", []):
            continue
        _append_field(lines, key, value)
    lines.append("---")
    if not body.startswith("\n"):
        body = "\n" + body
    return "\n".join(lines) + body


def _append_field(lines: list, key: str, value: Any) -> None:
    if isinstance(value, list):
        lines.append(f"{key}:")
        for item in value:
            lines.append(f"  - {item}")
    else:
        lines.append(f"{key}: {_format_value(value)}")
