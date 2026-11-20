#!/usr/bin/env bash
# Prepare the host's CPython 3.11 / aarch64 wheels with resumable downloads.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
wheel_dir="${WHEEL_DIR:-${root}/wheels}"
mkdir -p "${wheel_dir}"
cd "${wheel_dir}"

urls="$(python3 - "${root}/packages/ascend-op-eval/pyproject.toml" <<'PY'
import json
import sys
import tomllib
import urllib.request

with open(sys.argv[1], "rb") as package:
    requirements = tomllib.load(package)["project"]["optional-dependencies"]["npu"]

for requirement in requirements:
    name, _, version = requirement.partition("==")
    release = f"{name}/{version}" if version else name
    with urllib.request.urlopen(f"https://pypi.org/pypi/{release}/json") as response:
        files = json.load(response)["urls"]
    for file in files:
        filename = file["filename"]
        if filename.endswith("-py3-none-any.whl") or (
            "-cp311-" in filename and filename.endswith("aarch64.whl")
            and "musllinux" not in filename
        ):
            print(file["url"])
            break
    else:
        sys.exit(f"No CPython 3.11/aarch64 wheel on PyPI for {requirement}")
PY
)"
while IFS= read -r url; do
  filename="${url##*/}"
  for ((attempt=1; attempt<=200; attempt++)); do
    if curl -fsSL -C - --retry 10 --retry-delay 2 -m 600 -o "${filename}" "${url}"; then
      break
    fi
    if ((attempt == 200)); then
      echo "Download failed: ${filename}" >&2
      exit 1
    fi
    sleep 1
  done
done <<< "${urls}"
