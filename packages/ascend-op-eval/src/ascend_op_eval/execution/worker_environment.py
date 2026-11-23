"""Fail-closed checks for a worker's deployment-attested hardware profile.

The durable profile is derived from operator inventory settings.  This module
gives NPU workers a startup proof that those settings describe the selected
card and the runtime actually loaded in this process.  CPU workers prove the
runtime/toolchain they can execute, but do not invent hardware or driver facts.
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


class HardwarePreflightError(RuntimeError):
    """The worker cannot prove the deployment-attested stack."""


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

_TOOLCHAIN_PATTERN = re.compile(
    r"^\s*CANN\s+(?P<cann>[A-Za-z0-9+._-]+)\s*/\s*"
    r"python\s+(?P<python>[A-Za-z0-9+._-]+)\s*/\s*"
    r"torch\s+(?P<torch>[A-Za-z0-9+._-]+)\s*/\s*"
    r"torch_npu\s+(?P<torch_npu>[A-Za-z0-9+._-]+)\s*/\s*"
    r"triton_ascend\s+(?P<triton_ascend>[A-Za-z0-9+._-]+)\s*$"
)


def _normalise_model(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return re.sub(r"\s+", "", value).casefold()


def _normalise_runtime(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().casefold()
    return re.sub(r"^cann(?:[ -])?", "", normalized)


def _declared_toolchain(value: str) -> dict[str, str]:
    match = _TOOLCHAIN_PATTERN.fullmatch(value)
    if match is None:
        raise HardwarePreflightError(
            "worker_toolchain_version must use the fixed CANN/python/torch/"
            "torch_npu/triton_ascend identity format"
        )
    return match.groupdict()


def verify_worker_environment(
    settings,
    card: int | None,
    observe: WorkerStackObserver | None = None,
) -> None:
    """Refuse startup when attested and observable worker identity differ.

    ``card is None`` is a CPU worker.  It shares the profile's toolchain and
    CANN identity, but cannot attest a physical NPU; missing hardware fields
    are therefore accepted only on that execution class.  No unsupported stack
    is silently redirected to another profile.
    """
    observed = (observe_worker_stack if observe is None else observe)(card)
    declared_toolchain = _declared_toolchain(settings.worker_toolchain_version)
    expected = {
        "runtime_version": _normalise_runtime(settings.worker_runtime_version),
        "python_version": declared_toolchain["python"],
        "torch_version": declared_toolchain["torch"],
        "torch_npu_version": declared_toolchain["torch_npu"],
        "triton_ascend_version": declared_toolchain["triton_ascend"],
    }
    actual = {
        "runtime_version": _normalise_runtime(observed.runtime_version),
        "python_version": observed.python_version,
        "torch_version": observed.torch_version,
        "torch_npu_version": observed.torch_npu_version,
        "triton_ascend_version": observed.triton_ascend_version,
    }
    if _normalise_runtime(declared_toolchain["cann"]) != expected["runtime_version"]:
        raise HardwarePreflightError(
            "worker_toolchain_version CANN identity differs from worker_runtime_version"
        )

    mismatches = [
        field
        for field in expected
        if expected[field] != actual[field]
    ]
    if card is not None:
        expected["hardware_model"] = _normalise_model(settings.worker_hardware_model)
        expected["driver_version"] = settings.worker_driver_version.strip() or None
        actual["hardware_model"] = _normalise_model(observed.hardware_model)
        actual["driver_version"] = (
            observed.driver_version.strip() or None
            if observed.driver_version is not None
            else None
        )
        mismatches.extend(
            field
            for field in ("hardware_model", "driver_version")
            if expected[field] != actual[field]
        )
    if mismatches:
        raise HardwarePreflightError(
            "worker environment differs from the deployment-attested profile: "
            + ", ".join(mismatches)
        )


def observe_worker_stack(card: int | None) -> ObservedWorkerStack:
    """Read the local vendor/toolchain identity without fallback or guessing."""
    return ObservedWorkerStack(
        hardware_model=None if card is None else _selected_card_model(card),
        driver_version=None if card is None else _selected_card_driver(card),
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


def _selected_card_model(card: int) -> str:
    output = _run_npu_smi("-m")
    candidates: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[0] != str(card):
            continue
        name = " ".join(fields[3:])
        if name.casefold() != "mcu":
            candidates.append(name)
    if len(candidates) != 1:
        raise HardwarePreflightError(
            f"npu-smi did not return exactly one compute chip for card {card}"
        )
    return candidates[0]


def _selected_card_driver(card: int) -> str:
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
