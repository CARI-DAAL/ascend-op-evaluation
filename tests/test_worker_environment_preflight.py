"""Worker startup observes the complete host environment before serving."""

import os

import pytest
from ascend_op_eval.execution import worker_environment
from ascend_op_eval.execution.worker_environment import (
    HardwarePreflightError,
    ObservedWorkerStack,
    discover_worker_environment,
)


def _observed(**overrides):
    payload = {
        "hardware_model": "Ascend 910B1",
        "driver_version": "26.1.1",
        "runtime_version": "9.2.0",
        "python_version": "3.12.13",
        "torch_version": "2.10.0+cpu",
        "torch_npu_version": "2.10.0.post4",
        "triton_ascend_version": "3.6.0",
    }
    payload.update(overrides)
    return ObservedWorkerStack(**payload)


@pytest.mark.parametrize(
    "field",
    (
        "hardware_model", "driver_version", "runtime_version", "python_version",
        "torch_version", "torch_npu_version", "triton_ascend_version",
    ),
)
def test_discovery_fails_closed_for_every_missing_identity(field):
    with pytest.raises(HardwarePreflightError, match=field):
        discover_worker_environment(
            card=0, observe=lambda _: _observed(**{field: None}),
        )


def _install_fake_vendor_tools(
    monkeypatch, tmp_path, driver_versions=None, compute_models=None,
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    versions = driver_versions or {"4": "26.1.1", "7": "26.1.1"}
    models = compute_models or ["Ascend 910B1", "Ascend 910B1"]
    board_cases = "".join(
        f'    {card}) printf "Software Version : {version}\\n" ;;\n'
        for card, version in versions.items()
    )
    compute_rows = "".join(
        f'  printf "{card} 0 4 {model}\\n"\n'
        for card, model in zip((4, 7), models, strict=True)
    )
    (bin_dir / "npu-smi").write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "info" ] && [ "$2" = "-m" ]; then\n'
        '  printf "NPU ID Chip ID Chip Logic ID Chip Name\\n"\n'
        f"{compute_rows}"
        '  printf "4 1 - Mcu\\n"\n'
        '  printf "7 1 - Mcu\\n"\n'
        'elif [ "$1" = "info" ] && [ "$2" = "-t" ] && [ "$3" = "board" ]; then\n'
        '  case "$5" in\n'
        f"{board_cases}"
        "  esac\n"
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


def test_cpu_observer_requires_homogeneous_host_drivers(monkeypatch, tmp_path):
    _install_fake_vendor_tools(
        monkeypatch,
        tmp_path,
        driver_versions={"4": "26.1.1", "7": "26.1.2"},
    )

    with pytest.raises(
        HardwarePreflightError, match="one homogeneous driver/software version"
    ):
        discover_worker_environment(None)


def test_cpu_observer_preserves_exact_host_model_identity(monkeypatch, tmp_path):
    _install_fake_vendor_tools(
        monkeypatch,
        tmp_path,
        compute_models=["Ascend 910B1", "Ascend910B1"],
    )

    with pytest.raises(
        HardwarePreflightError, match="one homogeneous compute-chip model"
    ):
        discover_worker_environment(None)


def test_observer_reads_selected_card_and_cann_inventory(tmp_path, monkeypatch):
    _install_fake_vendor_tools(monkeypatch, tmp_path)

    profile = discover_worker_environment(7)

    assert profile.hardware_model == "Ascend 910B1"
    assert profile.driver_version == "26.1.1"
    assert profile.runtime_version == "CANN-9.2.0"
    assert profile.toolchain_version == (
        "CANN 9.2.0 / python 3.12.13 / torch 2.10.0+cpu / "
        "torch_npu 2.10.0.post4 / triton_ascend 3.6.0"
    )


def test_cpu_observer_reads_host_hardware_and_fails_without_vendor_tools(
    monkeypatch, tmp_path,
):
    bin_dir = tmp_path / "unavailable-bin"
    bin_dir.mkdir()
    (bin_dir / "npu-smi").write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
    (bin_dir / "npu-smi").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setattr(
        worker_environment, "_cann_version", lambda: "9.2.0",
    )

    with pytest.raises(HardwarePreflightError, match="npu-smi failed"):
        discover_worker_environment(None)
