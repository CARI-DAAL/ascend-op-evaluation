"""Exercise the portable agent CLI against a configured CPU/NPU service."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.test_eval_service import build_request

pytestmark = pytest.mark.npu
CLIENT = (Path(__file__).resolve().parents[1] / "plugins/ascend-op-eval/skills/ascend-op-eval"
          / "scripts/ascend_op_eval.py")


def test_preflight_then_device_verify(tmp_path):
    if not all(os.environ.get(key) for key in (
        "ASCEND_OP_EVAL_CLIENT_URL", "ASCEND_OP_EVAL_CLIENT_CAPABILITY_FILE",
    )):
        pytest.skip("configure the test service URL and capability file")

    def run(*args, expected=0):
        started = time.monotonic()
        process = subprocess.run(
            [sys.executable, str(CLIENT), *args, "--timeout", "600"],
            capture_output=True, text=True, timeout=610, cwd=tmp_path,
        )
        assert process.returncode == expected, (process.stderr, process.stdout)
        result = json.loads(process.stdout)
        if "evaluation_id" in result:
            print(args[0], result["evaluation_id"], f"{time.monotonic() - started:.3f}s")
            assert result["state"] == "completed"
        return result

    print(json.dumps(run("version")))
    add = build_request(measure_speed=False)
    candidate = tmp_path / "add.py"
    candidate.write_text("return 1\n", encoding="utf-8")
    bad = run("preflight", "--triton", str(candidate), expected=1)["result"]
    candidate.write_text(add["triton_code"], encoding="utf-8")
    good = run("preflight", "--triton", str(candidate))["result"]
    for result, verdict in ((bad, "compile_error"), (good, "compiled")):
        compile_check = result["compile"]
        assert compile_check["status"] == "succeeded"
        data = compile_check["data"]
        assert (data["compile_mode"], data["compiler_stage"]) == ("python_bytecode", "frontend")
        assert data["outcome"] == verdict
        assert result["provenance"]["execution_environment"] is None
        assert result["correctness"] is None and result["performance"] is None
    assert "line 1" in bad["compile"]["data"]["error_excerpt"]

    (tmp_path / "definition.json").write_text(json.dumps(add["definition"]), encoding="utf-8")
    (tmp_path / "workloads.json").write_text(json.dumps(add["workloads"]), encoding="utf-8")
    verified = run("verify", "--definition", "definition.json", "--workloads", "workloads.json",
                   "--triton", str(candidate))["result"]
    correctness = verified["correctness"]["data"]
    assert correctness["outcome"] == "correct"
    assert correctness["passed_cases"] == correctness["total_cases"] == len(add["workloads"])
    assert verified["provenance"]["execution_environment"] is not None
