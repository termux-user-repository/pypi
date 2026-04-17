#!/usr/bin/env python3
import json
import os
from collections import defaultdict
from pathlib import Path


MANIFEST_PATH = Path("data/manifest.jsonl")
DOCS_DIR = Path("docs")


def get_wheel_infos() -> list[tuple[str, str, str]]:
    if not MANIFEST_PATH.exists():
        return []

    items: list[tuple[str, str, str]] = []
    with MANIFEST_PATH.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            filename = row.get("filename")
            url = row.get("url")
            package_name = row.get("normalized_name") or row.get("package_name")
            if not filename or not url or not package_name:
                continue
            items.append((package_name, filename, url))
    return items


def get_packages_dict(wheel_infos: list[tuple[str, str, str]]) -> dict[str, list[tuple[str, str]]]:
    packages = defaultdict(list)
    for package_name, wheel_name, wheel_url in wheel_infos:
        packages[package_name].append((wheel_name, wheel_url))

    for package_name in packages:
        packages[package_name].sort(key=lambda x: x[0])
    return packages


def _page_header(title: str) -> str:
    return f"""
<html>
<head>
  <style>
  body{{margin:40px auto;max-width:760px;line-height:1.6;font-size:16px;color:#222;padding:0 14px}}
  h1,h2,h3{{line-height:1.2}}
  a{{display:block;margin:6px 0}}
  </style>
  <title>{title}</title>
</head>
<body>
"""


def generate_packages_index(packages_dict: dict[str, list[tuple[str, str]]]) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for package_name, wheels_info in packages_dict.items():
        pkg_dir = DOCS_DIR / package_name.lower()
        pkg_dir.mkdir(parents=True, exist_ok=True)
        with (pkg_dir / "index.html").open("w", encoding="utf-8") as package_index:
            package_index.write(_page_header(package_name.lower()))
            for wheel_name, wheel_url in wheels_info:
                package_index.write(f'<a href="{wheel_url}">{wheel_name}</a>\n')
            package_index.write("</body>\n</html>\n")


def generate_main_pages(packages: list[str]) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    with (DOCS_DIR / "index.html").open("w", encoding="utf-8") as main_package_index:
        main_package_index.write(_page_header("Termux User Repository PyPI"))
        main_package_index.write(
            "<header>Termux User Repository PyPI, use it with:</header>"
            "<pre>pip install --extra-index-url https://termux-user-repository.github.io/pypi/</pre>\n"
        )
        for package_name in sorted(packages):
            main_package_index.write(f'<a href="{package_name.lower()}">{package_name.lower()}</a>\n')
        main_package_index.write("</body>\n</html>\n")


def main() -> None:
    wheel_infos = get_wheel_infos()
    packages_dict = get_packages_dict(wheel_infos)
    generate_packages_index(packages_dict)
    generate_main_pages(list(packages_dict.keys()))

if __name__ == "__main__":
  main()
