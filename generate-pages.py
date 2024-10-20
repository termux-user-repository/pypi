#!/usr/bin/env python3
# generate-pages.py - Generate pages for pypi
#
# This file is based on https://github.com/bartbroere/pypi.bartbroe.re/blob/main/scrape.py.
#

import json
import os
from collections import defaultdict
import requests

WHEELS_RELEASE_URL = "https://api.github.com/repos/termux-user-repository/pypi-wheel-builder/releases/latest"

def get_wheel_infos():
  res = []
  resp = requests.get(WHEELS_RELEASE_URL)
  release_info = json.loads(resp.text)
  for assert_into in release_info["assets"]:
    assert_name = assert_into["name"]
    assert_url = assert_into["browser_download_url"]
    if assert_name.endswith(".whl"):
      res.append((assert_name, assert_url))
  return res

def get_packages_dict(wheel_infos):
  res = defaultdict(list)
  for wheel_info in wheel_infos:
    package_name = wheel_info[0].split("-")[0]
    package_name = package_name.replace("_", "-")
    res[package_name].append(wheel_info)
  return res

def generate_packages_index(packages_dict):
  for package_name, wheels_info in packages_dict.items():
    try:
      os.mkdir('docs')
    except FileExistsError:
      pass
    try:
      os.mkdir(os.path.join('docs', package_name.lower()))
    except FileExistsError:
      pass
    with open(os.path.join('docs', package_name.lower(), 'index.html'), 'w') as package_index:
      package_index.write(f"""
          <html>
          <head>
              <style>
              body{{margin:40px auto;max-width:650px;line-height:1.6;font-size:18px;color:#444;padding:0 10px}}
              h1,h2,h3{{line-height:1.2}}
              </style>
              <title>{package_name.lower()}</title>
          </head>
          <body>
          """)
      for wheel_name, wheel_url in wheels_info:
        package_index.write(f"""
                <a href="{wheel_url}">{wheel_name}</a>
            """)
      package_index.write(f"""
                </body>
                </html>
            """)

def generate_main_pages(packages):
  try:
    os.mkdir('docs')
  except FileExistsError:
    pass
  with open('docs/index.html', 'w') as main_package_index:
    main_package_index.write(f"""
    <html>
    <head>
    <style>
    body{{margin:40px auto;max-width:650px;line-height:1.6;font-size:18px;color:#444;padding:0 10px}}
    h1,h2,h3{{line-height:1.2}}
    </style>
    <title>Termux User Repository PyPI</title>
    </head>
    <body>
    <header>Termux User Repository PyPI, use it with:</header>
    <pre>pip install --extra-index-url https://termux-user-repository.github.io/pypi/</pre>
    """)
    for package_name in sorted(packages):
        main_package_index.write(f'<a href="{package_name.lower()}">{package_name.lower()}</a>\n\n')
    main_package_index.write("""
    </body>
    </html>
    """)

def main():
  wheel_infos = get_wheel_infos()
  packages_dict = get_packages_dict(wheel_infos)
  generate_packages_index(packages_dict)
  generate_main_pages(packages_dict.keys())

if __name__ == "__main__":
  main()
