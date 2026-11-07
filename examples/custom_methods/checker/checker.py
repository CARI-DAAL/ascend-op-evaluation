"""An external JSON-tree checker. No candidate code or service import is needed."""

import json
import math
from pathlib import Path


def run(request):
    actual = json.loads(Path(request["inputs"]["actual"]["path"]).read_text())
    reference = json.loads(Path(request["inputs"]["reference"]["path"]).read_text())
    atol, rtol = request["parameters"]["atol"], request["parameters"]["rtol"]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in (atol, rtol)):
        raise ValueError("atol and rtol must be finite nonnegative numbers")
    mismatches, compared = [], 0

    def compare(golden, observed, path):
        nonlocal compared
        if type(golden) in (int, float) and type(observed) in (int, float):
            compared += 1
            if not math.isfinite(golden) or not math.isfinite(observed):
                raise ValueError("the example checker requires finite JSON numbers")
            if abs(observed - golden) <= atol + rtol * abs(golden):
                return
        elif type(golden) is type(observed):
            if isinstance(golden, list) and len(golden) == len(observed):
                for index, (left, right) in enumerate(zip(golden, observed, strict=True)):
                    compare(left, right, f"{path}[{index}]")
                return
            if isinstance(golden, dict) and golden.keys() == observed.keys():
                for key in golden:
                    compare(golden[key], observed[key], f"{path}.{key}")
                return
            if golden == observed:
                compared += 1
                return
        if len(mismatches) < 8:
            mismatches.append(path)

    compare(reference, actual, "output")
    result = {
        "passed": not mismatches,
        "compared_numbers": compared,
        "mismatch_paths": mismatches,
        "atol": atol,
        "rtol": rtol,
    }
    Path(request["output_dir"], "comparison.json").write_text(json.dumps(result, allow_nan=False))
    return result
