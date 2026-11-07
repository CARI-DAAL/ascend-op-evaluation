"""External method examples execute real code with file-based inputs."""

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "examples/custom_methods"


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def request(tmp_path, parameters, **inputs):
    out = tmp_path / "outputs"
    out.mkdir(exist_ok=True)
    descriptors = {}
    for name, data in inputs.items():
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(data))
        descriptors[name] = {"path": str(path), "media_type": "application/json"}
    return {
        "parameters": parameters,
        "inputs": descriptors,
        "output_dir": str(out),
        "dependencies": {},
        "device": "cpu",
        "budget_seconds": 60,
    }


def test_external_checker_parameter_changes_real_decision(tmp_path):
    checker = module(ROOT / "checker/checker.py", "example_checker")
    invocation = request(
        tmp_path, {"atol": 0.01, "rtol": 0}, actual=[1.0, 2.1], reference=[1.0, 2.0]
    )
    assert checker.run(invocation)["passed"] is False
    invocation["parameters"]["atol"] = 0.2
    assert checker.run(invocation)["passed"] is True
    assert (tmp_path / "outputs/comparison.json").is_file()


def test_external_measurement_counts_repeated_and_conditional_launches(tmp_path):
    measure = module(ROOT / "measurement/measurement.py", "example_measurement")
    launches = {
        "invocations": [
            {
                "launches": [
                    {"name": "warm", "duration_us": 999, "role": "warmup"},
                    {"name": "a", "duration_us": 0.5},
                    {"name": "a", "duration_us": 0.5},
                    {"name": "b", "duration_us": 100},
                ]
            },
            {"launches": [{"name": "a", "duration_us": 100}, {"name": "b", "duration_us": 1}]},
            {"launches": [{"name": "a", "duration_us": 100}, {"name": "b", "duration_us": 100}]},
        ]
    }
    invocation = request(tmp_path, {"aggregation": "median_call_total"}, launches=launches)
    median = measure.run(invocation)
    assert median["value"] == 101
    assert median["samples"] == [101, 101, 200]
    invocation["parameters"]["aggregation"] = "sum_kernel_medians"
    assert measure.run(invocation)["value"] == 200
    launches["invocations"][1]["launches"].append({"name": "conditional", "duration_us": 2})
    launches["invocations"][2]["launches"].append({"name": "conditional", "duration_us": 4})
    invocation = request(tmp_path, {"aggregation": "sum_kernel_medians"}, launches=launches)
    assert measure.run(invocation)["value"] == 203


def test_pinned_cannbench_modules_are_byte_identical_to_recorded_source():
    vendor = ROOT / "cannbench/vendor"
    provenance = json.loads((vendor / "provenance.json").read_text())
    assert provenance["revision"] == "f0488d95b4d44a6a0da1b8cd99e91fbd06181962"
    for entry in provenance["files"]:
        assert (
            hashlib.sha256((vendor / entry["target_path"]).read_bytes()).hexdigest()
            == entry["sha256"]
        )


@pytest.mark.parametrize(
    "actual,reference,threshold,passed",
    [
        ([1.0, 2.0], [1.0, 2.0], None, True),
        ([1.0, 2.1], [1.0, 2.0], None, False),
        ([1.0, 2.1], [1.0, 2.0], 0.1, True),
        ([1.0, 2.0], [1.0, 2.0], 0.0, True),
    ],
)
def test_cannbench_checker_matches_real_upstream_numeric_code(
    tmp_path,
    monkeypatch,
    actual,
    reference,
    threshold,
    passed,
):
    import torch

    monkeypatch.syspath_prepend(str(ROOT / "cannbench"))
    from vendor.pinned.utils.compare import compare_tensors

    checker = module(ROOT / "cannbench/cannbench_checker.py", "pinned_checker")
    invocation = request(
        tmp_path,
        {"custom_thresholds": {} if threshold is None else {"float32": threshold}},
        actual={"outputs": [{"dtype": "float32", "data": actual}]},
        reference={"outputs": [{"dtype": "float64", "data": reference}]},
    )
    direct = compare_tensors(
        torch.tensor(actual, dtype=torch.float32),
        torch.tensor(reference, dtype=torch.float64),
        dtype="float32",
        custom_thresholds={} if threshold is None else {"float32": threshold},
    )
    wrapped = checker.run(invocation)
    assert wrapped["passed"] is direct.passed is passed
    assert wrapped["mere"] == direct.mere
    assert wrapped["mare"] == direct.mare


def test_cannbench_checker_compares_composite_and_integer_outputs(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "cannbench"))
    checker = module(ROOT / "cannbench/cannbench_checker.py", "pinned_checker_multi")
    data = {
        "outputs": [
            {"dtype": "float32", "data": [1.0]},
            {"dtype": "int64", "data": [9223372036854775807]},
        ]
    }
    invocation = request(
        tmp_path,
        {"custom_thresholds": {}},
        actual=data,
        reference=data,
    )
    assert checker.run(invocation)["passed"] is True
    data["outputs"][1]["data"] = [9223372036854775806]
    Path(invocation["inputs"]["actual"]["path"]).write_text(json.dumps(data))
    assert checker.run(invocation)["passed"] is False


def test_cannbench_measurement_matches_pinned_parser_not_median_of_totals(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.syspath_prepend(str(ROOT / "cannbench"))
    from vendor.pinned.perf_strategy import KernelDetailsStrategy, ProfFileLocations

    measure = module(ROOT / "cannbench/cannbench_measurement.py", "pinned_measurement")
    source = ROOT / "cannbench/kernel_details.csv"
    invocation = request(tmp_path, {})
    invocation["inputs"]["kernel_details"] = {"path": str(source), "media_type": "text/csv"}
    expected = SimpleNamespace(elapsed_us=0, error_msg=None, metadata={}, op_times={})
    KernelDetailsStrategy().parse(ProfFileLocations(csv_path=str(source)), expected)
    result = measure.run(invocation)
    assert result["value"] == expected.elapsed_us == 200.0
    assert result["per_kernel_medians_us"] == {"a": 100.0, "b": 100.0}
    assert result["aggregation"] == "sum_per_kernel_medians"
    assert (tmp_path / "outputs/kernel_details.csv").read_bytes() == source.read_bytes()


def test_harness_rejects_archive_path_escape_before_writing_outside(tmp_path):
    harness = module(ROOT / "cannbench/harness.py", "harness_safety")
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        info = tarfile.TarInfo("../outside")
        info.size = 6
        archive.addfile(info, io.BytesIO(b"escape"))
    with pytest.raises(ValueError, match="archive entry"):
        harness.extract_archive(data.getvalue(), tmp_path / "unpacked")
    assert not (tmp_path / "outside").exists()


def test_harness_builds_exact_argument_tokens_and_preserves_zero_false(tmp_path):
    harness = module(ROOT / "cannbench/harness.py", "harness_arguments")
    manifest = json.loads((ROOT / "cannbench/harness.method.json").read_text())
    parameters = {
        name: field["default"]
        for name, field in manifest["descriptor"]["parameters_schema"]["properties"].items()
    }
    parameters.update(warmup=0, eval_seed=0, no_perf=False, batch_cases=False)
    command = harness.build_command(
        "python",
        tmp_path / "upstream",
        tmp_path / "candidate",
        tmp_path / "reports",
        "tasks/level1/Exp",
        parameters,
    )
    assert command[:3] == ["python", "-m", "kernel_eval.staged_eval"]
    assert command[command.index("--warmup") + 1] == "0"
    assert command[command.index("--eval-seed") + 1] == "0"
    assert "--no-perf" not in command
    assert "--no-perf-batch-cases" in command


def test_upstream_archive_uses_pinned_git_bytes_not_dirty_worktree(tmp_path, monkeypatch):
    prepare = module(ROOT / "cannbench/prepare_harness.py", "prepare_harness_test")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    for relative in [
        "src/module.py",
        "scripts/run.sh",
        "VERSION",
        "LICENSE",
        "tasks/metadata/VERSION",
        "tasks/level1/Exp/golden.py",
    ]:
        path = checkout / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("original\n")
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    subprocess.run(["git", "-C", str(checkout), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    revision = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    monkeypatch.setattr(prepare, "REVISION", revision)
    (checkout / "src/module.py").write_text("dirty\n")
    archive = prepare.task_archive(checkout, "tasks/level1/Exp")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source:
        assert source.extractfile("src/module.py").read() == b"original\n"


def test_harness_pip_installs_only_into_private_python(tmp_path):
    harness = module(ROOT / "cannbench/harness.py", "harness_private_python")
    python = harness.private_python(tmp_path / "python-env")
    wheel = tmp_path / "cannbench_method_fixture-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("cannbench_method_fixture.py", "VALUE = 17\n")
        archive.writestr(
            "cannbench_method_fixture-1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: cannbench-method-fixture\nVersion: 1.0\n",
        )
        archive.writestr(
            "cannbench_method_fixture-1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr("cannbench_method_fixture-1.0.dist-info/RECORD", "")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    value = subprocess.check_output(
        [str(python), "-c", "import cannbench_method_fixture as m; print(m.VALUE)"], text=True
    )
    assert value.strip() == "17"
    parent = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import importlib.util; print(importlib.util.find_spec('cannbench_method_fixture'))",
        ],
        text=True,
    )
    assert parent.strip() == "None"
