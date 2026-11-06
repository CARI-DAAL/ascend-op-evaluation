"""The native hardware gate never treats absent or partial evidence as a pass."""

import copy

import pytest

from scripts.npu_native_gate import validate_resource


def evidence():
    return {
        "state": "completed",
        "result": {
            "provenance": {
                "execution_environment": {
                    "hardware_model": "test-card",
                    "runtime_version": "test-runtime",
                }
            },
            "correctness": {
                "status": "succeeded",
                "data": {
                    "outcome": "correct",
                    "passed": True,
                    "total_cases": 2,
                    "passed_cases": 2,
                },
            },
            "performance": {
                "status": "succeeded",
                "data": {
                    "measurement_method": "native_profiler_kernel_sum_v1",
                    "coverage": 1,
                    "selected_cases": 2,
                    "measured_cases": 2,
                    "per_case": [
                        {
                            "case_idx": 0,
                            "implementation_latency_ms": 0.1,
                            "reference_latency_ms": 0.2,
                        },
                        {
                            "case_idx": 1,
                            "implementation_latency_ms": 0.3,
                            "reference_latency_ms": 0.4,
                        },
                    ],
                },
            },
        },
    }


def test_gate_accepts_complete_native_evidence():
    validate_resource(
        evidence(),
        outcome="correct",
        hardware="test-card",
        runtime="test-runtime",
        performance=True,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(state="timed_out"),
        lambda r: r["result"].pop("performance"),
        lambda r: r["result"]["correctness"]["data"].update(passed_cases=1),
        lambda r: r["result"]["performance"]["data"].update(measurement_method="npu_event_v1"),
        lambda r: r["result"]["performance"]["data"].update(coverage=0.5),
        lambda r: r["result"]["performance"]["data"]["per_case"][0].update(
            implementation_latency_ms=0
        ),
        lambda r: r["result"]["performance"]["data"]["per_case"][0].update(baseline_cache_hit=True),
        lambda r: r["result"]["provenance"]["execution_environment"].update(hardware_model="other"),
    ],
)
def test_gate_rejects_unusable_or_mismatched_evidence(mutation):
    value = copy.deepcopy(evidence())
    mutation(value)
    with pytest.raises(ValueError):
        validate_resource(
            value, outcome="correct", hardware="test-card", runtime="test-runtime", performance=True
        )
