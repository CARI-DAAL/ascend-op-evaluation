"""Explicit custom-method-v1 package, submission and result contracts."""

import base64
import binascii
import hashlib
import re
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

CONTRACT = "custom-method-v1"
MAX_BLOB_BYTES = 1024 * 1024
MAX_PACKAGE_BYTES = 1024 * 1024
MAX_EXECUTION_BYTES = 8 * 1024 * 1024
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Ref = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Name = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")]
Kind = Literal["checker", "measurement", "harness"]


class MethodModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or not path.parts
        or len(value) > 256
        or "\\" in value
        or "\0" in value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise ValueError("method paths must be normalized relative POSIX paths")
    return value


class MethodRequirements(MethodModel):
    runtime: Name = "worker-python-v1"
    device: Literal["cpu", "npu"] = "cpu"
    capabilities: list[Name] = Field(default_factory=lambda: ["python"], max_length=32)
    packages: dict[Name, Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        default_factory=dict,
        max_length=32,
    )
    tools: list[Annotated[str, Field(pattern=r"^[A-Za-z0-9_+.-]{1,64}$")]] = Field(
        default_factory=list,
        max_length=32,
    )


class MethodInput(MethodModel):
    required: bool = True
    media_type: str | None = Field(default=None, max_length=128)


class MethodDescriptor(MethodModel):
    name: Name
    version: Annotated[str, Field(min_length=1, max_length=64)]
    kind: Kind
    entrypoint: Annotated[str, Field(min_length=3, max_length=256)]
    parameters_schema: dict[str, JsonValue]
    inputs: dict[Name, MethodInput] = Field(default_factory=dict, max_length=16)
    output_schema: dict[str, JsonValue] = Field(default_factory=lambda: {"type": "object"})
    output_artifacts: dict[str, MethodInput] = Field(default_factory=dict, max_length=128)
    requirements: MethodRequirements = Field(default_factory=MethodRequirements)
    dependencies: dict[Name, Ref] = Field(default_factory=dict, max_length=8)

    @model_validator(mode="after")
    def valid_descriptor(self):
        from .schemas import validate_schema

        if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", self.entrypoint):
            raise ValueError("method entrypoint must be module:function")
        validate_schema(self.parameters_schema, parameters=True)
        validate_schema(self.output_schema)
        for name in self.output_artifacts:
            safe_path(name)
        return self


class MethodPackage(MethodModel):
    contract_version: Literal["custom-method-v1"] = CONTRACT
    descriptor: MethodDescriptor
    files: dict[str, str] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def valid_files(self):
        if sum(len(v.encode("utf-8")) for v in self.files.values()) > MAX_PACKAGE_BYTES:
            raise ValueError("method source package exceeds 1 MiB")
        for name in self.files:
            safe_path(name)
            if any(str(p) in self.files for p in PurePosixPath(name).parents):
                raise ValueError("method file overlaps a directory")
        module = self.descriptor.entrypoint.split(":")[0].replace(".", "/")
        if module + ".py" not in self.files and module + "/__init__.py" not in self.files:
            raise ValueError("method entrypoint source must be in package")
        return self


class ArtifactUpload(MethodModel):
    contract_version: Literal["custom-method-v1"] = CONTRACT
    media_type: Annotated[str, Field(min_length=1, max_length=128)] = "application/octet-stream"
    content_base64: Annotated[str, Field(max_length=1400000)]

    def content(self):
        try:
            data = base64.b64decode(self.content_base64, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("artifact content must be base64") from error
        if len(data) > MAX_BLOB_BYTES:
            raise ValueError("artifact exceeds 1 MiB")
        return data

    @model_validator(mode="after")
    def valid_content(self):
        self.content()
        return self


class StoredArtifact(ArtifactUpload):
    artifact_ref: Ref
    sha256: Hash
    size_bytes: Annotated[int, Field(ge=0, le=MAX_BLOB_BYTES)]

    @model_validator(mode="after")
    def valid_identity(self):
        data = self.content()
        digest = hashlib.sha256(data).hexdigest()
        if (
            digest != self.sha256
            or self.artifact_ref != "sha256:" + digest
            or len(data) != self.size_bytes
        ):
            raise ValueError("artifact digest or size mismatch")
        return self

    @classmethod
    def from_bytes(cls, data: bytes, media_type="application/octet-stream"):
        digest = hashlib.sha256(data).hexdigest()
        return cls(
            artifact_ref="sha256:" + digest,
            sha256=digest,
            size_bytes=len(data),
            media_type=media_type,
            content_base64=base64.b64encode(data).decode(),
        )


class MethodAlias(MethodModel):
    contract_version: Literal["custom-method-v1"] = CONTRACT
    method_ref: Ref


class MethodLimits(MethodModel):
    log_bytes: int = Field(default=65536, ge=1024, le=1024 * 1024)
    artifact_bytes: int = Field(default=1024 * 1024, ge=1, le=2 * 1024 * 1024)
    artifact_count: int = Field(default=32, ge=0, le=128)


class MethodSubmission(MethodModel):
    contract_version: Literal["custom-method-v1"] = CONTRACT
    method_ref: Annotated[str, Field(min_length=1, max_length=128)]
    parameters: dict[str, JsonValue] = Field(default_factory=dict, max_length=128)
    inputs: dict[Name, Ref] = Field(default_factory=dict, max_length=16)
    deadline_seconds: int = Field(default=300, ge=10, le=3600)
    limits: MethodLimits = Field(default_factory=MethodLimits)


class RegisteredMethod(MethodModel):
    contract_version: Literal["custom-method-v1"] = CONTRACT
    method_ref: Ref
    descriptor_sha256: Hash
    implementation_sha256: Hash
    dependency_digests: dict[str, Hash] = Field(default_factory=dict)
    package: MethodPackage

    @model_validator(mode="after")
    def valid_identity(self):
        identity = package_identity(self.package)
        if any(getattr(self, key) != value for key, value in identity.items()):
            raise ValueError("method package digest mismatch")
        return self


class MethodExecution(RegisteredMethod):
    requested_parameters: dict[str, JsonValue]
    effective_parameters: dict[str, JsonValue]
    inputs: dict[str, StoredArtifact]
    dependencies: dict[str, StoredArtifact]
    runtime_id: str
    runtime_fingerprint: Hash
    capabilities: list[str]
    submission: MethodSubmission
    limits: MethodLimits

    @property
    def device(self):
        return self.package.descriptor.requirements.device

    @model_validator(mode="after")
    def frozen_dependencies_match(self):
        expected = self.package.descriptor.dependencies
        if set(self.dependencies) != set(expected) or any(
            self.dependencies[name].artifact_ref != ref for name, ref in expected.items()
        ):
            raise ValueError("frozen method dependency identity mismatch")
        if self.runtime_id != self.package.descriptor.requirements.runtime:
            raise ValueError("frozen runtime identity mismatch")
        return self


class MethodArtifact(MethodModel):
    name: str = Field(min_length=1, max_length=256)
    sha256: Hash
    size_bytes: int = Field(ge=0, le=MAX_BLOB_BYTES)
    media_type: str = Field(min_length=1, max_length=128)
    truncated: bool = False

    @model_validator(mode="after")
    def valid_name(self):
        safe_path(self.name)
        return self


class MethodIdentity(MethodModel):
    """Public admission identity available even when no method report exists."""

    contract_version: Literal["custom-method-v1"] = CONTRACT
    method_ref: Ref
    name: str
    version: str
    kind: Kind
    descriptor_sha256: Hash
    implementation_sha256: Hash
    dependency_digests: dict[str, Hash]
    requested_parameters: dict[str, JsonValue]
    effective_parameters: dict[str, JsonValue]
    runtime_id: str
    runtime_fingerprint: Hash
    inputs: dict[str, Ref]

    @classmethod
    def from_execution(cls, execution: MethodExecution):
        return cls(
            method_ref=execution.method_ref,
            name=execution.package.descriptor.name,
            version=execution.package.descriptor.version,
            kind=execution.package.descriptor.kind,
            descriptor_sha256=execution.descriptor_sha256,
            implementation_sha256=execution.implementation_sha256,
            dependency_digests=execution.dependency_digests,
            requested_parameters=execution.requested_parameters,
            effective_parameters=execution.effective_parameters,
            runtime_id=execution.runtime_id,
            runtime_fingerprint=execution.runtime_fingerprint,
            inputs={name: value.artifact_ref for name, value in execution.inputs.items()},
        )


class MethodResult(MethodModel):
    contract_version: Literal["custom-method-v1"] = CONTRACT
    method_ref: Ref
    descriptor_sha256: Hash
    implementation_sha256: Hash
    dependency_digests: dict[str, Hash] = Field(default_factory=dict)
    runtime_fingerprint: Hash
    kind: Kind
    outcome: Literal[
        "passed",
        "failed",
        "completed",
        "method_error",
        "protocol_error",
        "environment_unavailable",
        "timed_out",
    ]
    authority: Literal["caller_method"] = "caller_method"
    isolation: Literal["host", "sandbox"] = "host"
    runtime_observation: dict[str, JsonValue] = Field(default_factory=dict)
    requested_parameters: dict[str, JsonValue]
    effective_parameters: dict[str, JsonValue]
    report: dict[str, JsonValue] | None = None
    stdout: str = Field(default="", max_length=1024 * 1024)
    stderr: str = Field(default="", max_length=1024 * 1024)
    logs_truncated: bool = False
    exit_code: int | None = None
    artifacts: list[MethodArtifact] = Field(default_factory=list, max_length=128)
    error: str | None = Field(default=None, max_length=4096)


def package_identity(package: MethodPackage) -> dict:
    """Canonical identity shared by registration and the frozen worker payload."""
    from ..serialization import canonical_json_bytes, sha256_hex

    descriptor = sha256_hex(canonical_json_bytes(package.descriptor.model_dump(mode="json")))
    implementation = sha256_hex(canonical_json_bytes(package.files))
    dependencies = {
        name: ref.removeprefix("sha256:") for name, ref in package.descriptor.dependencies.items()
    }
    fields = {
        "descriptor_sha256": descriptor,
        "implementation_sha256": implementation,
        "dependency_digests": dependencies,
    }
    return {"method_ref": "sha256:" + sha256_hex(canonical_json_bytes(fields)), **fields}
