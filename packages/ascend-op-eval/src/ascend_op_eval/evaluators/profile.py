"""Profile check runner: engine profile_runner for op/deep case profiles.

Profile is independent of the correctness verdict. A single engine invocation
accepts the full selected case set, sharing discovery and orchestration setup.
Raw envelopes are returned unchanged; the shaping boundary validates their
identities and counts before publishing evidence.
Any timeout or failure aborts the whole check as an infrastructure outcome.
"""
import json
import sys
from pathlib import Path

from ascend_op_eval.api.contract import EvaluationRequest, ProfileParams
from ascend_op_eval.evaluators.base import (
    EngineCheckResult,
    LeaseLostError,
    engine_failure,
    engine_timeout,
    input_generation_failure,
    materialize,
    read_json,
    remaining_seconds,
    run_script,
    safe_module_stem,
)

# The engine requires --timeout within [10, 86400].
_MIN_ENGINE_TIMEOUT_SECONDS = 10
_MAX_ENGINE_TIMEOUT_SECONDS = 86400


class ProfileEvaluator:
    def __init__(self, engine_dir: str, *, runner=None):
        self.runner = runner
        self.engine_dir = engine_dir

    def run(
        self,
        request: EvaluationRequest,
        work_dir: Path,
        device_id: int,
        deadline_at,
        lease_valid=None,
        on_checkpoint=None,
    ) -> EngineCheckResult:
        params = request.profile or ProfileParams()
        if params.mode == "trace":
            from ascend_op_eval.evaluators.benchmark import BenchmarkEvaluator

            return BenchmarkEvaluator(self.engine_dir, runner=self.runner).run_trace(
                request, work_dir, device_id, deadline_at, lease_valid
            )
        materialize(request, work_dir)
        indices = params.case_indices
        if indices is not None and not indices:
            return engine_failure("profile", "profile case selection is empty")
        return self._run_once(
            request, params, work_dir, device_id, deadline_at, indices, lease_valid, on_checkpoint
        )

    def _run_once(
        self,
        request: EvaluationRequest,
        params: ProfileParams,
        work_dir: Path,
        device_id: int,
        deadline_at,
        case_indices: list[int] | None,
        lease_valid=None,
        on_checkpoint=None,
    ) -> EngineCheckResult:
        remaining = remaining_seconds(deadline_at)
        if remaining <= 0:
            return engine_timeout(
                "profile", "resource deadline expired before profile ran"
            )
        budget = max(
            _MIN_ENGINE_TIMEOUT_SECONDS,
            min(int(remaining), _MAX_ENGINE_TIMEOUT_SECONDS),
        )
        out_path = Path(work_dir) / "profile_result.json"
        cmd = [
            sys.executable,
            str(Path(self.engine_dir) / "profile_runner.py"),
            "--op_name",
            safe_module_stem(request),
            "--verify_dir",
            str(work_dir),
            "--triton_impl_name",
            request.triton_impl_name,
            "--implementation",
            request.implementation,
            "--profile-mode",
            params.mode,
            "--timeout",
            str(budget),
            "--output",
            str(out_path),
        ]
        native = getattr(request, "native_candidate", None)
        if native is not None:
            if not native.kernel_names:
                return engine_failure(
                    "profile", "native op/deep profiling requires explicit kernel_names",
                    code="INVALID_REQUEST", phase="request", retryable=False,
                )
            cmd.extend([
                "--candidate-kind", "native", "--kernel-names", json.dumps(native.kernel_names),
            ])
        if case_indices is not None:
            cmd.extend(["--case-indices", *(str(index) for index in case_indices)])
        if params.launch_limit is not None:
            cmd.extend(["--launch-count", str(params.launch_limit)])
        if params.metric_groups is not None:
            cmd.extend(["--metric-groups", *params.metric_groups])
        if not params.include_per_core:
            cmd.append("--no-per-core")
        last_file = None

        def poll():
            nonlocal last_file
            if lease_valid is not None and not lease_valid():
                return False
            if on_checkpoint is None:
                return True
            try:
                stat = out_path.lstat()
            except FileNotFoundError:
                return True
            identity = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
            if identity != last_file:
                last_file = identity
                raw = read_json(out_path, root=work_dir)
                if (isinstance(raw, dict) and raw.get("per_case_results")
                        and raw.get("remaining_case_indices")):
                    on_checkpoint(raw)
            return True

        outcome = (self.runner or run_script)(
            cmd, str(work_dir), device_id, deadline_at, poll,
            budget_seconds=budget + 60,
        )
        if outcome.outcome == "fenced":
            raise LeaseLostError("profile engine lost its lease")
        if outcome.timed_out or outcome.exit_code == 124:
            if remaining_seconds(deadline_at) > 0 and not poll():
                raise LeaseLostError("profile checkpoint lost its lease")
            return engine_timeout("profile", "profile exceeded the resource deadline")
        if remaining_seconds(deadline_at) <= 0:
            return engine_timeout("profile", "profile exceeded the resource deadline")
        result = read_json(out_path, root=work_dir)
        if outcome.exit_code == 0 and isinstance(result, dict):
            return EngineCheckResult(status="succeeded", raw=result, error=None)
        return input_generation_failure("profile", outcome) or engine_failure(
            "profile",
            "profile engine produced no usable result"
            f" (engine exit={outcome.exit_code})",
            outcome=outcome,
        )
