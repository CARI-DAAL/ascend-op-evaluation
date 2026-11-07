#!/usr/bin/env python3
"""Build a frozen task-scoped CANNBench method bundle; executes no submitted code."""

import argparse
import gzip
import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

REVISION = "f0488d95b4d44a6a0da1b8cd99e91fbd06181962"
CHUNK_BYTES = 512 * 1024


def task_archive(upstream, task_path):
    path = PurePosixPath(task_path)
    if not path.parts or path.parts[0] != "tasks" or ".." in path.parts or str(path) != task_path:
        raise ValueError("task path must be a normalized path under tasks/")
    subprocess.run(
        ["git", "-C", str(upstream), "cat-file", "-e", REVISION + "^{commit}"], check=True
    )
    paths = ["src", "scripts", "VERSION", "LICENSE", "tasks/metadata", task_path]
    listing = subprocess.check_output(
        ["git", "-C", str(upstream), "ls-tree", "-r", "-l", REVISION, "--", *paths], text=True
    )
    records = listing.splitlines()
    if not records or len(records) > 4096:
        raise ValueError("selected upstream tree is empty or exceeds entry limit")
    total = 0
    for line in records:
        mode, kind, _, size = line.split("\t", 1)[0].split()
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError("selected upstream needs unsupported symlink/submodule resources")
        total += int(size)
    if total > 64 * 1024 * 1024:
        raise ValueError("selected upstream exceeds expanded limit")
    raw = subprocess.check_output(
        ["git", "-C", str(upstream), "archive", "--format=tar", REVISION, *paths]
    )
    data = gzip.compress(raw, mtime=0)
    if len(data) > 8 * CHUNK_BYTES:
        raise ValueError(
            "task archive exceeds eight dependency chunks; select a smaller explicit task scope"
        )
    return data


def candidate_archive(root, files):
    if (
        not isinstance(files, list)
        or not files
        or len(files) > 128
        or len(set(files)) != len(files)
    ):
        raise ValueError("candidate files must be a nonempty unique explicit list")
    output = io.BytesIO()
    total = 0
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name in sorted(files):
            path = PurePosixPath(name)
            if not path.parts or path.is_absolute() or ".." in path.parts or str(path) != name:
                raise ValueError("invalid candidate path")
            current = Path(root)
            for part in path.parts:
                current = current / part
                if current.is_symlink():
                    raise ValueError("candidate paths cannot traverse symlinks")
            fd = os.open(current, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise ValueError("candidate input must be an ordinary file")
                with os.fdopen(os.dup(fd), "rb") as stream:
                    data = stream.read(8 * 1024 * 1024 + 1)
                total += len(data)
                if total > 8 * 1024 * 1024:
                    raise ValueError("candidate sources exceed expanded limit")
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o700 if os.fstat(fd).st_mode & 0o111 else 0o600
                archive.addfile(info, io.BytesIO(data))
            finally:
                os.close(fd)
    data = gzip.compress(output.getvalue(), mtime=0)
    if len(data) > 1024 * 1024:
        raise ValueError("candidate archive exceeds artifact upload limit")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--task-path", required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--candidate-files",
        type=Path,
        required=True,
        help="JSON list of relative files to include; never executes build.sh",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--torch-version", required=True)
    parser.add_argument("--torch-npu-version", required=True)
    args = parser.parse_args()
    archive = task_archive(args.upstream, args.task_path)
    candidate = candidate_archive(args.candidate, json.loads(args.candidate_files.read_text()))
    args.output.mkdir(parents=True, exist_ok=False)
    chunks = []
    for index, start in enumerate(range(0, len(archive), CHUNK_BYTES)):
        data = archive[start : start + CHUNK_BYTES]
        name = f"upstream{index:02d}"
        (args.output / (name + ".bin")).write_bytes(data)
        chunks.append({"name": name, "sha256": hashlib.sha256(data).hexdigest()})
    frozen = {
        "revision": REVISION,
        "task_path": args.task_path,
        "chunks": chunks,
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
    }
    (args.output / "upstream.json").write_text(json.dumps(frozen, indent=2) + "\n")
    (args.output / "harness.py").write_bytes(Path(__file__).with_name("harness.py").read_bytes())
    (args.output / "candidate.tar.gz").write_bytes(candidate)
    template = json.loads(Path(__file__).with_name("harness.method.json").read_text())
    template["descriptor"]["dependencies"] = {c["name"]: "sha256:" + c["sha256"] for c in chunks}
    template["descriptor"]["requirements"]["packages"] = {
        "torch": args.torch_version,
        "torch-npu": args.torch_npu_version,
    }
    (args.output / "method.json").write_text(json.dumps(template, indent=2) + "\n")
    print(
        json.dumps(
            {
                "directory": str(args.output),
                "revision": REVISION,
                "dependency_files": [c["name"] + ".bin" for c in chunks],
                "candidate": "candidate.tar.gz",
                "note": "upload dependencies before method",
            }
        )
    )


if __name__ == "__main__":
    main()
