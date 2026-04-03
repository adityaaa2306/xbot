"""JSONL and JSON persistence helpers for the signal engine."""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def ensure_parent(path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    target = ensure_parent(path)
    if not target.exists():
        return []

    rows: List[Dict[str, Any]] = []
    with open(target, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: str, records: Iterable[Dict[str, Any]]) -> int:
    target = ensure_parent(path)
    count = 0
    with open(target, "a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def upsert_jsonl_by_key(path: str, records: Iterable[Dict[str, Any]], key: str) -> int:
    existing = load_jsonl(path)
    existing_map = {
        row[key]: row
        for row in existing
        if isinstance(row, dict) and row.get(key) is not None
    }

    updated = 0
    for record in records:
        record_key = record.get(key)
        if record_key is None:
            continue
        existing_map[record_key] = record
        updated += 1

    target = ensure_parent(path)
    with open(target, "w", encoding="utf-8") as handle:
        for row in existing_map.values():
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return updated


def load_latest_jsonl(path: str) -> Optional[Dict[str, Any]]:
    rows = load_jsonl(path)
    return rows[-1] if rows else None


def write_json(path: str, payload: Dict[str, Any]) -> None:
    target = ensure_parent(path)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def load_json(path: str) -> Optional[Dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return None
    with open(target, "r", encoding="utf-8") as handle:
        return json.load(handle)

