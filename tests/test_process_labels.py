"""Read the real Linux process name at service-owned Python entrypoints."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "packages/ascend-op-eval/src/ascend_op_eval" / "engine"


@pytest.mark.parametrize(
    "script,phase",
    [
        ("verify.py", "Vfy"),
        ("benchmark.py", "Bench"),
        ("single_benchmark.py", "Bench"),
        ("joint_measurement.py", "Bench"),
        ("profile_runner.py", "Prof"),
    ],
)
@pytest.mark.parametrize("backend,prefix", [("ascendc", "AscC"), ("triton", "Trit")])
def test_engine_entrypoint_sets_backend_stage_and_task_before_device_import(
    script,
    phase,
    backend,
    prefix,
):
    probe = (
        "import runpy,sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0, {str(ENGINE)!r})\n"
        f"sys.argv = [{str(ENGINE / script)!r}, '--help']\n"
        "try: runpy.run_path(sys.argv[0], run_name='__main__')\n"
        "except SystemExit as e:\n"
        " assert e.code == 0\n"
        "print('PROCESS_COMM=' + Path('/proc/self/comm').read_text().strip())\n"
    )
    env = dict(os.environ)
    env["TRITON_EVAL_PROCESS_CONTEXT"] = json.dumps(
        {
            "backend": backend,
            "evaluation_id": "ev_" + "0" * 28 + "a1b2",
            "attempt_id": "at_" + "1" * 32,
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    observed = next(
        line.split("=", 1)[1]
        for line in result.stdout.splitlines()
        if line.startswith("PROCESS_COMM=")
    )
    assert observed == f"{prefix}-{phase}-a1b2"


def test_worker_context_reaches_real_child_with_explicit_environment(tmp_path):
    from types import SimpleNamespace

    from ascend_op_eval.evaluators.base import run_script
    from ascend_op_eval.execution.process_title import (
        evaluation_process,
        identify_request,
        process_phase,
    )

    original = Path("/proc/self/comm").read_text()
    probe = (
        "from ascend_op_eval.execution.process_title import set_stage\n"
        "from pathlib import Path\n"
        "set_stage('benchmark', case=3, initialize=True)\n"
        "print(Path('/proc/self/comm').read_text().strip())\n"
    )
    with evaluation_process("ev_" + "0" * 28 + "abcd", "at_" + "1" * 32):
        identify_request(SimpleNamespace(native_candidate=object(), implementation="comparison"))
        with process_phase("build"):
            assert Path("/proc/self/comm").read_text().strip() == "AscC-WBld-abcd"
        result = run_script(
            [sys.executable, "-c", probe],
            tmp_path,
            None,
            environment={"PATH": os.environ["PATH"]},
            budget_seconds=10,
        )
        assert result.exit_code == 0, result.stderr
        assert result.stdout.strip() == "AscC-B003-abcd"
    assert Path("/proc/self/comm").read_text() == original


@pytest.mark.parametrize("backend,prefix", [("ascendc", "AscC"), ("triton", "Trit")])
def test_case_execution_names_candidate_reference_and_comparison(backend, prefix):
    probe = """
import json
from pathlib import Path
import torch
from ascend_op_eval.engine import verify
from ascend_op_eval.execution.process_title import set_stage
seen = []
def comm(): return Path('/proc/self/comm').read_text().strip()
class Reference(torch.nn.Module):
    def forward(self, x):
        seen.append(comm())
        return x + 1
class Candidate(torch.nn.Module):
    _native_candidate = BACKEND == 'ascendc'
    def forward(self, x):
        seen.append(comm())
        return x + 1
set_stage('verify', initialize=True)
verify.run_single_case(verify.ModelPair(Reference(), Candidate()),
                      [torch.ones(2)], 'cpu', verify.CaseContext(3, 3))
print('LABELS=' + json.dumps([*seen, comm()]))
""".replace("BACKEND", repr(backend))
    env = {
        **os.environ,
        "TRITON_EVAL_PROCESS_CONTEXT": json.dumps(
            {
                "backend": backend,
                "evaluation_id": "ev_" + "0" * 28 + "cafe",
            }
        ),
    }
    result = subprocess.run(
        [sys.executable, "-c", probe], env=env, cwd=ROOT, text=True, capture_output=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(
        next(s[7:] for s in result.stdout.splitlines() if s.startswith("LABELS="))
    )
    assert observed == [f"{prefix}-V003-cafe", f"{prefix}-R003-cafe", f"{prefix}-C003-cafe"]


def test_missing_setproctitle_still_names_worker_and_preserves_utf8():
    probe = """
import sys
from pathlib import Path
sys.modules['setproctitle'] = None
from scripts.run_worker import set_process_title
from ascend_op_eval.execution.process_title import set_process_title as rename
set_process_title()
print(Path('/proc/self/comm').read_text().strip())
rename('A算子验证阶段', detail='ignored without optional module')
print(Path('/proc/self/comm').read_text().strip())
"""
    result = subprocess.run(
        [sys.executable, "-c", probe], cwd=ROOT, text=True, capture_output=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["Eval-Idle", "A算子验证"]


def test_sandbox_preserves_only_safe_process_context(tmp_path):
    import hashlib

    from ascend_op_eval.runtimes.sandbox import isolate_command

    manifest = tmp_path / "sandbox.json"
    content = json.dumps({"readonly_mounts": [], "environment": {}}).encode()
    manifest.write_bytes(content)
    env = {
        "TRITON_EVAL_ENGINE_SANDBOX_CONFIG": str(manifest),
        "TRITON_EVAL_ENGINE_SANDBOX_SHA256": hashlib.sha256(content).hexdigest(),
        "TRITON_EVAL_PROCESS_CONTEXT": json.dumps(
            {
                "backend": "ascendc",
                "evaluation_id": "ev_" + "0" * 28 + "abcd",
                "attempt_id": "at_" + "1" * 32,
                "secret": "not-forwarded",
            }
        ),
    }
    args, _ = isolate_command([sys.executable, "-c", "pass"], tmp_path, None, env)
    index = args.index("TRITON_EVAL_PROCESS_CONTEXT")
    forwarded = json.loads(args[index + 1])
    assert forwarded["backend"] == "ascendc"
    assert forwarded["evaluation_id"].endswith("abcd")
    assert "not-forwarded" not in args[index + 1]


@pytest.mark.parametrize(
    "mode,expected",
    [
        (["--describe-cases"], "AscC-Input-abcd"),
        (["--case-idx", "2"], "AscC-P003-abcd"),
    ],
)
def test_generated_profiler_child_is_named_before_loading_torch(tmp_path, mode, expected):
    from ascend_op_eval.engine.profile_runner import write_runner

    # Interrupt at the framework import to inspect the actual generated runner
    # without an NPU; its proctitle must already be set before device startup.
    (tmp_path / "torch.py").write_text(
        "from pathlib import Path\n"
        "raise RuntimeError('PROCESS_COMM=' + Path('/proc/self/comm').read_text().strip())\n"
    )
    runner = write_runner(str(tmp_path))
    env = {
        **os.environ,
        "TRITON_EVAL_PROCESS_CONTEXT": json.dumps(
            {
                "backend": "ascendc",
                "evaluation_id": "ev_" + "0" * 28 + "abcd",
            }
        ),
    }
    result = subprocess.run(
        [
            sys.executable,
            runner,
            "--engine-dir",
            str(ENGINE),
            "--verify-dir",
            str(tmp_path),
            "--op-name",
            "probe",
            "--triton-impl-name",
            "native_impl",
            *mode,
        ],
        env=env,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "RuntimeError: PROCESS_COMM=" + expected in result.stderr


def test_full_process_title_keeps_full_task_attempt_and_case():
    pytest.importorskip("setproctitle")
    evaluation_id, attempt_id = "ev_" + "a" * 32, "at_" + "b" * 32
    env = {
        **os.environ,
        "TRITON_EVAL_PROCESS_CONTEXT": json.dumps(
            {
                "backend": "ascendc",
                "evaluation_id": evaluation_id,
                "attempt_id": attempt_id,
            }
        ),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path\n"
                "from ascend_op_eval.execution.process_title import set_stage\n"
                "set_stage('benchmark', case=12, initialize=True)\n"
                "print(Path('/proc/self/cmdline').read_bytes().replace(b'\\0', b' ').decode())\n"
            ),
        ],
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "backend=ascendc phase=benchmark" in result.stdout
    assert evaluation_id in result.stdout and attempt_id in result.stdout
    assert "case=12" in result.stdout


def test_worker_restores_identity_after_exception_and_does_not_leak_task():
    from types import SimpleNamespace

    from ascend_op_eval.execution.process_title import (
        evaluation_process,
        identify_request,
        process_environment,
    )

    original = Path("/proc/self/comm").read_text()
    with pytest.raises(RuntimeError, match="test failure"):
        with evaluation_process("ev_" + "c" * 32, "at_" + "d" * 32):
            identify_request(SimpleNamespace(native_candidate=None, implementation="comparison"))
            assert Path("/proc/self/comm").read_text().strip() == "Trit-Job-cccc"
            raise RuntimeError("test failure")
    assert Path("/proc/self/comm").read_text() == original
    assert process_environment() == {}


def test_real_sandbox_child_keeps_task_label(tmp_path):
    import hashlib

    from ascend_op_eval.evaluators.base import run_script
    from test_cann_runtime import require_bwrap

    require_bwrap()
    manifest = tmp_path / "sandbox.json"
    manifest.write_text(
        json.dumps(
            {
                "readonly_mounts": [
                    [path, path]
                    for path in dict.fromkeys(
                        (
                            "/usr",
                            sys.base_prefix,
                            sys.prefix,
                            str(ROOT / "packages/ascend-op-eval/src/ascend_op_eval"),
                        )
                    )
                ],
                "environment": {"PYTHONPATH": str(ROOT)},
            }
        )
    )
    work = tmp_path / "attempt"
    work.mkdir()
    result = run_script(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path\n"
                "from ascend_op_eval.execution.process_title import set_stage\n"
                "set_stage('profile', case=2, initialize=True)\n"
                "print(Path('/proc/self/comm').read_text().strip())\n"
            ),
        ],
        work,
        None,
        budget_seconds=10,
        environment={
            "TRITON_EVAL_ENGINE_SANDBOX_CONFIG": str(manifest),
            "TRITON_EVAL_ENGINE_SANDBOX_SHA256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "TRITON_EVAL_PROCESS_CONTEXT": json.dumps(
                {
                    "backend": "ascendc",
                    "evaluation_id": "ev_" + "0" * 28 + "cafe",
                }
            ),
        },
    )
    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() == "AscC-P002-cafe"
