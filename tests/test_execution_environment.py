"""Execution-environment provenance version detection."""

import importlib.metadata
import sys

import pytest
from ascend_op_eval.runtimes.execution_environment import (
    build_execution_environment,
    is_complete_execution_environment,
)
from conftest import TEST_HARDWARE


def _serve(available: dict[str, str]):
    def version(name: str) -> str:
        if name in available:
            return available[name]
        raise importlib.metadata.PackageNotFoundError(name)

    return version


def test_worker_environment_reads_only_required_worker_distributions(monkeypatch):
    available = {
        "torch": "2.10.0",
        "torch_npu": "2.10.0.post4",
        "triton_ascend": "3.6.0",
        "triton": "3.4.0",
    }
    monkeypatch.setattr(importlib.metadata, "version", _serve(available))
    environment = build_execution_environment(TEST_HARDWARE)
    assert environment.torch_version == "2.10.0"
    assert environment.torch_npu_version == "2.10.0.post4"
    assert environment.triton_version == "3.6.0"


@pytest.mark.parametrize("missing", ["torch", "torch_npu", "triton_ascend"])
def test_worker_environment_fails_closed_when_a_required_distribution_disappears(
    monkeypatch, missing,
):
    available = {
        "torch": "2.10.0",
        "torch_npu": "2.10.0.post4",
        "triton_ascend": "3.6.0",
    }
    del available[missing]
    monkeypatch.setattr(importlib.metadata, "version", _serve(available))

    with pytest.raises(importlib.metadata.PackageNotFoundError):
        build_execution_environment(TEST_HARDWARE)


def test_worker_environment_publishes_the_hardware_profile():
    environment = build_execution_environment(TEST_HARDWARE)
    assert environment.hardware_profile == TEST_HARDWARE.hardware_profile


def test_worker_environment_never_imports_the_triton_runtime(tmp_path, monkeypatch):
    package = tmp_path / "triton"
    package.mkdir()
    (package / "__init__.py").write_text('raise AssertionError("runtime import was unnecessary")\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "triton", raising=False)
    monkeypatch.setattr(importlib.metadata, "version", _serve({
        "torch": "2.10.0", "torch_npu": "2.10.0.post4", "triton_ascend": "3.6.0",
    }))

    environment = build_execution_environment(TEST_HARDWARE)

    assert is_complete_execution_environment(environment)
    assert "triton" not in sys.modules
