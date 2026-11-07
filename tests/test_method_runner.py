"""The method bootstrap executes external entrypoints in real child processes."""

import json
import subprocess
import sys
from pathlib import Path

RUNNER = (
    Path(__file__).resolve().parents[1]
    / "packages/ascend-op-eval/src/ascend_op_eval/engine/method_runner.py"
)


def invoke(tmp_path, source, *, parameters=None, requirements=None):
    package = tmp_path / "package"
    package.mkdir(exist_ok=True)
    (package / "checker.py").write_text(source)
    output = tmp_path / "outputs"
    output.mkdir(exist_ok=True)
    request = {
        "contract_version": "custom-method-v1",
        "method_ref": "sha256:" + "a" * 64,
        "package_dir": str(package),
        "entrypoint": "checker:run",
        "requirements": requirements or {},
        "parameters": parameters or {},
        "requested_parameters": parameters or {},
        "inputs": {},
        "dependencies": {},
        "output_dir": str(output),
        "device": "cpu",
        "budget_seconds": 30,
    }
    request_path, result_path = tmp_path / "request.json", tmp_path / "result.json"
    request_path.write_text(json.dumps(request))
    proc = subprocess.run(
        [sys.executable, str(RUNNER), str(request_path), str(result_path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(result_path.read_text()), proc


def test_external_checker_uses_effective_parameters_and_emits_artifact(tmp_path):
    source = """
from pathlib import Path

def run(request):
    Path(request['output_dir'], 'evidence.txt').write_text('observed')
    print('checker invoked')
    return {'passed': request['parameters']['tolerance'] >= 0.5}
"""
    report, proc = invoke(tmp_path, source, parameters={"tolerance": 0.1})
    assert report["outcome"] == "completed"
    assert report["report"] == {"passed": False}
    assert "checker invoked" in proc.stdout
    assert (tmp_path / "outputs/evidence.txt").read_text() == "observed"
    report, _ = invoke(tmp_path, source, parameters={"tolerance": 0.5})
    assert report["report"]["passed"] is True


def test_measurement_aggregation_is_owned_by_external_method(tmp_path):
    source = """
import statistics

def run(request):
    # Controlled launches: repeated names within a call and conditional kernels.
    launches = [(0,'a',1), (0,'a',2), (0,'b',7), (1,'a',2), (1,'b',3), (2,'a',90)]
    samples = [sum(duration for call, name, duration in launches if call == index)
               for index in range(3)]
    aggregate = {'mean': statistics.mean, 'median': statistics.median}[
        request['parameters']['aggregation']]
    return {'metric':'controlled_kernel_sum','unit':'us','samples':samples,
            'value':aggregate(samples),'aggregation':request['parameters']['aggregation']}
"""
    report, _ = invoke(tmp_path, source, parameters={"aggregation": "mean"})
    assert report["report"]["value"] == 35
    assert report["report"]["samples"] == [10, 5, 90]
    report, _ = invoke(tmp_path, source, parameters={"aggregation": "median"})
    assert report["report"]["value"] == 10


def test_missing_declared_dependency_prevents_method_import(tmp_path):
    marker = tmp_path / "imported"
    source = (
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "def run(request): return {'passed':True}\n"
    )
    report, _ = invoke(
        tmp_path, source, requirements={"packages": {"definitely-missing-eval-dependency": "1"}}
    )
    assert report["outcome"] == "environment_unavailable"
    assert not marker.exists()


def test_missing_declared_tool_is_environment_failure(tmp_path):
    report, _ = invoke(
        tmp_path,
        "def run(request): return {'passed':True}\n",
        requirements={"tools": ["definitely-missing-eval-tool"]},
    )
    assert report["outcome"] == "environment_unavailable"


def test_method_exception_and_invalid_report_are_different(tmp_path):
    report, proc = invoke(tmp_path, "def run(request): raise RuntimeError('broken checker')\n")
    assert report["outcome"] == "method_error"
    assert "broken checker" in proc.stderr
    report, _ = invoke(tmp_path, "def run(request): return {'value':float('nan')}\n")
    assert report["outcome"] == "protocol_error"
    report, _ = invoke(tmp_path, "def run(request): return 1\n")
    assert report["outcome"] == "protocol_error"
