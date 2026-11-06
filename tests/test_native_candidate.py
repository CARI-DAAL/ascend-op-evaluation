"""Native project requests preserve identity without executing supplied code."""
import pytest
from pydantic import ValidationError

from triton_evaluation.operator_input import OperatorRequest, to_evaluation_request


def payload(**candidate):
    return {
        "definition": {"inputs": {"x": {}}, "reference": "def run(x): return x"},
        "workloads": [{"inputs": {"x": {"type": "scalar", "value": 1}}}],
        "candidate": {
            "kind": "native", "files": {"entry.py": "def run(x): return x"},
            "build": ["python3", "-c", "pass"], "entrypoint": "entry:run", **candidate,
        },
    }


def test_native_request_preserves_project_identity_and_defaults_to_profiler():
    request = to_evaluation_request(OperatorRequest.model_validate(payload()))
    assert request.implementation == "comparison"
    assert request.native_candidate.entrypoint == "entry:run"
    assert request.performance.method == "profiler"
    assert "_native_candidate = True" in request.kernel_code
    modified = payload(files={"entry.py": "def run(x): return x + 1"})
    other = to_evaluation_request(OperatorRequest.model_validate(modified))
    assert other.kernel_code != request.kernel_code
    assert other.reference_code == request.reference_code


@pytest.mark.parametrize("path", ["../escape.py", "/absolute.py", "a/../b.py", "a\\b.py"])
def test_native_source_paths_cannot_escape(path):
    with pytest.raises(ValidationError):
        OperatorRequest.model_validate(payload(files={path: "pass"}))


def test_native_and_triton_sources_are_exclusive():
    data = payload()
    data["triton_code"] = "def run(x): return x"
    with pytest.raises(ValidationError):
        OperatorRequest.model_validate(data)


def test_native_event_timing_requires_explicit_stream_contract():
    data = payload()
    data["performance"] = {"method": "event"}
    with pytest.raises(ValueError, match="event_timing"):
        to_evaluation_request(OperatorRequest.model_validate(data))
    data["candidate"]["event_timing"] = True
    assert to_evaluation_request(OperatorRequest.model_validate(data)).performance.method == "event"


def test_native_profiler_bound_and_cache_reuse_are_explicit():
    for settings, message in [({"repeats": 101}, "100 repeats"),
                              ({"use_baseline_cache": True}, "baseline_cache")]:
        data = payload()
        data["performance"] = settings
        with pytest.raises(ValueError, match=message):
            to_evaluation_request(OperatorRequest.model_validate(data))
    result = to_evaluation_request(OperatorRequest.model_validate(payload()))
    assert result.performance.repeats == 20
    assert result.performance.use_baseline_cache is False


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan")])
def test_native_tolerance_cannot_be_negative_or_nonfinite(value):
    data = payload()
    data["workloads"][0]["tolerance"] = {"max_atol": value}
    with pytest.raises(ValueError):
        to_evaluation_request(OperatorRequest.model_validate(data))


def test_native_artifacts_are_private_and_bound_to_build(tmp_path):
    import ctypes
    import shutil
    from datetime import datetime, timedelta, timezone

    from triton_evaluation.api.contract import NativeCandidate
    from triton_evaluation.runtime.native_candidate import build_candidate, validate_build

    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("C compiler unavailable")
    builds = []
    for name, increment in [("first", 1), ("second", 7)]:
        work = tmp_path / name
        source = f"int increment(int x) {{ return x + {increment}; }}"
        candidate = NativeCandidate.model_validate(payload(
            files={"entry.py": "def run(x): return x", "op.c": source},
            build=[compiler, "-shared", "-fPIC", "op.c", "-o", "op.so"],
        )["candidate"])
        evidence = build_candidate(candidate, work, device_id=None,
            deadline_at=datetime.now(timezone.utc) + timedelta(seconds=30),
            lease_valid=lambda: True)
        assert evidence.outcome == "compiled"
        validate_build(work / "native_candidate", evidence)
        lib = ctypes.CDLL(str(work / "native_candidate/op.so"))
        assert lib.increment(3) == 3 + increment
        builds.append(evidence)
    assert builds[0].artifact_sha256 != builds[1].artifact_sha256
    replacement = tmp_path / "replacement.so"
    replacement.write_bytes(b"replaced")
    replacement.replace(tmp_path / "first/native_candidate/op.so")
    with pytest.raises(ValueError, match="changed"):
        validate_build(tmp_path / "first/native_candidate", builds[0])


def test_native_failed_build_and_bounded_logs_are_observable(tmp_path):
    import sys
    from datetime import datetime, timedelta, timezone

    from triton_evaluation.api.contract import NativeCandidate
    from triton_evaluation.runtime.native_candidate import build_candidate

    candidate = NativeCandidate.model_validate(payload(build=[sys.executable, "-c",
        "import sys; print('x'*20000); print('compiler diagnostic',file=sys.stderr); sys.exit(3)"
    ])["candidate"])
    result = build_candidate(candidate, tmp_path, device_id=None,
        deadline_at=datetime.now(timezone.utc) + timedelta(seconds=30), lease_valid=lambda: True)
    assert result.outcome == "compile_error"
    assert result.exit_code == 3
    assert "compiler diagnostic" in result.stderr
    assert len(result.stdout.encode()) <= 16384
    assert result.logs_truncated


def test_native_build_timeout_and_lease_are_not_compile_errors(tmp_path):
    import sys
    from datetime import datetime, timedelta, timezone

    from triton_evaluation.api.contract import NativeCandidate
    from triton_evaluation.evaluators.base import LeaseLostError
    from triton_evaluation.runtime.native_candidate import build_candidate

    candidate = NativeCandidate.model_validate(payload(build=[sys.executable, "-c",
        "import time; time.sleep(10)"], build_timeout_seconds=1)["candidate"])
    result = build_candidate(candidate, tmp_path, device_id=None,
        deadline_at=datetime.now(timezone.utc) + timedelta(seconds=30), lease_valid=lambda: True)
    assert result.outcome == "timed_out"
    with pytest.raises(LeaseLostError):
        build_candidate(candidate, tmp_path, device_id=None,
            deadline_at=datetime.now(timezone.utc) + timedelta(seconds=30),
            lease_valid=lambda: False)


def test_native_staging_refuses_symlink_directory(tmp_path):
    from triton_evaluation.api.contract import NativeCandidate
    from triton_evaluation.runtime.native_candidate import stage_project

    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "native_candidate").symlink_to(outside, target_is_directory=True)
    candidate = NativeCandidate.model_validate(payload()["candidate"])
    with pytest.raises(OSError):
        stage_project(candidate, tmp_path)
    assert not (outside / "entry.py").exists()


def test_native_performance_samples_are_bound_to_method_and_mean():
    from triton_evaluation.api.contract import PerformanceCase

    data = dict(case_idx=0, input_shapes=[], implementation_latency_ms=0.02,
                reference_latency_ms=0.03, speedup_vs_reference=1.5,
                measurement_method="native_profiler_kernel_sum_v1",
                implementation_samples_ms=[0.01, 0.03], reference_samples_ms=[0.02, 0.04])
    assert PerformanceCase.model_validate(data).implementation_latency_ms == 0.02
    with pytest.raises(ValidationError, match="mean"):
        PerformanceCase.model_validate({**data, "implementation_latency_ms": 0.04})
    with pytest.raises(ValidationError, match="native sample"):
        PerformanceCase.model_validate({**data, "measurement_method": "npu_event_v1"})
    with pytest.raises(ValidationError, match="fresh"):
        PerformanceCase.model_validate({**data, "baseline_cache_hit": True})


def test_native_wrapper_refuses_preloaded_external_entrypoint(tmp_path):
    import subprocess
    import sys

    from triton_evaluation.api.contract import NativeCandidate
    from triton_evaluation.runtime.native_candidate import candidate_wrapper, stage_project

    candidate = NativeCandidate.model_validate(payload(
        files={"json.py": "def run(x): return x"}, entrypoint="json:run",
    )["candidate"])
    stage_project(candidate, tmp_path)
    wrapper = tmp_path / "wrapper.py"
    wrapper.write_text(candidate_wrapper(candidate))
    result = subprocess.run([sys.executable, "-c", "import json; import wrapper"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert "native entry module resolved outside the project" in result.stderr


def test_native_digest_rejects_fifo_replacement_without_blocking(tmp_path):
    import subprocess
    import sys
    import textwrap

    root = tmp_path / "tree"
    root.mkdir()
    (root / "victim").write_text("old")
    script = textwrap.dedent('''
        import os, sys
        from pathlib import Path
        from triton_evaluation.runtime.native_candidate import project_digest
        root = Path(sys.argv[1])
        real_open = os.open
        def swap(path, flags, *args, **kwargs):
            if path == 'victim':
                (root / 'victim').unlink()
                os.mkfifo(root / 'victim')
            return real_open(path, flags, *args, **kwargs)
        os.open = swap
        try:
            project_digest(root)
        except ValueError:
            print('rejected nonregular replacement')
        else:
            raise AssertionError('accepted FIFO')
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(root)],
                            capture_output=True, text=True, timeout=3)
    assert result.returncode == 0, result.stderr
    assert "rejected nonregular" in result.stdout


def test_native_digest_checks_opened_size_before_reading(tmp_path, monkeypatch):
    import os

    from triton_evaluation.runtime.native_candidate import project_digest

    path = tmp_path / "victim"
    path.write_text("old")
    real_open, real_read = os.open, os.read

    def swap(name, flags, *args, **kwargs):
        if name == "victim":
            with path.open("wb") as stream:
                stream.truncate(512 * 1024 * 1024 + 1)
        return real_open(name, flags, *args, **kwargs)

    def read(fd, count):
        if os.fstat(fd).st_size > 512 * 1024 * 1024:
            pytest.fail("oversized replacement was read before rejecting its opened size")
        return real_read(fd, count)

    monkeypatch.setattr(os, "open", swap)
    monkeypatch.setattr(os, "read", read)
    with pytest.raises(ValueError, match="limits"):
        project_digest(tmp_path)


def test_native_digest_bounds_directory_enumeration(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from triton_evaluation.runtime import native_candidate

    class TooManyEntries:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def __iter__(self):
            for i in range(8194):
                if i == 8193:
                    pytest.fail("directory enumerated beyond the allowed tree budget")
                yield SimpleNamespace(name=f"entry-{i}")

    monkeypatch.setattr(native_candidate.os, "scandir", lambda *_args: TooManyEntries())
    with pytest.raises(ValueError, match="8192"):
        native_candidate.project_digest(tmp_path)


@pytest.mark.parametrize("change", ["add", "remove"])
def test_native_artifact_identity_includes_empty_directories(tmp_path, change):
    from triton_evaluation.api.contract import NativeBuildEvidence
    from triton_evaluation.runtime.native_candidate import project_digest, validate_build

    (tmp_path / "entry.py").write_text("def run(x): return x\n")
    directory = tmp_path / "optional-feature"
    if change == "remove":
        directory.mkdir()
    evidence = NativeBuildEvidence(
        outcome="compiled", duration_ms=0, artifact_sha256=project_digest(tmp_path),
    )
    if change == "add":
        directory.mkdir()
    else:
        directory.rmdir()
    with pytest.raises(ValueError, match="changed"):
        validate_build(tmp_path, evidence)


def test_native_directory_entries_do_not_consume_file_budget(tmp_path):
    from triton_evaluation.runtime.native_candidate import project_digest

    for index in range(4096):
        (tmp_path / f"directory-{index:04d}").mkdir()
    (tmp_path / "entry.py").write_text("def run(x): return x\n")
    assert len(project_digest(tmp_path)) == 64
