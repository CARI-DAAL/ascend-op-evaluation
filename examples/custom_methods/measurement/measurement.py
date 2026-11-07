"""Aggregate explicit invocation/launch observations, never infer boundaries by name."""

import json
import math
import statistics
from pathlib import Path


def run(request):
    source = json.loads(Path(request["inputs"]["launches"]["path"]).read_text())
    invocations = source["invocations"]
    if not isinstance(invocations, list) or not invocations:
        raise ValueError("at least one invocation is required")
    totals, per_kernel = [], {}
    for invocation in invocations:
        grouped = {}
        for launch in invocation["launches"]:
            role = launch.get("role", "target")
            if role not in {"preparation", "warmup", "target"}:
                raise ValueError("unknown launch role")
            value = launch["duration_us"]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("invalid duration")
            if role != "target":
                continue
            name = launch["name"]
            if not isinstance(name, str) or not name:
                raise ValueError("target launch needs a name")
            grouped[name] = grouped.get(name, 0.0) + value
        totals.append(sum(grouped.values()))
        for name, value in grouped.items():
            per_kernel.setdefault(name, []).append(value)
    method = request["parameters"]["aggregation"]
    if method == "mean_call_total":
        value = statistics.mean(totals)
    elif method == "median_call_total":
        value = statistics.median(totals)
    elif method == "sum_kernel_medians":
        # Conditional absence is excluded from that kernel's distribution.
        # This is explicit method semantics, not a universal timing default.
        value = sum(statistics.median(samples) for samples in per_kernel.values())
    else:
        raise ValueError("unknown aggregation")
    report = {
        "metric": "observed_kernel_duration",
        "unit": "us",
        "value": value,
        "samples": totals,
        "aggregation": method,
        "per_kernel_samples": per_kernel,
        "evidence_scope": "aggregation of supplied observations; not a device measurement",
    }
    Path(request["output_dir"], "aggregation.json").write_text(json.dumps(report, allow_nan=False))
    Path(request["output_dir"], "launches.json").write_text(json.dumps(source, allow_nan=False))
    return report
