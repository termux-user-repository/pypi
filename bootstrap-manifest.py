#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_SOURCE_REPO = "termux-user-repository/pypi-wheel-builder"
DEFAULT_SOURCE_TAG = "wheels"
DEFAULT_TARGET_ORG = "tur-pypi-dists"


def run_cmd(args: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, text=True, capture_output=capture_output)


def gh_api_json(path: str) -> list | dict:
    out = run_cmd(["gh", "api", path], capture_output=True).stdout
    return json.loads(out)


def iter_paginated(path_prefix: str) -> list[dict]:
    page = 1
    all_items: list[dict] = []
    while True:
        path = f"{path_prefix}?per_page=100&page={page}"
        items = gh_api_json(path)
        if not items:
            break
        if not isinstance(items, list):
            raise RuntimeError(f"Unexpected API response for {path}")
        all_items.extend(items)
        if len(items) < 100:
            break
        page += 1
    return all_items


def canonicalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_wheel_fields(filename: str) -> tuple[str, str, str]:
    if not filename.endswith(".whl"):
        raise ValueError("Not a wheel file")

    wheel_base = filename[:-4]
    parts = wheel_base.split("-")
    if len(parts) < 5:
        raise ValueError(f"Unsupported wheel naming format: {filename}")

    py_tag = parts[-3]
    head = parts[:-3]
    if len(head) < 2:
        raise ValueError(f"Unsupported wheel naming format: {filename}")

    if len(head) >= 3 and re.match(r"^[0-9][0-9A-Za-z_.]*$", head[-1]):
        name = "-".join(head[:-2])
        version = head[-2]
    else:
        name = "-".join(head[:-1])
        version = head[-1]

    if not name or not version:
        raise ValueError(f"Unsupported wheel naming format: {filename}")

    pyversion = extract_pyversion_from_tag(py_tag)
    if not pyversion:
        raise ValueError(f"Unsupported python tag in wheel: {filename}")

    return name, version, pyversion


def extract_pyversion_from_tag(py_tag: str) -> str:
    cp_versions: list[int] = []
    py_versions: list[int] = []

    for token in py_tag.split("."):
        cp_match = re.match(r"^cp([0-9]+)$", token)
        if cp_match:
            cp_versions.append(int(cp_match.group(1)))
            continue

        py_match = re.match(r"^py([0-9]+)$", token)
        if py_match:
            py_versions.append(int(py_match.group(1)))

    if cp_versions:
        return str(max(cp_versions))
    if py_versions:
        return str(max(py_versions))
    return ""


def py_digits_to_version(py_digits: str) -> str:
    if not re.match(r"^[0-9]+$", py_digits):
        raise ValueError(f"Invalid pyversion: {py_digits}")
    if len(py_digits) == 1:
        return py_digits
    major = py_digits[0]
    minor = int(py_digits[1:])
    return f"{major}.{minor}"


def build_row(target_org: str, asset: dict) -> dict[str, str] | None:
    filename = asset.get("name", "")
    if not filename.endswith(".whl"):
        return None

    name, version, pyversion = parse_wheel_fields(filename)
    python_version = py_digits_to_version(pyversion)
    target_repo_name = f"python{python_version}-{name}"
    target_repo_full_name = f"{target_org}/{target_repo_name}"
    target_tag = f"v{version}"
    digest = asset.get("digest", "")
    sha256 = ""
    if isinstance(digest, str) and digest.startswith("sha256:"):
        sha256 = digest.split(":", 1)[1]

    uploaded_at = asset.get("updated_at") or asset.get("created_at") or ""
    url = f"https://github.com/{target_repo_full_name}/releases/download/{target_tag}/{filename}"

    return {
        "package_name": name,
        "normalized_name": canonicalize_package_name(name),
        "version": version,
        "pyversion": pyversion,
        "python_version": python_version,
        "repo": target_repo_full_name,
        "tag": target_tag,
        "filename": filename,
        "url": url,
        "sha256": sha256,
        "uploaded_at": str(uploaded_at),
    }


def row_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["repo"], row["tag"], row["filename"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap data/manifest.jsonl from pypi-wheel-builder release assets")
    parser.add_argument("--source-repo", default=DEFAULT_SOURCE_REPO, help="Source repo in owner/name format")
    parser.add_argument("--source-tag", default=DEFAULT_SOURCE_TAG, help="Release tag to read assets from")
    parser.add_argument("--target-org", default=DEFAULT_TARGET_ORG, help="Target org/user for wheel repositories")
    parser.add_argument("--output", default="data/manifest.jsonl", help="Output JSONL file path")
    parser.add_argument(
        "--check-url-get",
        dest="check_url_get",
        action="store_true",
        help="Check generated wheel URLs with minimal HTTP GET (Range: bytes=0-0) and report 404 errors",
    )
    return parser.parse_args()


def check_url_with_get(url: str) -> int:
    # Use a ranged GET so availability is checked without downloading the full wheel.
    req = Request(url, method="GET", headers={"Range": "bytes=0-0"})
    with urlopen(req, timeout=15) as resp:
        return getattr(resp, "status", 200)


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: dict[tuple[str, str, str], dict[str, str]] = {}
    release = gh_api_json(f"/repos/{args.source_repo}/releases/tags/{args.source_tag}")
    if not isinstance(release, dict):
        raise RuntimeError("Unexpected release response format")

    tag = release.get("tag_name")
    assets = release.get("assets") or []
    if not tag or not isinstance(assets, list):
        raise RuntimeError("No assets found in source release")

    for asset in assets:
        if not isinstance(asset, dict):
            continue
        wheel_name = str(asset.get("name", "<unknown>"))
        py_tag_hint = ""
        if wheel_name.endswith(".whl"):
            parts = wheel_name[:-4].split("-")
            if len(parts) >= 3:
                py_tag_hint = parts[-3]
        try:
            row = build_row(str(args.target_org), asset)
        except ValueError as exc:
            if py_tag_hint:
                print(
                    f"Skip invalid wheel in {args.source_repo}:{tag}: {wheel_name} (py_tag={py_tag_hint}) -> {exc}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Skip invalid wheel in {args.source_repo}:{tag}: {wheel_name} -> {exc}",
                    file=sys.stderr,
                )
            continue
        if not row:
            continue
        rows[row_key(row)] = row

    sorted_rows = sorted(
        rows.values(),
        key=lambda x: (x["normalized_name"], x["version"], x["filename"]),
    )

    if args.check_url_get:
        not_found_count = 0
        for row in sorted_rows:
            url = row["url"]
            try:
                status = check_url_with_get(url)
            except HTTPError as exc:
                if exc.code == 404:
                    not_found_count += 1
                    print(f"URL 404: {url}", file=sys.stderr)
                else:
                    print(f"URL check failed [{exc.code}]: {url}", file=sys.stderr)
                continue
            except URLError as exc:
                print(f"URL check failed [network]: {url} ({exc.reason})", file=sys.stderr)
                continue

            if status == 404:
                not_found_count += 1
                print(f"URL 404: {url}", file=sys.stderr)

        if not_found_count > 0:
            print(f"Detected {not_found_count} generated URL(s) returning 404", file=sys.stderr)

    with output_path.open("w", encoding="utf-8") as fp:
        for row in sorted_rows:
            fp.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")

    print(f"Wrote {len(sorted_rows)} records to {output_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
