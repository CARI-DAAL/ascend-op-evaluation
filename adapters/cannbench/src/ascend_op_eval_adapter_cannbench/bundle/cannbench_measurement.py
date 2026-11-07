"""Use CANNBench's exact kernel-details parser on an explicitly supplied capture."""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from vendor.pinned.perf_strategy import KernelDetailsStrategy, ProfFileLocations


def run(request):
    source = Path(request["inputs"]["kernel_details"]["path"])
    output = Path(request["output_dir"], "kernel_details.csv")
    shutil.copyfile(source, output)
    result = SimpleNamespace(elapsed_us=0.0, error_msg=None, metadata={}, op_times={})
    KernelDetailsStrategy().parse(ProfFileLocations(csv_path=str(output)), result)
    if result.error_msg or result.elapsed_us <= 0:
        raise ValueError(result.error_msg or "upstream parser produced no usable target timing")
    medians = result.op_times["device_kernels"]
    report = {
        "metric": "cannbench_kernel_details",
        "unit": "us",
        "value": result.elapsed_us,
        "samples": list(medians.values()),
        "aggregation": "sum_per_kernel_medians",
        "sample_scope": "per-kernel medians, not independent invocation samples",
        "per_kernel_medians_us": medians,
        "upstream_metadata": result.metadata,
        "upstream_revision": "f0488d95b4d44a6a0da1b8cd99e91fbd06181962",
        "scope": "parse supplied capture; no kernel execution or NPU measurement claim",
    }
    Path(request["output_dir"], "measurement.json").write_text(json.dumps(report, allow_nan=False))
    return report
