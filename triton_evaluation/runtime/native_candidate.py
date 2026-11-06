"""Private native-source staging and a bounded attempt-owned build.

This module never imports candidate code in the service process. The entrypoint
wrapper executes only inside the ordinary engine subprocess.
"""
import hashlib
import os
import stat
import time
import uuid
from pathlib import Path

from ..api.contract import NativeBuildEvidence, NativeCandidate
from ..serialization import canonical_json_bytes, sha256_hex

PROJECT_DIRECTORY = "native_candidate"
BUILD_LOG_BYTES = 16 * 1024


def candidate_wrapper(candidate: NativeCandidate) -> str:
    digest = sha256_hex(canonical_json_bytes(candidate.model_dump(mode="json")))
    module, function = candidate.entrypoint.split(":")
    return f'''# native project identity: {digest}
import importlib as _native_importlib
import os as _native_os
from pathlib import Path as _NativePath
import sys as _native_sys
import torch as _native_torch

_native_root = str(_NativePath(__file__).resolve().parent / {PROJECT_DIRECTORY!r})
_native_sys.dont_write_bytecode = True
_native_sys.path.insert(0, _native_root)
_native_previous = _native_os.getcwd()
try:
    _native_os.chdir(_native_root)
    _native_module = _native_importlib.import_module({module!r})
    _native_location = getattr(_native_module, "__file__", None)
    if (_native_location is None or not _NativePath(_native_location).resolve().is_relative_to(
            _NativePath(_native_root).resolve())):
        raise ImportError("native entry module resolved outside the project")
    _native_run = getattr(_native_module, {function!r})
    if not callable(_native_run):
        raise TypeError("native entrypoint is not callable")
finally:
    _native_os.chdir(_native_previous)

class ModelNew(_native_torch.nn.Module):
    _native_candidate = True
    _native_event_timing = {candidate.event_timing!r}
    _native_kernel_names = {tuple(candidate.kernel_names or [])!r}

    def forward(self, *args):
        previous = _native_os.getcwd()
        try:
            _native_os.chdir(_native_root)
            return _native_run(*args)
        finally:
            _native_os.chdir(previous)
'''


def stage_project(candidate: NativeCandidate, work_dir: Path) -> Path:
    """Replace source entries without traversing candidate-created symlinks."""
    from ..evaluators.base import _directory_descriptor

    root = Path(work_dir) / PROJECT_DIRECTORY
    for name, source in candidate.files.items():
        path = root / name
        with _directory_descriptor(path.parent, create=True) as parent_fd:
            temporary = f".native-{uuid.uuid4().hex}"
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent_fd)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(source)
                os.replace(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
    return root


def _tail(value: str) -> str:
    return value.encode("utf-8")[-BUILD_LOG_BYTES:].decode("utf-8", errors="ignore")


def build_candidate(candidate: NativeCandidate, work_dir: Path, *, device_id,
                    deadline_at, lease_valid, runner=None) -> NativeBuildEvidence:
    from ..evaluators.base import LeaseLostError, run_script

    if not lease_valid():
        raise LeaseLostError("native build lost its attempt lease")
    root = stage_project(candidate, work_dir)
    started = time.monotonic()
    try:
        result = (runner or run_script)(
            candidate.build, root, device_id, deadline_at, lease_valid,
            budget_seconds=candidate.build_timeout_seconds, output_limit_bytes=BUILD_LOG_BYTES,
        )
    except OSError as error:
        # Missing compiler / loader / permission is environment evidence, not
        # proof that the submitted source is invalid.
        return NativeBuildEvidence(
            outcome="infrastructure_error", duration_ms=(time.monotonic() - started) * 1000,
            stderr=_tail(f"native build could not start: {type(error).__name__}"),
        )
    if result.outcome == "fenced" or not lease_valid():
        raise LeaseLostError("native build lost its attempt lease")
    status = (
        "timed_out" if result.timed_out else
        "compiled" if result.exit_code == 0 else "compile_error"
    )
    artifact_digest = None
    if status == "compiled":
        try:
            artifact_digest = project_digest(root)
        except (OSError, ValueError):
            status = "infrastructure_error"
    return NativeBuildEvidence(
        outcome=status, exit_code=result.exit_code, artifact_sha256=artifact_digest,
        duration_ms=(time.monotonic() - started) * 1000,
        stdout=_tail(result.stdout), stderr=_tail(result.stderr),
        logs_truncated=(result.logs_truncated
                        or len(result.stdout.encode("utf-8")) > BUILD_LOG_BYTES
                        or len(result.stderr.encode("utf-8")) > BUILD_LOG_BYTES),
    )


class NativeArtifactChanged(ValueError):
    """The build tree no longer matches the host-recorded completed build."""


def project_digest(root: Path) -> str:
    """Hash regular build outputs without following links or trusting a manifest.

    The first native contract permits regular files/directories only, with at
    most 4096 files and 512 MiB. These bounds keep host verification finite.
    """
    from ..evaluators.base import _directory_descriptor

    entries = []
    total = 0
    nodes = 0
    files = 0

    def collect(directory_fd, prefix=""):
        nonlocal total, nodes, files
        if prefix.count("/") > 32:
            raise ValueError("native artifact directory nesting exceeds 32")
        names = []
        with os.scandir(directory_fd) as directory:
            for entry in directory:
                nodes += 1
                if nodes > 8192:
                    raise ValueError("native artifact tree exceeds 8192 entries")
                names.append(entry.name)
        for name in sorted(names):
            path = prefix + name
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                entries.append((path, "directory"))
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=directory_fd)
                try:
                    collect(fd, path + "/")
                finally:
                    os.close(fd)
            elif stat.S_ISREG(info.st_mode):
                if files >= 4096 or total + info.st_size > 512 * 1024 * 1024:
                    raise ValueError("native build artifact limits exceeded")
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory_fd)
                digest = hashlib.sha256()
                try:
                    before = os.fstat(fd)
                    if not stat.S_ISREG(before.st_mode):
                        raise ValueError("native artifact is not a regular file")
                    if total + before.st_size > 512 * 1024 * 1024:
                        raise ValueError("native build artifact limits exceeded")
                    remaining = before.st_size
                    while remaining:
                        chunk = os.read(fd, min(65536, remaining))
                        if not chunk:
                            raise ValueError("native artifact changed during collection")
                        digest.update(chunk)
                        remaining -= len(chunk)
                    after = os.fstat(fd)
                    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                        after.st_size, after.st_mtime_ns, after.st_ctime_ns
                    ):
                        raise ValueError("native artifact changed during collection")
                    total += before.st_size
                    files += 1
                    entries.append((path, "file", before.st_mode & 0o111, digest.hexdigest()))
                finally:
                    os.close(fd)
            else:
                raise ValueError("native artifacts must be regular files or directories")

    with _directory_descriptor(root) as root_fd:
        collect(root_fd)
    return sha256_hex(canonical_json_bytes(entries))


def validate_build(candidate_root: Path, evidence: NativeBuildEvidence) -> None:
    try:
        digest = project_digest(candidate_root)
    except (OSError, ValueError) as error:
        raise NativeArtifactChanged("native build outputs changed or became invalid") from error
    if digest != evidence.artifact_sha256:
        raise NativeArtifactChanged("native build outputs changed after compilation")
