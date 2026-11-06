"""Explicit native candidate comparison and per-invocation profiler methods.

These methods deliberately do not claim CANNBench compatibility. Native float
comparison uses CPU float64 arithmetic and a direct absolute error cap; profiler
latency is the mean sum of all launches in each separately captured invocation.
"""

from __future__ import annotations
import csv
import math
import shutil
import time
from pathlib import Path

COMPARISON_METHOD = "native_tensor_v1"
MEASUREMENT_METHOD = "native_profiler_kernel_sum_v1"
_DEFAULT_TOLERANCES = {
    "float16": (0.09, 2 ** (-10)),
    "bfloat16": (0.1, 2 ** (-7)),
    "float32": (0.001, 2 ** (-13)),
    "float64": (0.001, 2 ** (-13)),
}


class NativeComparisonError(AssertionError):
    def __init__(self, message, kind="value_mismatch"):
        super().__init__(message)
        self.kind = kind


def _require(condition, message, kind="value_mismatch"):
    if not condition:
        raise NativeComparisonError(message, kind)


def copy_inputs(inputs, device):
    """Copy a tensor/container tree, preserving shared strided storage and views.

    Storage is copied once per independent execution. Unsupported object/layout
    inputs fail explicitly rather than quietly changing their semantics.
    """
    import torch

    objects, storages = ({}, {})
    active = set()

    def copy(value):
        key = id(value)
        if key in active:
            raise ValueError("native inputs cannot contain cyclic containers")
        if key in objects:
            return objects[key]
        if isinstance(value, torch.Tensor):
            if value.layout != torch.strided or value.is_conj() or value.is_neg():
                raise ValueError("native inputs require ordinary strided tensors")
            source = value.untyped_storage()
            storage_key = (str(value.device), source._cdata)
            if storage_key not in storages:
                raw = torch.empty(0, dtype=torch.uint8, device=value.device).set_(
                    source, 0, (source.nbytes(),), (1,)
                )
                storages[storage_key] = raw.to(device=device, copy=True)
            result = torch.empty(0, dtype=value.dtype, device=device).set_(
                storages[storage_key].untyped_storage(),
                value.storage_offset(),
                value.size(),
                value.stride(),
            )
            objects[key] = result
            return result
        if value is None or type(value) in (bool, int, float, str):
            return value
        active.add(key)
        try:
            if type(value) is list:
                result = [copy(item) for item in value]
            elif type(value) is tuple:
                result = tuple((copy(item) for item in value))
            elif type(value) is dict and all((type(k) in (str, int) for k in value)):
                result = {k: copy(item) for k, item in value.items()}
            else:
                raise ValueError("unsupported native input object")
            objects[key] = result
            return result
        finally:
            active.remove(key)

    return copy(inputs)


def compare_outputs(
    reference,
    actual,
    *,
    tolerance=None,
    non_compute=False,
    expected_device=None,
    path="output",
):
    """Compare Tensor trees with strict structure/dtype and explicit tolerances."""
    import torch

    if isinstance(reference, torch.Tensor):
        _require(
            isinstance(actual, torch.Tensor),
            f"{path}: candidate output must be a Tensor",
        )
        _require(
            reference.shape == actual.shape,
            f"{path}: output shape mismatch",
            "shape_mismatch",
        )
        _require(reference.dtype == actual.dtype, f"{path}: output dtype mismatch")
        _require(
            actual.layout == reference.layout == torch.strided,
            f"{path}: unsupported layout",
        )
        if expected_device is not None:
            expected = torch.device(expected_device)
            _require(
                actual.device.type == expected.type
                and (expected.index is None or actual.device.index == expected.index),
                f"{path}: candidate output device mismatch",
            )
        golden, candidate = (reference.detach().cpu(), actual.detach().cpu())
        if non_compute:
            _require(
                torch.equal(
                    golden.contiguous().reshape(-1).view(torch.uint8),
                    candidate.contiguous().reshape(-1).view(torch.uint8),
                ),
                f"{path}: bit-exact output mismatch",
            )
            return
        if not golden.is_floating_point():
            _require(not golden.is_complex(), f"{path}: complex outputs unsupported")
            _require(
                torch.equal(golden, candidate), f"{path}: integer/bool output mismatch"
            )
            return
        policy = tolerance or {}
        default = _DEFAULT_TOLERANCES.get(str(golden.dtype).removeprefix("torch."))
        _require(default is not None, f"{path}: native floating dtype unsupported")
        atol = default[0] if policy.get("max_atol") is None else policy["max_atol"]
        rtol = default[1] if policy.get("max_rtol") is None else policy["max_rtol"]
        ratio = (
            1.0
            if policy.get("required_matched_ratio") is None
            else policy["required_matched_ratio"]
        )
        cap = policy.get("max_error_cap")
        _require(
            all((math.isfinite(x) and x >= 0 for x in (atol, rtol))),
            "invalid native tolerance",
        )
        _require(
            math.isfinite(ratio) and 0 <= ratio <= 1, "invalid native matched ratio"
        )
        _require(
            cap is None or (math.isfinite(cap) and cap >= 0), "invalid native error cap"
        )
        golden, candidate = (golden.double(), candidate.double())
        allowed = torch.zeros_like(golden, dtype=torch.bool)
        if policy.get("allow_negative_inf", False):
            allowed = torch.isneginf(golden) & torch.isneginf(candidate)
        _require(
            bool((torch.isfinite(golden) | allowed).all())
            and bool((torch.isfinite(candidate) | allowed).all()),
            f"{path}: non-finite output",
            "non_finite_mismatch",
        )
        golden, candidate = (golden[~allowed], candidate[~allowed])
        if not golden.numel():
            return
        difference = (candidate - golden).abs()
        matched = difference <= atol + rtol * golden.abs()
        _require(
            float(matched.double().mean()) >= ratio
            and (cap is None or bool((difference <= cap).all())),
            f"{path}: output exceeds native tolerance",
        )
        return
    _require(type(reference) is type(actual), f"{path}: output structure mismatch")
    if type(reference) in (list, tuple):
        _require(
            len(reference) == len(actual), f"{path}: output structure length mismatch"
        )
        _require(reference, f"{path}: empty output structure")
        pairs = enumerate(zip(reference, actual))
    elif type(reference) is dict:
        _require(
            reference.keys() == actual.keys(), f"{path}: output structure keys mismatch"
        )
        _require(reference, f"{path}: empty output structure")
        pairs = ((key, (value, actual[key])) for key, value in reference.items())
    else:
        raise AssertionError(f"{path}: outputs must be Tensor trees")
    for key, (expected, observed) in pairs:
        compare_outputs(
            expected,
            observed,
            tolerance=tolerance,
            non_compute=non_compute,
            expected_device=expected_device,
            path=f"{path}[{key}]",
        )


def parse_call_profile(directory):
    """Sum every launch from exactly one isolated invocation's kernel CSV."""
    paths = list(Path(directory).rglob("kernel_details.csv"))
    if len(paths) != 1:
        raise ValueError(
            "native profiler requires exactly one kernel_details.csv export"
        )
    totals = {}
    with paths[0].open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        if not {"Name", "Duration(us)"} <= set(rows.fieldnames or ()):
            raise ValueError("native profiler CSV is missing required columns")
        for row in rows:
            name = row.get("Name", "").strip()
            try:
                duration = float(row["Duration(us)"])
            except (ValueError, TypeError) as exc:
                raise ValueError("invalid native kernel duration") from exc
            if not name or not math.isfinite(duration) or duration <= 0:
                raise ValueError("invalid native kernel identity or duration")
            totals[name] = totals.get(name, 0.0) + duration
    if not totals or any((not math.isfinite(value) for value in totals.values())):
        raise ValueError("native profiler exported no usable kernel durations")
    return totals


def _capture_call(test_fn, directory):
    import torch
    import torch_npu
    from triton_evaluation.runtime.profiler_runtime import profiler_export_runtime

    torch.npu.synchronize()
    config = torch_npu.profiler._ExperimentalConfig(
        profiler_level=torch_npu.profiler.ProfilerLevel.Level1,
        aic_metrics=torch_npu.profiler.AiCMetrics.PipeUtilization,
        l2_cache=False,
        data_simplification=False,
    )
    with (
        profiler_export_runtime(),
        torch_npu.profiler.profile(
            activities=[torch_npu.profiler.ProfilerActivity.NPU],
            on_trace_ready=torch_npu.profiler.tensorboard_trace_handler(str(directory)),
            record_shapes=False,
            profile_memory=False,
            with_stack=False,
            with_flops=False,
            with_modules=False,
            experimental_config=config,
        ),
    ):
        test_fn()
        torch.npu.synchronize()


def measure_profile(
    test_fn,
    warmup,
    repeats,
    profile_name,
    *,
    clear_l2_cache=False,
    keep_res=False,
    samples_ms=None,
):
    """Mean of separately captured callable invocations; no Triton dependency."""
    import torch

    if (
        type(warmup) is not int
        or warmup < 0
        or type(repeats) is not int
        or (not 1 <= repeats <= 100)
    ):
        raise ValueError("native profiler requires warmup >= 0 and 1 <= repeats <= 100")
    if clear_l2_cache:
        raise ValueError("native profiler does not support implicit L2 clearing")
    for _ in range(warmup):
        if hasattr(test_fn, "prepare"):
            test_fn.prepare()
        test_fn()
        torch.npu.synchronize()
    root = Path.cwd() / f"{profile_name}_native_{time.time_ns()}"
    root.mkdir()
    totals = {}
    try:
        for index in range(repeats):
            directory = root / f"call_{index:04d}"
            directory.mkdir()
            if hasattr(test_fn, "prepare"):
                test_fn.prepare()
            _capture_call(test_fn, directory)
            call = parse_call_profile(directory)
            if samples_ms is not None:
                samples_ms.append(sum(call.values()) / 1000.0)
            for name, duration in call.items():
                totals[name] = totals.get(name, 0.0) + duration
        means = {name: value / repeats for name, value in totals.items()}
        return (means, sum(means.values()) / 1000.0)
    finally:
        if not keep_res:
            shutil.rmtree(root, ignore_errors=True)
