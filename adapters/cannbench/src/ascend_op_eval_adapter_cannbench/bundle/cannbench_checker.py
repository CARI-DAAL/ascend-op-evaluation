"""Run the pinned CANNBench numeric comparator; not the full task evaluator."""

import json
import math
from pathlib import Path

import torch
from vendor.pinned.utils.compare import compare_tensors


def decode_document(document):
    def scalar(value):
        if isinstance(value, list):
            return [scalar(item) for item in value]
        if value in ("nan", "+inf", "-inf"):
            return {"nan": float("nan"), "+inf": float("inf"), "-inf": -float("inf")}[value]
        return value

    outputs = document["outputs"]
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("tensor document needs a nonempty outputs list")
    result = []
    for output in outputs:
        if output is None:
            result.append(None)
            continue
        if set(output) - {"dtype", "shape", "data"}:
            raise ValueError(
                "unsupported tensor encoding field (layout/alias require full harness)"
            )
        dtype = getattr(torch, output["dtype"], None)
        if not isinstance(dtype, torch.dtype):
            raise ValueError("unknown tensor dtype")
        value = torch.tensor(scalar(output["data"]), dtype=dtype, device="cpu")
        if "shape" in output:
            value = value.reshape(output["shape"])
        result.append(value)
    return result


def finite_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else "+Inf" if value > 0 else "-Inf"
    if isinstance(value, dict):
        return {key: finite_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [finite_json(item) for item in value]
    return value


def run(request):
    def read(name):
        return decode_document(json.loads(Path(request["inputs"][name]["path"]).read_text()))

    parameters = request["parameters"]
    actual = read("actual")
    first = next((value for value in actual if isinstance(value, torch.Tensor)), None)
    if first is None:
        raise ValueError("at least one actual tensor output is required")
    result = compare_tensors(
        actual,
        read("reference"),
        dtype=str(first.dtype).removeprefix("torch."),
        native_output=read("native") if "native" in request["inputs"] else None,
        custom_thresholds=parameters["custom_thresholds"],
    )
    report = finite_json(result.to_dict())
    report["scope"] = "pinned numeric comparator; no proto validation, generation or NPU execution"
    report["upstream_revision"] = "f0488d95b4d44a6a0da1b8cd99e91fbd06181962"
    Path(request["output_dir"], "comparison.json").write_text(json.dumps(report, allow_nan=False))
    return report
