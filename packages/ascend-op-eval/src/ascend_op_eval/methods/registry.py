"""Caller-scoped immutable packages and inputs backed by the durable Redis."""

import redis

from ascend_op_eval.methods.contracts import (
    MAX_EXECUTION_BYTES,
    ArtifactUpload,
    MethodExecution,
    MethodPackage,
    MethodSubmission,
    RegisteredMethod,
    StoredArtifact,
    package_identity,
)
from ascend_op_eval.methods.schemas import effective_parameters
from ascend_op_eval.serialization import canonical_json_bytes, sha256_hex


class MethodRegistryError(ValueError):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.status = code, status


class MethodRegistry:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    def _key(self, caller, kind, identity):
        owner = sha256_hex(caller.caller_id.encode())
        return f"{self.settings.redis_prefix}:methods:{owner}:{kind}:{identity}"

    def _write(self, caller, key, value: bytes, *, immutable=True):
        """Atomically account payload bytes and records across the caller registry.

        The ledger is bounded by the configured record limit. Expired data is
        removed from accounting before every write; all writers watch the same
        caller ledger so concurrent uploads cannot overbook the budget.
        """
        ledger = self._key(caller, "quota", "v1")
        while True:
            transaction = self.client.pipeline()
            try:
                transaction.watch(ledger, key)
                records = transaction.hgetall(ledger)
                if len(records) > 4096:
                    raise MethodRegistryError(
                        "METHOD_REGISTRY_INTEGRITY_ERROR",
                        "registry accounting exceeds bounds",
                        500,
                    )
                keys = list(records)
                with self.client.pipeline(transaction=False) as probe:
                    for record_key in keys:
                        probe.exists(record_key)
                    present = probe.execute()
                stale = [
                    record_key
                    for record_key, exists in zip(keys, present, strict=True)
                    if not exists
                ]
                try:
                    active = {
                        record_key: int(records[record_key])
                        for record_key, exists in zip(keys, present, strict=True)
                        if exists
                    }
                except ValueError as error:
                    raise MethodRegistryError(
                        "METHOD_REGISTRY_INTEGRITY_ERROR",
                        "registry accounting is invalid",
                        500,
                    ) from error
                if any(size < 0 for size in active.values()):
                    raise MethodRegistryError(
                        "METHOD_REGISTRY_INTEGRITY_ERROR",
                        "registry accounting is invalid",
                        500,
                    )
                old = transaction.get(key)
                effective = old if immutable and old is not None else value
                byte_key = key.encode()
                used = sum(active.values())
                next_bytes = used - active.get(byte_key, 0) + len(effective)
                next_records = len(active) + (byte_key not in active)
                grows = next_bytes > used or next_records > len(active)
                if grows and (
                    next_bytes > self.settings.method_registry_max_bytes
                    or next_records > self.settings.method_registry_max_records
                ):
                    raise MethodRegistryError(
                        "METHOD_REGISTRY_LIMIT_EXCEEDED",
                        "caller method registry byte or record limit exceeded",
                        413,
                    )
                transaction.multi()
                if stale:
                    transaction.hdel(ledger, *stale)
                # Reuploading identical content retains its bytes but refreshes
                # retention without charging a second copy.
                transaction.set(key, effective, ex=self.settings.retention_seconds)
                transaction.hset(ledger, key, str(len(effective)))
                transaction.expire(ledger, self.settings.retention_seconds)
                transaction.execute()
                return
            except redis.WatchError:
                continue
            finally:
                transaction.reset()

    def register(self, caller, package: MethodPackage, expected_digest=None):
        package = MethodPackage.model_validate(package)
        for ref in package.descriptor.dependencies.values():
            self.artifact(caller, ref)
        identity = package_identity(package)
        if expected_digest is not None and expected_digest != identity["method_ref"]:
            raise MethodRegistryError("METHOD_DIGEST_MISMATCH", "method digest does not match")
        result = RegisteredMethod(package=package, **identity)
        key = self._key(caller, "package", result.method_ref)
        content = canonical_json_bytes(result.model_dump(mode="json"))
        self._write(caller, key, content)
        return self.resolve(caller, result.method_ref)

    def resolve(self, caller, ref):
        if not ref.startswith("sha256:"):
            alias = self.client.get(self._key(caller, "alias", ref))
            if alias is None:
                raise MethodRegistryError("METHOD_NOT_FOUND", "method is unavailable", 404)
            ref = alias.decode()
        content = self.client.get(self._key(caller, "package", ref))
        if content is None:
            raise MethodRegistryError("METHOD_NOT_FOUND", "method is unavailable", 404)
        try:
            result = RegisteredMethod.model_validate_json(content)
            if result.method_ref != ref:
                raise ValueError("identity differs")
            return result
        except ValueError as error:
            raise MethodRegistryError(
                "METHOD_DIGEST_MISMATCH",
                "stored method integrity check failed",
                500,
            ) from error

    def alias(self, caller, alias, ref):
        result = self.resolve(caller, ref)
        self._write(
            caller, self._key(caller, "alias", alias), result.method_ref.encode(), immutable=False
        )
        return {
            "contract_version": "custom-method-v1",
            "alias": alias,
            "method_ref": result.method_ref,
        }

    def upload(self, caller, upload: ArtifactUpload):
        result = StoredArtifact.from_bytes(upload.content(), upload.media_type)
        key = self._key(caller, "artifact", result.artifact_ref)
        self._write(caller, key, canonical_json_bytes(result.model_dump(mode="json")))
        stored = self.artifact(caller, result.artifact_ref)
        if stored.media_type != result.media_type:
            raise MethodRegistryError(
                "ARTIFACT_METADATA_CONFLICT",
                "artifact media type differs from its sealed record",
                409,
            )
        return stored

    def artifact(self, caller, ref):
        raw = self.client.get(self._key(caller, "artifact", ref))
        if raw is None:
            raise MethodRegistryError("ARTIFACT_NOT_FOUND", "artifact is unavailable", 404)
        try:
            result = StoredArtifact.model_validate_json(raw)
            if result.artifact_ref != ref:
                raise ValueError("identity differs")
            return result
        except ValueError as error:
            raise MethodRegistryError(
                "ARTIFACT_DIGEST_MISMATCH", "stored artifact integrity check failed", 500
            ) from error

    def freeze(self, caller, submission: MethodSubmission):
        method = self.resolve(caller, submission.method_ref)
        descriptor = method.package.descriptor
        if sum(output.required for output in descriptor.output_artifacts.values()) > (
            submission.limits.artifact_count
        ):
            raise MethodRegistryError(
                "INVALID_METHOD_LIMITS",
                "required method outputs exceed artifact_count",
            )
        required = descriptor.requirements
        if required.runtime != self.settings.method_runtime_id or not set(
            required.capabilities
        ) <= set(runtime_capabilities(self.settings)):
            raise MethodRegistryError(
                "ENVIRONMENT_UNAVAILABLE", "required method runtime or capability is unavailable"
            )
        if "process-isolation" in required.capabilities and not self.settings.engine_sandbox_config:
            raise MethodRegistryError(
                "ENVIRONMENT_UNAVAILABLE", "method requires a configured process sandbox"
            )
        try:
            effective = effective_parameters(descriptor.parameters_schema, submission.parameters)
        except ValueError as error:
            raise MethodRegistryError("INVALID_METHOD_PARAMETERS", str(error)) from error
        if submission.inputs.keys() - descriptor.inputs.keys() or any(
            spec.required and name not in submission.inputs
            for name, spec in descriptor.inputs.items()
        ):
            raise MethodRegistryError("INVALID_METHOD_INPUTS", "method input names do not match")
        inputs = {name: self.artifact(caller, ref) for name, ref in submission.inputs.items()}
        for name, artifact in inputs.items():
            media = descriptor.inputs[name].media_type
            if media is not None and artifact.media_type != media:
                raise MethodRegistryError(
                    "INVALID_METHOD_INPUTS", "method input media type differs"
                )
        dependencies = {
            name: self.artifact(caller, ref) for name, ref in descriptor.dependencies.items()
        }
        execution = MethodExecution(
            **method.model_dump(mode="python"),
            requested_parameters=submission.parameters,
            effective_parameters=effective,
            inputs=inputs,
            dependencies=dependencies,
            runtime_id=required.runtime,
            runtime_fingerprint=runtime_fingerprint(self.settings),
            capabilities=runtime_capabilities(self.settings),
            submission=submission,
            limits=submission.limits,
        )
        if len(canonical_json_bytes(execution.model_dump(mode="json"))) > MAX_EXECUTION_BYTES:
            raise MethodRegistryError(
                "METHOD_LIMIT_EXCEEDED", "frozen method request exceeds 8 MiB", 413
            )
        return execution

    def runtimes(self):
        return {
            "contract_version": "custom-method-v1",
            "registry_limits": {
                "max_records_per_caller": self.settings.method_registry_max_records,
                "max_payload_bytes_per_caller": self.settings.method_registry_max_bytes,
                "retention_seconds": self.settings.retention_seconds,
            },
            "runtimes": [
                {
                    "runtime_id": self.settings.method_runtime_id,
                    "capabilities": runtime_capabilities(self.settings),
                    "identity_source": (
                        "deployment-declared; worker validates package/tool requirements"
                    ),
                }
            ],
        }


def runtime_fingerprint(settings):
    """Bind the operator's runtime declaration; child observations are separate."""
    return sha256_hex(
        canonical_json_bytes(
            {
                "id": settings.method_runtime_id,
                "capabilities": runtime_capabilities(settings),
                "toolchain": settings.worker_toolchain_version,
                "runtime": settings.worker_runtime_version,
                "driver": settings.worker_driver_version,
                "hardware": settings.worker_hardware_model,
                "evaluator_build": settings.evaluator_build,
                "sandbox_sha256": settings.engine_sandbox_sha256,
                "runtime_overlay_sha256": settings.engine_runtime_overlay_sha256,
                "profiler_runtime_sha256": settings.profiler_runtime_sha256,
            }
        )
    )


def runtime_capabilities(settings):
    capabilities = set(settings.method_capabilities)
    if not settings.engine_sandbox_config:
        capabilities.discard("process-isolation")
    return sorted(capabilities)
