"""Typed deployment identity shared by worker discovery and HTTP."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ascend_op_eval.serialization import canonical_json_bytes, sha256_hex
from ascend_op_eval.versioning import HARDWARE_PROFILE_PATTERN


class DeploymentModel(BaseModel):
    """Strict deployment values: unknown fields and scalar coercion fail."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_default=True,
        allow_inf_nan=False,
    )


def derive_hardware_profile(
    *,
    hardware_model: str,
    driver_version: str,
    runtime_version: str,
    toolchain_version: str,
) -> str:
    """Derive the immutable routing ID for an observed hardware stack."""

    digest = sha256_hex(canonical_json_bytes({
        "hardware_model": hardware_model,
        "driver_version": driver_version,
        "runtime_version": runtime_version,
        "toolchain_version": toolchain_version,
    }))
    return f"hw_{digest[:32]}"


class HardwareProfileDescriptor(DeploymentModel):
    """A complete stack observed by one worker pool.

    The routing ID is derived from these visible fields. Callers may compare
    each field directly and use the ID only as a stable routing token.
    """

    hardware_profile: Annotated[str, Field(pattern=HARDWARE_PROFILE_PATTERN)]
    hardware_model: str = Field(min_length=1)
    driver_version: str = Field(min_length=1)
    runtime_version: str = Field(min_length=1)
    toolchain_version: str = Field(min_length=1)
    default: bool = False

    @model_validator(mode="after")
    def _validate_derived_profile(self) -> "HardwareProfileDescriptor":
        if self.hardware_profile != self.derived_hardware_profile:
            raise ValueError("hardware profile does not derive from its observed fields")
        return self

    @property
    def derived_hardware_profile(self) -> str:
        return derive_hardware_profile(
            hardware_model=self.hardware_model,
            driver_version=self.driver_version,
            runtime_version=self.runtime_version,
            toolchain_version=self.toolchain_version,
        )
