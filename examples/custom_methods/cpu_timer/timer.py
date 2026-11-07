"""Measure a bundled CPU callable; this is wall time, not NPU kernel latency."""

import json
import statistics
from pathlib import Path
from time import perf_counter_ns

from . import target


def run(request):
    parameters = request["parameters"]
    for _ in range(parameters["warmup"]):
        target.work(parameters["iterations"])
    samples = []
    checksum = None
    for _ in range(parameters["repeat"]):
        started = perf_counter_ns()
        checksum = target.work(parameters["iterations"])
        samples.append(perf_counter_ns() - started)
    aggregation = parameters["aggregation"]
    value = statistics.mean(samples) if aggregation == "mean" else statistics.median(samples)
    report = {
        "metric": "cpu_call_wall_time", "unit": "ns", "value": value,
        "samples": samples, "aggregation": aggregation,
        "calls": target.calls, "checksum": checksum,
        "evidence_scope": "local CPU callable wall time; no NPU timing claim",
    }
    Path(request["output_dir"], "timing.json").write_text(json.dumps(report, allow_nan=False))
    return report
