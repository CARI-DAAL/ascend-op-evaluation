"""Deprecated import bridge to Ascend Op Eval; all aliases share module identity.

The bridge performs no data conversion and does not grant new wire capabilities.
Install ascend-op-eval-compat only for consumers that still use the old imports.
"""

import importlib
import importlib.abc
import importlib.util
import sys
import warnings

import ascend_op_eval

_MOVED = {
    "runtime.health": "resources.health",
    "runtime.sandbox": "runtimes.sandbox",
    "runtime.execution_environment": "runtimes.execution_environment",
    "runtime.profiler_runtime": "runtimes.profiler_runtime",
    "runtime": "execution",
    "service": "control",
}


class _Alias(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith("triton_evaluation."):
            return None
        suffix = fullname.removeprefix("triton_evaluation.")
        for old, new in _MOVED.items():
            if suffix == old or suffix.startswith(old + "."):
                suffix = new + suffix[len(old):]
                break
        module = importlib.import_module("ascend_op_eval." + suffix)
        spec = importlib.util.spec_from_loader(
            fullname, self, is_package=hasattr(module, "__path__"),
        )
        spec.loader_state = module
        return spec

    def create_module(self, spec):
        return spec.loader_state

    def exec_module(self, module):
        pass


warnings.warn(
    "triton_evaluation is deprecated; use ascend_op_eval and its documented module paths",
    DeprecationWarning,
    stacklevel=2,
)
sys.meta_path.insert(0, _Alias())
__path__ = []
__doc__ = ascend_op_eval.__doc__
