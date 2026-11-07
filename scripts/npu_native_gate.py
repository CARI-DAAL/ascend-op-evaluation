#!/usr/bin/env python3
"""Exercise native AscendC builds, correctness and profiler timing via the service.

Run against an isolated NPU service. A compiler, hardware or profiler failure
fails the gate; there is no skip-as-pass path. The small scalar kernels validate
integration, not performance calibration or CANNBench compatibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "plugins/triton-eval/skills/triton-eval/scripts/triton_eval.py"
FIXTURE = ROOT / "tests/fixtures/native/ascendc_smoke"
METHOD = "native_profiler_kernel_sum_v1"


def _data(resource, name):
    check = (resource.get("result") or {}).get(name)
    if not isinstance(check, dict) or check.get("status") != "succeeded":
        raise ValueError(f"{name} has no successful evidence")
    value = check.get("data")
    if not isinstance(value, dict):
        raise ValueError(f"{name} has no data")
    return value


def validate_resource(resource, *, outcome, hardware, runtime, performance=False):
    """Validate actual returned evidence, including full workload coverage."""
    if resource.get("state") != "completed":
        raise ValueError("evaluation did not complete")
    result = resource.get("result") or {}
    environment = (result.get("provenance") or {}).get("execution_environment") or {}
    if (
        environment.get("hardware_model") != hardware
        or environment.get("runtime_version") != runtime
    ):
        raise ValueError("actual worker environment differs from gate requirements")
    correctness = _data(resource, "correctness")
    if correctness.get("outcome") != outcome:
        raise ValueError("unexpected correctness outcome")
    if outcome == "correct":
        if correctness.get("passed") is not True:
            raise ValueError("correctness did not pass")
        # Fixtures each contain two workloads. Outcome=correct must cover both.
        if correctness.get("total_cases") != 2 or correctness.get("passed_cases") != 2:
            raise ValueError("correctness did not cover both fixture workloads")
    elif correctness.get("passed") is not False:
        raise ValueError("negative candidate was not rejected")
    if performance:
        timing = _data(resource, "performance")
        if (
            timing.get("measurement_method") != METHOD
            or timing.get("coverage") != 1
            or timing.get("complete", True) is not True
            or timing.get("selected_cases") != 2
            or timing.get("measured_cases") != 2
        ):
            raise ValueError("incomplete or wrong-method timing")
        cases = timing.get("per_case") or []
        if len(cases) != 2 or {c.get("case_idx") for c in cases} != {0, 1}:
            raise ValueError("timing case coverage differs")
        for case in cases:
            for key in ("implementation_latency_ms", "reference_latency_ms"):
                value = case.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError("invalid timing sample")
            if case.get("baseline_cache_hit") is True:
                raise ValueError("native baseline unexpectedly reused")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-url", required=True)
    parser.add_argument("--capability-file", required=True, type=Path)
    parser.add_argument("--expected-hardware-model", required=True)
    parser.add_argument("--expected-runtime-version", required=True)
    parser.add_argument("--compiler-arch", required=True, help="Bisheng target, e.g. dav-2201")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = {
        "passed": False,
        "scope": "native-ascendc-http-smoke",
        "performance_calibration": False,
        "evaluations": [],
        "expected_hardware_model": args.expected_hardware_model,
        "expected_runtime_version": args.expected_runtime_version,
        "compiler_arch": args.compiler_arch,
        "fixture_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(FIXTURE.iterdir())
            if p.is_file()
        },
    }

    def persist():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        temporary.replace(args.output)

    try:
        with tempfile.TemporaryDirectory(prefix="native-npu-gate-") as work:
            project = Path(work) / "project"
            shutil.copytree(FIXTURE, project)
            entries = [
                ("add", "correct", True),
                ("reduce_sum", "correct", True),
                ("matmul", "correct", True),
                ("wrong-add", "wrong", False),
                ("build-error", "compile_error", False),
                ("runtime-error", "runtime_error", False),
            ]
            for name, expected, performance in entries:
                op = name if name in {"add", "reduce_sum", "matmul"} else "add"
                manifest = json.loads((project / f"{op}.native.json").read_text())
                manifest["build"] = ["bash", "build.sh", args.compiler_arch]
                if name == "wrong-add":
                    manifest["build"].append("ON")
                elif name == "build-error":
                    manifest["build"] = ["bash", "-c", "echo intentional-build-error >&2; exit 7"]
                elif name == "runtime-error":
                    (project / "failure.py").write_text(
                        "def run(x, y):\n"
                        "    raise RuntimeError('intentional native gate failure')\n"
                    )
                    manifest["files"].append("failure.py")
                    manifest["entrypoint"] = "failure:run"
                path = project / "request.native.json"
                path.write_text(json.dumps(manifest))
                command = [
                    sys.executable,
                    "-I",
                    "-S",
                    str(CLI),
                    "benchmark" if performance else "verify",
                    "--url",
                    args.service_url,
                    "--capability-file",
                    str(args.capability_file),
                    "--definition",
                    str(project / f"{op}.definition.json"),
                    "--workloads",
                    str(project / f"{op}.workloads.jsonl"),
                    "--native-project",
                    str(path),
                    "--deadline-seconds",
                    "900",
                    "--timeout",
                    "960",
                    "--poll-interval",
                    "1",
                ]
                if performance:
                    command += ["--method", "profiler", "--warmup", "3", "--repeats", "3"]
                run = subprocess.run(command, capture_output=True, text=True, timeout=990)
                value = json.loads(run.stdout)
                report["evaluations"].append(
                    {"case": name, "exit_code": run.returncode, "resource": value}
                )
                persist()
                if run.returncode != (0 if expected == "correct" else 1):
                    raise ValueError("client did not observe the expected domain outcome")
                validate_resource(
                    value,
                    outcome=expected,
                    performance=performance,
                    hardware=args.expected_hardware_model,
                    runtime=args.expected_runtime_version,
                )
        report["passed"] = True
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        # Avoid copying arbitrary process output or credentials into setup errors.
        report["error"] = {
            "type": type(error).__name__,
            "message": "native gate failed; inspect recorded resources and worker setup",
        }
    persist()
    print(json.dumps({"passed": report["passed"], "output": str(args.output)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
