#!/usr/bin/env python3
import json
import os
from pathlib import Path


MANIFEST_PATH = Path("data/manifest.jsonl")
REQUIRED_FIELDS = {
    "package_name",
    "normalized_name",
    "version",
    "pyversion",
    "python_version",
    "repo",
    "tag",
    "filename",
    "url",
    "sha256",
    "uploaded_at",
}


def row_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["repo"], row["tag"], row["filename"]


def load_manifest() -> dict[tuple[str, str, str], dict[str, str]]:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MANIFEST_PATH.exists():
        return {}

    rows: dict[tuple[str, str, str], dict[str, str]] = {}
    with MANIFEST_PATH.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            key = row_key(row)
            rows[key] = row
    return rows


def read_dispatch_records() -> list[dict[str, str]]:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return []

    event_data = json.loads(Path(event_path).read_text(encoding="utf-8"))
    payload = event_data.get("client_payload") or {}
    wheels = payload.get("wheels") or []
    if not isinstance(wheels, list):
        return []

    cleaned: list[dict[str, str]] = []
    for row in wheels:
        if not isinstance(row, dict):
            continue
        if not REQUIRED_FIELDS.issubset(row.keys()):
            continue
        cleaned.append({k: str(row[k]) for k in REQUIRED_FIELDS})
    return cleaned


def write_manifest(rows: dict[tuple[str, str, str], dict[str, str]]) -> None:
    sorted_rows = sorted(
        rows.values(),
        key=lambda x: (x["normalized_name"], x["version"], x["filename"]),
    )
    with MANIFEST_PATH.open("w", encoding="utf-8") as fp:
        for row in sorted_rows:
            fp.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def main() -> int:
    existing = load_manifest()
    incoming = read_dispatch_records()
    if not incoming:
        print("No wheel records in dispatch payload, manifest unchanged")
        return 0

    changed = 0
    for row in incoming:
        key = row_key(row)
        if existing.get(key) != row:
            existing[key] = row
            changed += 1

    write_manifest(existing)
    print(f"Manifest upsert complete: received={len(incoming)} changed={changed} total={len(existing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
