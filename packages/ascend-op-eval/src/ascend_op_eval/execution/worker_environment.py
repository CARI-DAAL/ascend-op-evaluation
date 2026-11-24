"""Fail-closed discovery of a worker's actual hardware profile.

The durable profile is derived only from identities this process can observe:
the selected card (or the host cards for a CPU worker), the installed CANN
inventory, and the Python packages that will execute work. Missing facts are
startup failures; there is no declaration to compare and no fallback profile.
"""

from __future__ import annotations

import importlib.metadata
import os
import platform
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ascend_op_eval.deployment import HardwareProfileDescriptor, derive_hardware_profile


class HardwarePreflightError(RuntimeError):
    """The worker cannot observe its complete hardware and toolchain stack."""


@dataclass(frozen=True)
class ObservedWorkerStack:
    """Identity observable in this worker process before work is claimed."""

    hardware_model: str | None
    driver_version: str | None
    runtime_version: str
    python_version: str
    torch_version: str
    torch_npu_version: str
    triton_ascend_version: str


WorkerStackObserver = Callable[[int | None], ObservedWorkerStack]


def discover_worker_environment(
    card: int | None,
    observe: WorkerStackObserver | None = None,
) -> HardwareProfileDescriptor:
    """Observe the complete worker stack and derive its routing identity.

    CPU workers run in the same deployment environment and therefore observe
    host NPU identity as well. They cannot guess a hardware model or driver
    version when the vendor tools are unavailable.
    """
    observed = (observe_worker_stack if observe is None else observe)(card)
    required = {
        "hardware_model": observed.hardware_model,
        "driver_version": observed.driver_version,
        "runtime_version": observed.runtime_version,
        "python_version": observed.python_version,
        "torch_version": observed.torch_version,
        "torch_npu_version": observed.torch_npu_version,
        "triton_ascend_version": observed.triton_ascend_version,
    }
    missing = [name for name, value in required.items() if value is None or not value.strip()]
    if missing:
        raise HardwarePreflightError(
            "worker hardware identity is incomplete: " + ", ".join(missing)
        )
    cann_version = observed.runtime_version.strip()
    runtime_version = f"CANN-{cann_version}"
    toolchain_version = (
        f"CANN {cann_version} / "
        f"python {observed.python_version} / torch {observed.torch_version} / "
        f"torch_npu {observed.torch_npu_version} / "
        f"triton_ascend {observed.triton_ascend_version}"
    )
    return HardwareProfileDescriptor(
        hardware_profile=derive_hardware_profile(
            hardware_model=observed.hardware_model.strip(),
            driver_version=observed.driver_version.strip(),
            runtime_version=runtime_version,
            toolchain_version=toolchain_version,
        ),
        hardware_model=observed.hardware_model.strip(),
        driver_version=observed.driver_version.strip(),
        runtime_version=runtime_version,
        toolchain_version=toolchain_version,
        default=False,
    )


def observe_worker_stack(card: int | None) -> ObservedWorkerStack:
    """Read the local vendor/toolchain identity without fallback or guessing."""
    return ObservedWorkerStack(
        hardware_model=_selected_card_model(card),
        driver_version=_selected_card_driver(card),
        runtime_version=_cann_version(),
        python_version=platform.python_version(),
        torch_version=_distribution_version("torch"),
        torch_npu_version=_distribution_version("torch_npu"),
        triton_ascend_version=_distribution_version("triton_ascend"),
    )


def _run_npu_smi(*arguments: str) -> str:
    command = ("npu-smi", "info", *arguments)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise HardwarePreflightError(
            f"cannot observe NPU identity with {command[0]!r}: {error}"
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise HardwarePreflightError(
            f"npu-smi failed with exit code {completed.returncode}: {detail}"
        )
    return completed.stdout


def _selected_card_model(card: int | None) -> str:
    cards = _compute_cards()
    if card is None:
        names = [name for _, name in cards]
        if len(set(names)) != 1:
            raise HardwarePreflightError(
                "npu-smi did not return one homogeneous compute-chip model"
            )
        # CPU workers need one host identity, not one card per compute chip.
        return names[0]
    candidates = [name for card_id, name in cards if card_id == card]
    if len(candidates) != 1:
        raise HardwarePreflightError(
            f"npu-smi did not return exactly one compute chip for card {card}"
        )
    return candidates[0]


def _selected_card_driver(card: int | None) -> str:
    if card is None:
        versions = [_card_driver(card_id) for card_id, _ in _compute_cards()]
        if len(set(versions)) != 1:
            raise HardwarePreflightError(
                "npu-smi did not return one homogeneous driver/software version"
            )
        return versions[0]
    return _card_driver(card)


def _card_driver(card: int) -> str:
    output = _run_npu_smi("-t", "board", "-i", str(card))
    match = re.search(
        r"^\s*Software Version\s*:\s*([^\s]+)\s*$",
        output,
        flags=re.MULTILINE,
    )
    if match is None or match.group(1).casefold() == "na":
        raise HardwarePreflightError(
            f"npu-smi did not expose a driver/software version for card {card}"
        )
    return match.group(1)


def _compute_cards() -> list[tuple[int, str]]:
    output = _run_npu_smi("-m")
    cards: list[tuple[int, str]] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0] != "NPU":
            try:
                card = int(fields[0])
            except ValueError:
                continue
            name = " ".join(fields[3:])
            if name.casefold() != "mcu":
                cards.append((card, name))
    return cards


def _cann_root() -> Path:
    home = os.environ.get("ASCEND_HOME_PATH")
    set_env = os.environ.get("CANN_SET_ENV_PATH")
    if home:
        root = Path(home)
    elif set_env:
        root = Path(set_env).resolve().parent
    else:
        raise HardwarePreflightError(
            "cannot observe CANN identity: ASCEND_HOME_PATH or CANN_SET_ENV_PATH is required"
        )
    try:
        return root.resolve(strict=True)
    except OSError as error:
        raise HardwarePreflightError(f"configured CANN root is unavailable: {error}") from error


def _cann_version() -> str:
    machine = platform.machine().casefold()
    architecture = "x86_64-linux" if machine == "x86_64" else f"{machine}-linux"
    info = _cann_root() / architecture / "ascend_toolkit_install.info"
    try:
        lines = info.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise HardwarePreflightError(f"cannot read CANN inventory {info}: {error}") from error
    for line in lines:
        key, separator, value = line.strip().partition("=")
        if separator and key == "version" and value:
            return value
    raise HardwarePreflightError(f"CANN inventory {info} has no version")


def _distribution_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError as error:
        raise HardwarePreflightError(
            f"required worker package {name!r} is not installed"
        ) from error
