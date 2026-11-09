"""Private external-method staging, bounded execution and safe output collection."""

from __future__ import annotations

import hashlib
import json
import math
import mimetypes
import os
import stat
import sys
import time
from datetime import datetime
from pathlib import Path

from ascend_op_eval.execution.process_title import process_phase
from ascend_op_eval.methods.contracts import (
    MAX_BLOB_BYTES,
    HandoffFile,
    MethodArtifact,
    MethodExecution,
    MethodResult,
    MethodStageRecord,
    StoredArtifact,
    safe_path,
)
from ascend_op_eval.methods.schemas import validate_value

MAX_PROTOCOL_BYTES = 128 * 1024
MAX_OUTPUT_NODES = 1024
PUBLICATION_RESERVE_SECONDS = 1.0
# Stage handoff carries built data (wheels), not method code: it bypasses the
# 1 MiB artifact store and goes through the worker-shared stage spool.
MAX_HANDOFF_BYTES = 256 * 1024 * 1024
MAX_HANDOFF_FILES = 32


class OutputProtocolError(ValueError):
    pass


def _reject_nonfinite(value):
    raise ValueError("non-finite JSON constant")


def _write_file(root, relative, content):
    from ascend_op_eval.evaluators.base import _directory_descriptor

    path = root / relative
    with _directory_descriptor(path.parent, create=True) as parent:
        fd = os.open(
            path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=parent
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
    return str(path)


def stage_execution(execution, root, deadline_at, stage_index=0, handoff=None):
    from ascend_op_eval.evaluators.base import remaining_seconds

    package_dir, output_dir = root / "package", root / "outputs"
    scratch = root / "scratch"
    for directory in (package_dir, output_dir, scratch):
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, source in execution.package.files.items():
        _write_file(package_dir, name, source.encode("utf-8"))
    inputs, dependencies = {}, {}
    for label, artifacts, destination in (
        ("inputs", execution.inputs, inputs),
        ("dependencies", execution.dependencies, dependencies),
    ):
        for name, artifact in artifacts.items():
            # Revalidate bytes and content identity, not only the previously
            # admitted reference; model_copy() must not bypass these checks.
            artifact = StoredArtifact.model_validate(artifact.model_dump())
            content = artifact.content()
            if artifact.media_type.split(";", 1)[0].strip() == "application/json":
                try:
                    json.loads(content, parse_constant=_reject_nonfinite)
                except (ValueError, UnicodeError, RecursionError) as error:
                    raise OutputProtocolError("declared JSON input is invalid") from error
            path = _write_file(root, f"{label}/{name}", content)
            destination[name] = {
                "path": path,
                "sha256": artifact.sha256,
                "media_type": artifact.media_type,
            }
    descriptor = execution.package.descriptor
    plan = descriptor.stage_plan
    stage = plan[stage_index]
    request = {
        "contract_version": execution.contract_version,
        "method_ref": execution.method_ref,
        "package_dir": str(package_dir),
        "entrypoint": stage.entrypoint,
        "parameters": execution.effective_parameters,
        "requested_parameters": execution.requested_parameters,
        "inputs": inputs,
        "dependencies": dependencies,
        "requirements": descriptor.requirements.model_dump(mode="json"),
        "output_dir": str(output_dir),
        "scratch_dir": str(scratch),
        "device": "npu:0" if stage.device == "npu" else "cpu",
        "deadline_at": deadline_at.isoformat(),
        "budget_seconds": max(0, remaining_seconds(deadline_at) - PUBLICATION_RESERVE_SECONDS),
    }
    if descriptor.stages is not None:
        request["stage"] = {"index": stage_index, "count": len(plan)}
        request["handoff"] = handoff or {}
        if stage_index < len(plan) - 1:
            (root / "handoff").mkdir(mode=0o700)
            request["handoff_dir"] = str(root / "handoff")
    request_path = Path(
        _write_file(root, "request.json", json.dumps(request, allow_nan=False).encode())
    )
    # Files are staged read-only to catch accidental writes. Keep directories
    # owner-writable for reliable cleanup; same-UID permissions are not a judge
    # isolation boundary and user code could chmod its own files either way.
    return request_path, output_dir


def _read_regular(parent_fd, name, maximum):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise OutputProtocolError("method output is not a bounded regular file")
        chunks, remaining = [], before.st_size
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                raise OutputProtocolError("method output changed while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise OutputProtocolError("method output changed while reading")
        return b"".join(chunks)
    finally:
        os.close(fd)


def collect_outputs(directory, limits, *, read=True):
    """Walk bounded outputs; live probes tolerate vanished atomic-write entries.

    Only ENOENT is transient while the method is running. Final collection is
    strict, and links, special files, invalid sizes and other errors always fail.
    """
    from ascend_op_eval.evaluators.base import _directory_descriptor

    output = {}
    count = nodes = total = 0

    def visit(fd, prefix="", depth=0):
        nonlocal count, nodes, total
        if depth > 16:
            raise OutputProtocolError("method output directory depth exceeded")
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                nodes += 1
                if nodes > MAX_OUTPUT_NODES:
                    raise OutputProtocolError("method output directory count exceeded")
                names.append(entry.name)
        for name in sorted(names):
            try:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                if read:
                    raise
                continue
            relative = prefix + name
            if stat.S_ISDIR(info.st_mode):
                try:
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    if read:
                        raise
                    continue
                try:
                    visit(child, relative + "/", depth + 1)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                count += 1
                total += info.st_size
                if count > limits.artifact_count:
                    raise OutputProtocolError("method artifact count budget exceeded")
                if info.st_size > MAX_BLOB_BYTES or total > limits.artifact_bytes:
                    raise OutputProtocolError("method artifact byte budget exceeded")
                if read:
                    # Opened-file size is checked independently of the lstat.
                    content = _read_regular(
                        fd,
                        name,
                        min(MAX_BLOB_BYTES, limits.artifact_bytes - (total - info.st_size)),
                    )
                    if len(content) != info.st_size:
                        raise OutputProtocolError("method output changed during collection")
                    output[relative] = StoredArtifact.from_bytes(
                        content,
                        mimetypes.guess_type(name)[0] or "application/octet-stream",
                    )
            else:
                raise OutputProtocolError("method outputs must be regular files or directories")

    try:
        with _directory_descriptor(directory) as fd:
            visit(fd)
    except FileNotFoundError:
        if read:
            raise
        # A producer can atomically replace a whole output directory as well.
        # Nothing is published from this live budget probe; final collection
        # must still inspect every declared output after execution stops.
    return output


def read_protocol(root):
    from ascend_op_eval.evaluators.base import _directory_descriptor

    try:
        with _directory_descriptor(root) as fd:
            payload = json.loads(_read_regular(fd, "result.json", MAX_PROTOCOL_BYTES))
    except (OSError, ValueError) as error:
        raise OutputProtocolError("method produced no valid protocol report") from error
    if (
        not isinstance(payload, dict)
        or payload.get("protocol") != "custom-method-result-v1"
        or payload.get("outcome")
        not in {
            "completed",
            "method_error",
            "protocol_error",
            "environment_unavailable",
        }
    ):
        raise OutputProtocolError("method result protocol is invalid")
    return payload


def validate_report(descriptor, report):
    validate_value(descriptor.output_schema, report, label="report")
    if descriptor.kind == "checker":
        if type(report.get("passed")) is not bool:
            raise OutputProtocolError("checker report requires passed boolean")
        return "passed" if report["passed"] else "failed"
    if descriptor.kind == "measurement":
        if any(
            not isinstance(report.get(key), str) or not report[key]
            for key in ("metric", "unit", "aggregation")
        ):
            raise OutputProtocolError("measurement report requires metric, unit and aggregation")
        values = [report.get("value")]
        samples = report.get("samples")
        if not isinstance(samples, list) or not samples:
            raise OutputProtocolError("measurement report requires nonempty samples")
        values += samples
        if any(
            type(value) not in (float, int) or not math.isfinite(value) or value < 0
            for value in values
        ):
            raise OutputProtocolError(
                "measurement values and samples must be finite nonnegative numbers"
            )
    return "completed"


def _logs(stdout, stderr, budget):
    out, err = stdout.encode("utf-8"), stderr.encode("utf-8")
    err_budget = min(len(err), budget if not out else budget // 2)
    out_budget = min(len(out), budget - err_budget)
    err_budget = min(len(err), budget - out_budget)
    return (
        out[-out_budget:].decode("utf-8", "ignore") if out_budget else "",
        err[-err_budget:].decode("utf-8", "ignore") if err_budget else "",
        len(out) + len(err) > budget,
    )


def _copy_into(source: Path, target: Path, limit: int) -> tuple[str, int]:
    """Stream one no-follow regular file into a new target; return digest and size."""
    digest, size = hashlib.sha256(), 0
    with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW), "rb") as reader:
        if not stat.S_ISREG(os.fstat(reader.fileno()).st_mode):
            raise OutputProtocolError("stage handoff entry is not a regular file")
        with target.open("xb") as writer:
            while chunk := reader.read(1 << 20):
                size += len(chunk)
                if size > limit:
                    raise OutputProtocolError("stage handoff byte budget exceeded")
                digest.update(chunk)
                writer.write(chunk)
    return digest.hexdigest(), size


def spool_handoff(directory: Path, spool_dir: Path) -> dict[str, HandoffFile]:
    """Content-address every file a stage left in its handoff directory."""
    spool_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    handoff, total = {}, 0
    for root, directories, names in os.walk(directory):
        for name in directories + names:
            mode = os.lstat(os.path.join(root, name)).st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise OutputProtocolError(
                    "stage handoff must hold only regular files and directories"
                )
        for name in sorted(names):
            relative = safe_path(Path(root, name).relative_to(directory).as_posix())
            if len(handoff) >= MAX_HANDOFF_FILES:
                raise OutputProtocolError("stage handoff file count exceeded")
            partial = spool_dir / f".{os.getpid()}.{time.monotonic_ns()}.partial"
            try:
                digest, size = _copy_into(
                    Path(root, name), partial, MAX_HANDOFF_BYTES - total
                )
                os.replace(partial, spool_dir / digest)
            finally:
                partial.unlink(missing_ok=True)
            total += size
            handoff[relative] = HandoffFile(sha256=digest, size_bytes=size)
    return handoff


def restore_handoff(handoff: dict, spool_dir: Path, destination: Path) -> dict:
    """Copy the previous stage's spooled files in, verifying recorded digests."""
    staged = {}
    for name, item in handoff.items():
        target = destination / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        digest, size = _copy_into(spool_dir / item.sha256, target, item.size_bytes)
        if (digest, size) != (item.sha256, item.size_bytes):
            raise OutputProtocolError("stage handoff differs from its recorded digest")
        target.chmod(0o400)
        staged[name] = {"path": str(target), "sha256": digest, "size_bytes": size}
    return staged


def execute_method(
    execution: MethodExecution,
    work_dir: Path,
    *,
    device_id,
    deadline_at: datetime,
    lease_valid,
    runner=None,
    artifact_sink=None,
    isolation="host",
    stage_records=(),
    spool_dir: Path | None = None,
) -> MethodResult:
    """Execute a frozen method's next stage; reports remain caller-method claims.

    ``stage_records`` are the already completed stages of a staged method.
    A non-final stage that leaves handoff files returns ``completed`` with a
    nonempty ``handoff`` record, telling the worker to queue the next stage.
    """
    stage_index = len(stage_records)
    handoff: dict[str, HandoffFile] = {}
    started = time.monotonic()
    result = _execute_stage(
        execution, work_dir, device_id=device_id, deadline_at=deadline_at,
        lease_valid=lease_valid, runner=runner, artifact_sink=artifact_sink,
        isolation=isolation, stage_index=stage_index,
        handoff_in=stage_records[-1].handoff if stage_records else {},
        spool_dir=spool_dir, handoff_out=handoff,
    )
    stages = execution.package.descriptor.stages
    if stages is None:
        return result
    record = MethodStageRecord(
        index=stage_index,
        device=stages[stage_index].device,
        entrypoint=stages[stage_index].entrypoint,
        outcome=result.outcome,
        duration_ms=int((time.monotonic() - started) * 1000),
        handoff=handoff,
        error=result.error,
    )
    return result.model_copy(update={"stages": [*stage_records, record]})


def _execute_stage(
    execution: MethodExecution,
    work_dir: Path,
    *,
    device_id,
    deadline_at: datetime,
    lease_valid,
    runner,
    artifact_sink,
    isolation,
    stage_index,
    handoff_in,
    spool_dir,
    handoff_out,
) -> MethodResult:
    from ascend_op_eval.evaluators.base import LeaseLostError, remaining_seconds, run_script

    execution = MethodExecution.model_validate(execution.model_dump(mode="json"))
    identity = {
        name: getattr(execution, name)
        for name in (
            "contract_version",
            "method_ref",
            "descriptor_sha256",
            "implementation_sha256",
            "dependency_digests",
            "runtime_fingerprint",
            "requested_parameters",
            "effective_parameters",
        )
    }
    identity.update(kind=execution.package.descriptor.kind, isolation=isolation)
    if not lease_valid():
        raise LeaseLostError("method lost lease before staging")
    required = execution.package.descriptor.requirements
    stages = execution.package.descriptor.stage_plan
    final = stage_index == len(stages) - 1
    if stages[stage_index].device == "npu" and device_id is None:
        return MethodResult(
            **identity, outcome="environment_unavailable", error="method requires an assigned NPU"
        )
    if execution.package.descriptor.stages is not None and spool_dir is None:
        return MethodResult(
            **identity,
            outcome="environment_unavailable",
            error="staged method requires a configured stage spool",
        )
    if "process-isolation" in required.capabilities and isolation != "sandbox":
        return MethodResult(
            **identity,
            outcome="environment_unavailable",
            error="method requires configured process isolation",
        )
    try:
        handoff = restore_handoff(handoff_in, spool_dir, work_dir / "handoff_in")
    except (OSError, ValueError):
        return MethodResult(
            **identity,
            outcome="environment_unavailable",
            error="stage handoff is missing or corrupt in the stage spool",
        )
    try:
        request_path, output_dir = stage_execution(
            execution, work_dir, deadline_at, stage_index, handoff
        )
    except (OSError, ValueError) as error:
        return MethodResult(**identity, outcome="protocol_error", error=str(error)[:512])
    result_path = work_dir / "result.json"

    def output_guard():
        collect_outputs(output_dir, execution.limits, read=False)
        try:
            info = result_path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_PROTOCOL_BYTES:
            raise OutputProtocolError("method protocol output is invalid or oversized")

    try:
        with process_phase("method"):
            process = (runner or run_script)(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "engine/method_runner.py"),
                    str(request_path),
                    str(result_path),
                ],
                work_dir,
                device_id,
                deadline_at,
                lease_valid,
                budget_seconds=max(0, remaining_seconds(deadline_at) - PUBLICATION_RESERVE_SECONDS),
                output_limit_bytes=execution.limits.log_bytes,
                max_log_bytes=execution.limits.log_bytes,
                resource_guard=output_guard,
            )
    except OSError as error:
        return MethodResult(
            **identity,
            outcome="environment_unavailable",
            error=f"method runtime could not start: {type(error).__name__}",
        )
    if process.outcome == "fenced" or not lease_valid():
        raise LeaseLostError("method lost its attempt lease")
    stdout, stderr, truncated = _logs(process.stdout, process.stderr, execution.limits.log_bytes)
    common = dict(
        identity,
        stdout=stdout,
        stderr=stderr,
        logs_truncated=truncated or process.logs_truncated,
        exit_code=process.exit_code,
    )
    if process.timed_out or remaining_seconds(deadline_at) <= 0:
        return MethodResult(
            **common, outcome="timed_out", error="method execution exceeded deadline"
        )
    if process.outcome in {"resource_limit", "output_limit"}:
        return MethodResult(
            **common,
            outcome="protocol_error",
            error=process.resource_error or "method output resource limit exceeded",
        )
    try:
        artifacts = collect_outputs(output_dir, execution.limits)
        for name, specification in execution.package.descriptor.output_artifacts.items():
            if name in artifacts and specification.media_type is not None:
                artifacts[name] = artifacts[name].model_copy(
                    update={"media_type": specification.media_type}
                )
        metadata = [
            MethodArtifact(
                name=name,
                sha256=item.sha256,
                size_bytes=item.size_bytes,
                media_type=item.media_type,
            )
            for name, item in artifacts.items()
        ]
        if artifact_sink is not None:
            artifact_sink(artifacts)
        common["artifacts"] = metadata
        if process.exit_code != 0:
            return MethodResult(
                **common,
                outcome="method_error",
                error=f"method process exited with status {process.exit_code}",
            )
        payload = read_protocol(work_dir)
        outcome = payload["outcome"]
        if outcome != "completed":
            return MethodResult(
                **common, outcome=outcome, error=str(payload.get("error") or outcome)[:512]
            )
        if not final:
            # Empty handoff ends the evaluation here (for example, a failed
            # build); its report is then validated as the final report below.
            try:
                files = spool_handoff(work_dir / "handoff", spool_dir)
            except OSError as error:
                return MethodResult(
                    **common,
                    outcome="environment_unavailable",
                    error=f"stage spool write failed: {type(error).__name__}",
                )
            if files:
                if not isinstance(payload.get("report"), dict):
                    raise OutputProtocolError("method report must be an object")
                handoff_out.update(files)
                return MethodResult(
                    **common,
                    outcome="completed",
                    report=payload["report"],
                    runtime_observation=payload.get("runtime_observation", {}),
                )
        for name, specification in execution.package.descriptor.output_artifacts.items():
            if specification.required and name not in artifacts:
                raise OutputProtocolError(f"missing declared method artifact: {name}")
        report = payload.get("report")
        if not isinstance(report, dict):
            raise OutputProtocolError("method report must be an object")
        outcome = validate_report(execution.package.descriptor, report)
        return MethodResult(
            **common,
            outcome=outcome,
            report=report,
            runtime_observation=payload.get("runtime_observation", {}),
        )
    except LeaseLostError:
        raise
    except (OSError, ValueError) as error:
        return MethodResult(**common, outcome="protocol_error", error=str(error)[:512])
