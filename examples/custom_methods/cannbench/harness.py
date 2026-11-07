"""External full-harness bridge for a task-scoped, fixed CANNBench archive.

The service does not import this module. It runs in an admitted method process.
Actual NPU execution requires the declared isolated runtime and is not CPU-qualified.
"""

import hashlib
import io
import json
import os
import re
import site
import subprocess
import tarfile
import venv
from pathlib import Path, PurePosixPath

REVISION = "f0488d95b4d44a6a0da1b8cd99e91fbd06181962"
MAX_EXPANDED = 64 * 1024 * 1024


def extract_archive(data, target):
    """Extract only bounded regular files/dirs, with no links or host paths."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    total, count = 0, 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive:
            count += 1
            path = PurePosixPath(member.name.rstrip("/"))
            if (
                not path.parts
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in member.name
                or "\0" in member.name
                or count > 4096
                or (not member.isfile() and not member.isdir())
            ):
                raise ValueError("unsupported archive entry")
            total += member.size
            if member.size < 0 or total > MAX_EXPANDED:
                raise ValueError("archive exceeds expanded size limit")
            destination = target.joinpath(*path.parts)
            if destination.exists():
                if member.isdir() and destination.is_dir():
                    continue
                raise ValueError("duplicate archive entry")
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("archive file has no data")
            with source, destination.open("xb") as stream:
                remaining = member.size
                while remaining:
                    chunk = source.read(min(65536, remaining))
                    if not chunk:
                        raise ValueError("truncated archive entry")
                    stream.write(chunk)
                    remaining -= len(chunk)
            destination.chmod(0o700 if member.mode & 0o111 else 0o600)


def private_python(directory):
    """Upstream pip installs into a fresh private venv; runtime deps remain read-only."""
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(directory)
    python = Path(directory) / "bin/python"
    library = Path(
        subprocess.check_output(
            [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            text=True,
        ).strip()
    )
    # Preserve access to the explicitly selected worker runtime, even when its
    # Torch lives in a parent venv rather than the operating-system site-packages.
    paths = [str(Path(path).resolve()) for path in site.getsitepackages() if Path(path).is_dir()]
    (library / "parent-runtime.pth").write_text("\n".join(paths) + "\n")
    return python


def build_command(python, upstream, candidate, report_dir, task_path, parameters):
    mode = parameters["execution_mode"]
    if mode not in {"staged", "single"}:
        raise ValueError("unknown execution mode")
    operator = parameters["operator"]
    if operator is not None and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", operator):
        raise ValueError("operator must be a task identifier")
    task = PurePosixPath(task_path)
    if not task.parts or task.parts[0] != "tasks" or ".." in task.parts:
        raise ValueError("invalid pinned task path")
    command = [
        str(python),
        "-m",
        "kernel_eval.staged_eval" if mode == "staged" else "kernel_eval.cli",
    ]
    if mode == "single":
        command.append("eval")
    command.extend(
        [
            "--bench-name",
            "cann",
            "--source-dir",
            str(candidate),
            "--task-dir",
            str(upstream / task),
            "--reports-dir",
            str(report_dir),
            "--device",
            "npu",
            "--device-id",
            "0",
            "--warmup",
            str(parameters["warmup"]),
            "--repeat",
            str(parameters["repeat"]),
            "--profiler-level",
            parameters["profiler_level"],
            "--eval-seed",
            str(parameters["eval_seed"]),
            "--input-dist",
            parameters["input_dist"],
            "--build-timeout",
            str(parameters["build_timeout_seconds"]),
            "--timeout-per-operator",
            str(parameters["operator_timeout_seconds"]),
            "--perf-metric-strategy",
            parameters["perf_metric_strategy"],
            "--perf-batch-cases" if parameters["batch_cases"] else "--no-perf-batch-cases",
        ]
    )
    if operator is not None:
        command.extend(["--operator", operator])
    if parameters["case_id"] is not None:
        command.extend(["--case-id", parameters["case_id"]])
    if parameters["no_perf"]:
        command.append("--no-perf")
    return command


def run(request):
    manifest = json.loads(Path(__file__).with_name("upstream.json").read_text())
    if manifest["revision"] != REVISION:
        raise ValueError("this method is tied to a different upstream revision")
    chunks = []
    for item in manifest["chunks"]:
        data = Path(request["dependencies"][item["name"]]["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("upstream dependency chunk differs from frozen manifest")
        chunks.append(data)
    archive = b"".join(chunks)
    if hashlib.sha256(archive).hexdigest() != manifest["archive_sha256"]:
        raise ValueError("upstream archive identity mismatch")
    work = Path.cwd()
    upstream, candidate = work / "upstream", work / "candidate"
    extract_archive(archive, upstream)
    extract_archive(Path(request["inputs"]["candidate"]["path"]).read_bytes(), candidate)
    if not (candidate / "build.sh").is_file():
        raise ValueError("candidate archive requires build.sh")
    python = private_python(work / "python-env")
    env = dict(os.environ)
    env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = str(upstream / "src")
    # This pinned upstream explicitly supports a private .run install target.
    # Do not change ASCEND_OPP_PATH, which still provides runtime headers/ops.
    env["MC2_OPP_INSTALL_ROOT"] = str(work / "private-opp")
    env["CANN_BENCH_BUILD_TIMEOUT_SEC"] = str(request["parameters"]["build_timeout_seconds"])
    report_dir = Path(request["output_dir"]) / "reports"
    report_dir.mkdir()
    command = build_command(
        python, upstream, candidate, report_dir, manifest["task_path"], request["parameters"]
    )
    # Parent service supervises this whole process tree and its absolute deadline.
    # Stream stdout/stderr to its bounded log capture instead of hiding diagnostics.
    result = subprocess.run(command, cwd=upstream, env=env, check=False)
    reports = sorted(
        str(path.relative_to(request["output_dir"])) for path in report_dir.rglob("*.json")
    )
    report = {
        "upstream_revision": REVISION,
        "upstream_archive_sha256": manifest["archive_sha256"],
        "task_path": manifest["task_path"],
        "exit_code": result.returncode,
        "completed": result.returncode == 0 and bool(reports),
        "reports": reports,
        "effective_parameters": request["parameters"],
        "scope": "fixed public task snapshot; upstream reports own correctness and scoring",
    }
    Path(request["output_dir"], "harness.json").write_text(json.dumps(report, allow_nan=False))
    # Harness exit failure is preserved as an upstream outcome, not presented as
    # a successful checker pass. Consumers inspect exit_code and original reports.
    return report
