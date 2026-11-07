"""Custom method executions are bounded real subprocesses, not candidate wrappers."""

import sys
from pathlib import Path

from ascend_op_eval.evaluators.base import run_script


def test_method_log_budget_stops_chatty_process(tmp_path):
    result = run_script(
        [sys.executable, "-u", "-c", "import time; print('x'*100000); time.sleep(30)"],
        tmp_path,
        None,
        budget_seconds=5,
        output_limit_bytes=1024,
        max_log_bytes=2048,
    )
    assert result.outcome == "output_limit"
    assert result.logs_truncated
    assert len(result.stdout.encode()) <= 1024


def execution(
    source, *, kind="checker", params=None, requirements=None, artifacts=None, limits=None
):
    from ascend_op_eval.methods.contracts import (
        MethodExecution,
        MethodLimits,
        MethodPackage,
        MethodSubmission,
        package_identity,
    )

    package = MethodPackage.model_validate(
        {
            "descriptor": {
                "name": "test",
                "version": "1",
                "kind": kind,
                "entrypoint": "checker:run",
                "parameters_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "requirements": requirements or {},
                "output_artifacts": artifacts or {},
            },
            "files": {"checker.py": source},
        }
    )
    identity = package_identity(package)
    limits = MethodLimits(**(limits or {}))
    return MethodExecution(
        **identity,
        package=package,
        requested_parameters=params or {},
        effective_parameters=params or {},
        inputs={},
        dependencies={},
        runtime_id="worker-python-v1",
        runtime_fingerprint="a" * 64,
        capabilities=["python"],
        limits=limits,
        submission=MethodSubmission(method_ref=identity["method_ref"], limits=limits),
    )


def execute(tmp_path, spec, **kwargs):
    from datetime import datetime, timedelta, timezone

    from ascend_op_eval.execution.method_execution import execute_method

    return execute_method(
        spec,
        tmp_path,
        device_id=None,
        deadline_at=datetime.now(timezone.utc) + timedelta(seconds=20),
        lease_valid=lambda: True,
        **kwargs,
    )


def test_method_runtime_returns_distinct_checker_outcomes_and_bounded_artifacts(tmp_path):
    spec = execution(
        "from pathlib import Path\ndef run(request):\n"
        " Path(request['output_dir'],'raw.json').write_text('[1,2]')\n"
        " return {'passed':False}\n",
        artifacts={"raw.json": {"required": True, "media_type": "application/json"}},
    )
    saved = []
    result = execute(tmp_path, spec, artifact_sink=lambda value: saved.append(value))
    assert result.outcome == "failed"
    assert result.authority == "caller_method"
    assert result.isolation == "host"
    assert result.method_ref == spec.method_ref
    assert result.artifacts[0].name == "raw.json"
    assert saved[0]["raw.json"].content() == b"[1,2]"


def test_missing_required_artifact_is_protocol_error(tmp_path):
    result = execute(
        tmp_path,
        execution(
            "def run(request): return {'passed':True}\n",
            artifacts={"required.csv": {"required": True}},
        ),
    )
    assert result.outcome == "protocol_error"
    assert "missing declared" in result.error


def test_method_output_symlink_is_not_followed(tmp_path):
    outside = tmp_path.parent / "private-data"
    outside.write_text("private")
    source = (
        "from pathlib import Path\ndef run(request):\n"
        f" Path(request['output_dir'],'leak').symlink_to({str(outside)!r})\n"
        " return {'passed':True}\n"
    )
    result = execute(tmp_path, execution(source))
    assert result.outcome == "protocol_error"
    assert result.artifacts == []


def test_method_output_limit_rejects_even_zero_exit(tmp_path):
    result = execute(
        tmp_path,
        execution(
            "from pathlib import Path\ndef run(request):\n"
            " Path(request['output_dir'],'big').write_bytes(b'x'*10000)\n"
            " return {'passed':True}\n",
            limits={"artifact_bytes": 10},
        ),
    )
    assert result.outcome == "protocol_error"
    assert "byte budget" in result.error


def test_host_does_not_claim_requested_process_isolation(tmp_path):
    result = execute(
        tmp_path,
        execution(
            "raise AssertionError('must not import')\n",
            requirements={"capabilities": ["python", "process-isolation"]},
        ),
    )
    assert result.outcome == "environment_unavailable"
    assert result.isolation == "host"


def test_real_sandbox_method_cleans_detached_session_child(tmp_path):
    import hashlib
    import json
    import time
    from functools import partial

    from test_cann_runtime import require_bwrap

    require_bwrap()
    root = Path(__file__).resolve().parents[1]
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
                            str(root / "packages/ascend-op-eval/src/ascend_op_eval"),
                        )
                    )
                ],
                "environment": {"PYTHONPATH": str(root)},
            }
        )
    )
    work = tmp_path / "attempt"
    work.mkdir()
    runner = partial(
        run_script,
        environment={
            "TRITON_EVAL_ENGINE_SANDBOX_CONFIG": str(manifest),
            "TRITON_EVAL_ENGINE_SANDBOX_SHA256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
    )
    source = """
import subprocess,sys,time
from pathlib import Path

def run(request):
    marker=Path(request['output_dir'],'heartbeat')
    script=("import time,sys; from pathlib import Path; p=Path(sys.argv[1]); i=0\\n"
            "while True:\\n p.write_text(str(i)); i+=1; time.sleep(0.02)")
    subprocess.Popen([sys.executable,'-c',script,str(marker)],start_new_session=True)
    for _ in range(100):
        if marker.exists(): break
        time.sleep(0.01)
    assert marker.exists()
    return {'passed':True}
"""
    result = execute(
        work,
        execution(source, requirements={"capabilities": ["python", "process-isolation"]}),
        runner=runner,
        isolation="sandbox",
    )
    assert result.outcome == "passed", result.error
    assert result.isolation == "sandbox"
    marker = work / "outputs/heartbeat"
    observed = marker.read_bytes()
    time.sleep(0.15)
    assert marker.read_bytes() == observed


def test_private_attempt_tree_remains_removable(tmp_path):
    import shutil

    work = tmp_path / "attempt"
    work.mkdir()
    assert (
        execute(work, execution("def run(request): return {'passed':True}\n")).outcome == "passed"
    )
    shutil.rmtree(work)
    assert not work.exists()


def test_method_timeout_is_distinct_and_preserves_bounded_logs(tmp_path):
    from datetime import datetime, timedelta, timezone

    from ascend_op_eval.execution.method_execution import execute_method

    spec = execution(
        "import time\ndef run(request):\n print('started',flush=True)\n time.sleep(30)\n"
    )
    result = execute_method(
        spec,
        tmp_path,
        device_id=None,
        deadline_at=datetime.now(timezone.utc) + timedelta(seconds=1.3),
        lease_valid=lambda: True,
    )
    assert result.outcome == "timed_out"
    assert "started" in result.stdout
    assert result.method_ref == spec.method_ref


def test_lease_loss_stops_method_and_prevents_artifact_publication(tmp_path):
    import time
    from datetime import datetime, timedelta, timezone

    import pytest
    from ascend_op_eval.evaluators.base import LeaseLostError
    from ascend_op_eval.execution.method_execution import execute_method

    started = time.monotonic()
    published = []
    with pytest.raises(LeaseLostError):
        execute_method(
            execution("import time\ndef run(request): time.sleep(30)\n"),
            tmp_path,
            device_id=None,
            deadline_at=datetime.now(timezone.utc) + timedelta(seconds=10),
            lease_valid=lambda: time.monotonic() - started < 0.2,
            artifact_sink=lambda value: published.append(value),
        )
    assert not published
    assert time.monotonic() - started < 3


def test_missing_dependency_is_not_hidden_by_absent_required_output(tmp_path):
    result = execute(
        tmp_path,
        execution(
            "def run(request): return {'passed':True}\n",
            requirements={"packages": {"definitely-missing-method-dependency": "1"}},
            artifacts={"required.csv": {"required": True}},
        ),
    )
    assert result.outcome == "environment_unavailable"
    assert "missing package" in result.error


def test_invalid_declared_json_input_is_protocol_error_before_import(tmp_path):
    from ascend_op_eval.methods.contracts import MethodInput, StoredArtifact, package_identity

    spec = execution("raise AssertionError('must not import')\n")
    package = spec.package.model_copy(
        update={
            "descriptor": spec.package.descriptor.model_copy(
                update={"inputs": {"actual": MethodInput(media_type="application/json")}}
            )
        }
    )
    spec = spec.model_copy(
        update={
            **package_identity(package),
            "package": package,
            "inputs": {"actual": StoredArtifact.from_bytes(b"not-json", "application/json")},
        }
    )
    result = execute(tmp_path, spec)
    assert result.outcome == "protocol_error"
    assert "declared JSON input" in result.error
