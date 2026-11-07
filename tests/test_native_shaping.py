"""Native numerical policy identity survives the engine-to-API projection."""

import json
from pathlib import Path

import pytest
from ascend_op_eval.evaluators.shaping import (
    ShapingError,
    shape_correctness,
    shape_performance,
)


def correct_payload():
    path = Path(__file__).parent / "fixtures" / "engine" / "verify-correct.json"
    return json.loads(path.read_text())


def test_native_comparison_method_is_preserved():
    raw = correct_payload()
    raw["comparison_method"] = "native_tensor_v1"
    result = shape_correctness(raw, decoy=False)
    assert result.model_dump(mode="json")["comparison_method"] == "native_tensor_v1"


def test_legacy_correctness_does_not_gain_native_method():
    result = shape_correctness(correct_payload(), decoy=False)
    assert "comparison_method" not in result.model_dump(mode="json")


def test_unknown_comparison_method_is_not_accepted():
    raw = correct_payload()
    raw["comparison_method"] = "unrecognized"
    with pytest.raises(ShapingError):
        shape_correctness(raw, decoy=False)


def test_native_explicit_mismatch_is_a_wrong_verdict():
    path = Path(__file__).parent / "fixtures" / "engine" / "verify-wrong-value.json"
    raw = json.loads(path.read_text())
    raw["comparison_method"] = "native_tensor_v1"
    for failure in raw["failures"]:
        failure["kind"] = "value_mismatch"
    result = shape_correctness(raw, decoy=False)
    assert result.outcome == "wrong"
    assert all(f.kind == "value_mismatch" for f in result.failures)


def native_timing_payload():
    path = Path(__file__).parent / "fixtures" / "engine" / "benchmark-event-timing.json"
    raw = json.loads(path.read_text())
    raw["repeats"] = 2
    raw["measurement_method"] = "native_profiler_kernel_sum_v1"
    for case in raw["per_shape_results"]:
        case["measurement_method"] = "native_profiler_kernel_sum_v1"
    first, second = raw["per_shape_results"][:2]
    first["framework"]["measurement_samples_ms"] = [0.5, 1.5]
    second["framework"]["measurement_samples_ms"] = [0.5, 1.5]
    first["implementation"]["measurement_samples_ms"] = [0.25, 0.75]
    second["implementation"]["measurement_samples_ms"] = [1.0, 3.0]
    return raw


def test_native_raw_timing_samples_survive_projection():
    result = shape_performance(native_timing_payload())
    first = result.model_dump(mode="json")["per_case"][0]
    assert first["implementation_samples_ms"] == [0.25, 0.75]
    assert first["reference_samples_ms"] == [0.5, 1.5]


def test_native_timing_cannot_claim_latency_unrelated_to_samples():
    raw = native_timing_payload()
    raw["per_shape_results"][0]["implementation"]["measurement_samples_ms"] = [2.0, 3.0]
    with pytest.raises(ShapingError):
        shape_performance(raw)


@pytest.mark.parametrize("method,expected", [
    ("profiler_kernel_sum_v1", "failed"),
    ("native_profiler_kernel_sum_v1", "succeeded"),
])
def test_native_trace_rejects_a_different_measurement_protocol(tmp_path, method, expected):
    import sys
    from datetime import datetime, timedelta, timezone

    from ascend_op_eval.evaluators.base import EngineCheckResult
    from ascend_op_eval.operator_input import OperatorRequest, to_evaluation_request
    from test_evaluation_evaluator import (
        ENVIRONMENT,
        Harness,
        RecordingSink,
        StubCheck,
        trial_pinned,
    )

    request = to_evaluation_request(OperatorRequest.model_validate({
        "definition": {"inputs": {}, "reference": "def run(): return 1"},
        "workloads": [{"inputs": {}}],
        "candidate": {"files": {"entry.py": "def run(): return 1"},
                      "build": [sys.executable, "-c", "pass"], "entrypoint": "entry:run"},
        "checks": ["profile"], "profile": {"mode": "trace"},
    }))
    raw = {
        "mode": "trace", "measurement_method": method, "total_cases": 1,
        "counts": {"selected": 1, "complete": 1, "partial": 0, "failed": 0},
        "cases": [{"case_idx": 0, "status": "complete", "kernels": [
            {"op_name": "native", "time_ms": 1.0, "percentage": 100.0},
        ]}],
    }
    harness = Harness(None, profile=StubCheck(EngineCheckResult(status="succeeded", raw=raw)))
    result = harness.run(request, tmp_path, 0, datetime.now(timezone.utc) + timedelta(minutes=1),
                         lambda: True, ENVIRONMENT, trial_pinned(), RecordingSink())
    assert result.profile.status == expected
    if expected == "failed":
        assert result.profile.error.code == "INVALID_ENGINE_OUTPUT"
