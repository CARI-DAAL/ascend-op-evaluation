from pathlib import Path

import torch
import torch_npu  # noqa: F401

torch.ops.load_library(str(Path(__file__).parent / "build/libnative_eval_smoke.so"))


def add(x, y):
    return torch.ops.native_eval_smoke.add(x, y)


def reduce_sum(x):
    return torch.ops.native_eval_smoke.reduce_sum(x)


def matmul(x, y):
    return torch.ops.native_eval_smoke.matmul(x, y)
