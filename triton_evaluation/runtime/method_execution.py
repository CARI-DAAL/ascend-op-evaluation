"""Private external-method staging, bounded execution and safe output collection."""

from __future__ import annotations

import json
import math
import mimetypes
import os
import stat
import sys
from datetime import datetime
from pathlib import Path

from ..evaluators.base import LeaseLostError, _directory_descriptor, remaining_seconds, run_script
from ..methods.contracts import (
    MAX_BLOB_BYTES,
    MethodArtifact,
    MethodExecution,
    MethodResult,
    StoredArtifact,
)
from ..methods.schemas import validate_value
from .process_title import process_phase

MAX_PROTOCOL_BYTES = 128 * 1024
MAX_OUTPUT_NODES = 1024
PUBLICATION_RESERVE_SECONDS = 1.0


class OutputProtocolError(ValueError):
    pass


def _reject_nonfinite(value):
    raise ValueError("non-finite JSON constant")


def _write_file(root, relative, content):
    path = root / relative
    with _directory_descriptor(path.parent, create=True) as parent:
        fd = os.open(
            path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=parent
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
    return str(path)


def stage_execution(execution, root, deadline_at):
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
    request = {
        "contract_version": execution.contract_version,
        "method_ref": execution.method_ref,
        "package_dir": str(package_dir),
        "entrypoint": descriptor.entrypoint,
        "parameters": execution.effective_parameters,
        "requested_parameters": execution.requested_parameters,
        "inputs": inputs,
        "dependencies": dependencies,
        "requirements": descriptor.requirements.model_dump(mode="json"),
        "output_dir": str(output_dir),
        "scratch_dir": str(scratch),
        "device": "npu:0" if execution.device == "npu" else "cpu",
        "deadline_at": deadline_at.isoformat(),
        "budget_seconds": max(0, remaining_seconds(deadline_at) - PUBLICATION_RESERVE_SECONDS),
    }
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
    """Walk by descriptors; inspect limits before reading or sorting whole trees."""
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
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            relative = prefix + name
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
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

    with _directory_descriptor(directory) as fd:
        visit(fd)
    return output


def read_protocol(root):
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
) -> MethodResult:
    """Execute a frozen method; returned reports remain caller-method claims."""
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
    if required.device == "npu" and device_id is None:
        return MethodResult(
            **identity, outcome="environment_unavailable", error="method requires an assigned NPU"
        )
    if "process-isolation" in required.capabilities and isolation != "sandbox":
        return MethodResult(
            **identity,
            outcome="environment_unavailable",
            error="method requires configured process isolation",
        )
    try:
        request_path, output_dir = stage_execution(execution, work_dir, deadline_at)
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
