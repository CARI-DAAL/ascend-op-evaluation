"""Worker-side execution environment for provenance (design section 4.5).

The environment describes the *actual worker*, never the API process: the
hardware/driver/runtime/toolchain fields come from startup observation,
``hardware_count`` is fixed to 1 because each worker process exposes exactly one
card, and package versions are read from the exact required distributions
inside the worker process. It never includes hostname, card serial numbers,
source code, or request inputs.
"""

import importlib.metadata

from ascend_op_eval.api.contract import ExecutionEnvironment
from ascend_op_eval.deployment import HardwareProfileDescriptor


def is_complete_execution_environment(environment: ExecutionEnvironment | None) -> bool:
    """Unknown hardware/software identity cannot authorize trusted evidence reuse."""
    if (
        environment is None
        or environment.hardware_profile is None
        or environment.hardware_count <= 0
    ):
        return False
    return all(
        isinstance(value, str) and bool(value.strip())
        for field, value in environment.model_dump().items()
        if field != "hardware_count"
    )


def _required_version(distribution: str) -> str:
    return importlib.metadata.version(distribution)


def build_execution_environment(hardware: HardwareProfileDescriptor) -> ExecutionEnvironment:
    """Assemble the worker environment from observed identity and packages."""
    return ExecutionEnvironment(
        hardware_model=hardware.hardware_model,
        hardware_profile=hardware.hardware_profile,
        hardware_count=1,
        driver_version=hardware.driver_version,
        runtime_version=hardware.runtime_version,
        torch_version=_required_version("torch"),
        torch_npu_version=_required_version("torch_npu"),
        triton_version=_required_version("triton_ascend"),
        toolchain_version=hardware.toolchain_version,
    )
