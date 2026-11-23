"""Worker startup must prove the deployment-attested stack before serving."""

import os

import pytest
from ascend_op_eval.config import Settings
from ascend_op_eval.execution import worker_environment
from ascend_op_eval.execution.worker_environment import (
    HardwarePreflightError,
    ObservedWorkerStack,
    verify_worker_environment,
)


def test_matching_npu_worker_stack_passes_preflight():
    settings = Settings(
        worker_hardware_model="Ascend910B1",
        worker_driver_version="26.1.1",
        worker_runtime_version="CANN-9.2.0",
        worker_toolchain_version=(
            "CANN 9.2.0 / python 3.12.13 / torch 2.10.0+cpu / "
            "torch_npu 2.10.0.post4 / triton_ascend 3.6.0"
        ),
    )
    observed = ObservedWorkerStack(
        hardware_model="Ascend 910B1",
        driver_version="26.1.1",
        runtime_version="9.2.0",
        python_version="3.12.13",
        torch_version="2.10.0+cpu",
        torch_npu_version="2.10.0.post4",
        triton_ascend_version="3.6.0",
    )

    verify_worker_environment(settings, card=0, observe=lambda _: observed)


def test_npu_worker_preflight_reports_every_mismatch_and_missing_identity():
    settings = Settings(
        worker_hardware_model="Ascend910B1",
        worker_driver_version="26.1.1",
        worker_runtime_version="CANN-9.2.0",
        worker_toolchain_version=(
            "CANN 9.2.0 / python 3.12.13 / torch 2.10.0+cpu / "
            "torch_npu 2.10.0.post4 / triton_ascend 3.6.0"
        ),
    )
    observed = ObservedWorkerStack(
        hardware_model=None,
        driver_version=None,
        runtime_version="9.1.0",
        python_version="3.11.12",
        torch_version="2.9.0",
        torch_npu_version="2.9.0.post8",
        triton_ascend_version="3.2.0",
    )

    with pytest.raises(HardwarePreflightError, match="hardware_model.*driver_version"):
        verify_worker_environment(settings, card=3, observe=lambda _: observed)


def test_cpu_worker_checks_runtime_and_toolchain_without_guessing_hardware():
    settings = Settings(
        worker_hardware_model="unknown-on-this-host",
        worker_driver_version="unknown-on-this-host",
        worker_runtime_version="CANN-9.2.0",
        worker_toolchain_version=(
            "CANN 9.2.0 / python 3.12.13 / torch 2.10.0+cpu / "
            "torch_npu 2.10.0.post4 / triton_ascend 3.6.0"
        ),
    )
    observed = ObservedWorkerStack(
        hardware_model=None,
        driver_version=None,
        runtime_version="9.2.0",
        python_version="3.12.13",
        torch_version="2.10.0+cpu",
        torch_npu_version="2.10.0.post4",
        triton_ascend_version="3.6.0",
    )

    verify_worker_environment(settings, card=None, observe=lambda _: observed)


def test_observer_reads_selected_card_and_cann_inventory(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "npu-smi").write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "info" ] && [ "$2" = "-m" ]; then\n'
        '  printf "NPU ID Chip ID Chip Logic ID Chip Name\\n"\n'
        '  printf "4 0 4 Ascend 910B1\\n"\n'
        '  printf "4 1 - Mcu\\n"\n'
        'elif [ "$1" = "info" ] && [ "$2" = "-t" ] && [ "$3" = "board" ]; then\n'
        '  printf "Software Version : 26.1.1\\n"\n'
        "else\n"
        '  exit 9\n'
        "fi\n",
        encoding="utf-8",
    )
    (bin_dir / "npu-smi").chmod(0o755)
    cann_root = tmp_path / "cann-9.2.0"
    inventory = cann_root / "aarch64-linux"
    inventory.mkdir(parents=True)
    (inventory / "ascend_toolkit_install.info").write_text(
        "package_name=Ascend-cann-toolkit\nversion=9.2.0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("ASCEND_HOME_PATH", str(cann_root))
    monkeypatch.setattr(worker_environment.platform, "python_version", lambda: "3.12.13")
    monkeypatch.setattr(
        worker_environment.importlib.metadata,
        "version",
        lambda name: {
            "torch": "2.10.0+cpu",
            "torch_npu": "2.10.0.post4",
            "triton_ascend": "3.6.0",
        }[name],
    )

    observed = worker_environment.observe_worker_stack(4)

    assert observed == ObservedWorkerStack(
        hardware_model="Ascend 910B1",
        driver_version="26.1.1",
        runtime_version="9.2.0",
        python_version="3.12.13",
        torch_version="2.10.0+cpu",
        torch_npu_version="2.10.0.post4",
        triton_ascend_version="3.6.0",
    )


def test_cpu_observer_does_not_invoke_npu_smi(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "npu-smi").write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
    (bin_dir / "npu-smi").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.delenv("ASCEND_HOME_PATH", raising=False)
    monkeypatch.delenv("CANN_SET_ENV_PATH", raising=False)
    monkeypatch.setattr(worker_environment, "_cann_version", lambda: "9.2.0")
    monkeypatch.setattr(worker_environment.platform, "python_version", lambda: "3.12.13")
    monkeypatch.setattr(
        worker_environment.importlib.metadata,
        "version",
        lambda name: {
            "torch": "2.10.0+cpu",
            "torch_npu": "2.10.0.post4",
            "triton_ascend": "3.6.0",
        }[name],
    )

    observed = worker_environment.observe_worker_stack(None)

    assert observed.hardware_model is None
    assert observed.driver_version is None
