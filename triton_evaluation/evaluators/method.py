"""Custom method check adapter using the ordinary leased engine runner."""

import os
from functools import partial
from pathlib import Path

from ..api.contract import CheckSucceeded
from ..config import Settings, command_environment
from ..methods.contracts import MethodResult
from ..runtime.method_execution import execute_method
from ..runtime.sandbox import CONFIG_ENV
from .base import run_script


class MethodEvaluator:
    def __init__(self, *, runner=None, settings=None):
        self.runner = runner
        self.settings = settings

    def run(
        self,
        request,
        work_dir,
        device_id,
        deadline_at,
        lease_valid,
        *,
        settings=None,
        on_artifacts=None,
    ):
        from ..methods.registry import runtime_fingerprint

        actual = settings or self.settings or Settings.from_env()
        execution = request.method_execution
        runner = self.runner or partial(run_script, environment=command_environment(actual))
        environment = getattr(runner, "keywords", {}).get("environment")
        if environment is None:
            environment = os.environ
        isolation = "sandbox" if environment.get(CONFIG_ENV) else "host"
        required = execution.package.descriptor.requirements
        if (
            execution.runtime_id != actual.method_runtime_id
            or execution.runtime_fingerprint != runtime_fingerprint(actual)
            or not set(required.capabilities) <= set(actual.method_capabilities)
        ):
            data = MethodResult(
                **{
                    key: getattr(execution, key)
                    for key in (
                        "contract_version",
                        "method_ref",
                        "descriptor_sha256",
                        "implementation_sha256",
                        "dependency_digests",
                        "runtime_fingerprint",
                        "requested_parameters",
                        "effective_parameters",
                    )
                },
                kind=execution.package.descriptor.kind,
                isolation=isolation,
                outcome="environment_unavailable",
                error="worker method runtime differs from admission",
            )
        else:
            data = execute_method(
                execution,
                Path(work_dir),
                device_id=device_id,
                deadline_at=deadline_at,
                lease_valid=lease_valid,
                runner=runner,
                artifact_sink=on_artifacts,
                isolation=isolation,
            )
        return CheckSucceeded[MethodResult](status="succeeded", data=data)
