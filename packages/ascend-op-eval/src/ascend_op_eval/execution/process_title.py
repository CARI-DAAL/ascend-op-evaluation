"""Best-effort process labels; never part of evaluation or evidence identity.

Linux comm has 15 usable bytes. The compact name retains backend, phase/case
and the evaluation suffix; optional setproctitle adds full IDs to ps output.
The worker context is passed explicitly through the existing engine environment.
"""

import ctypes
import json
import logging
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

CONTEXT_ENV = "TRITON_EVAL_PROCESS_CONTEXT"
_CONTEXT = ContextVar("evaluation_process_context", default=None)
_PREFIX = {"ascendc": "AscC", "triton": "Trit", "torch": "PyT", "method": "Meth", "eval": "Eval"}
_PHASE = {
    "build": "Build", "load": "Load", "verify": "Vfy", "benchmark": "Bench",
    "profile": "Prof", "reference": "Ref", "inputs": "Input", "compare": "Cmp",
    "job": "Job", "idle": "Idle", "health": "Probe", "method": "Run",
}
_CASES = {"verify": "V", "benchmark": "B", "profile": "P", "reference": "R",
          "inputs": "I", "compare": "C"}
_WORKER_PHASE = {"build": "WBld", "load": "WLoad", "verify": "WVfy",
                 "benchmark": "WBch", "profile": "WProf", "job": "Job", "method": "WRun"}


@dataclass(frozen=True)
class ProcessContext:
    backend: str = "eval"
    evaluation_id: str = ""
    attempt_id: str = ""
    phase: str = "job"
    case: int | None = None
    role: str = "engine"


def _identifier(value, prefix):
    if isinstance(value, str) and re.fullmatch(prefix + r"_[0-9a-f]{32}", value):
        return value
    return ""


def current_context():
    context = _CONTEXT.get()
    if context is not None:
        return context
    return _decode_context(os.environ.get(CONTEXT_ENV, "{}"))


def _decode_context(value):
    try:
        raw = json.loads(value if len(value) <= 1024 else "{}")
        if not isinstance(raw, dict):
            return ProcessContext()
        return ProcessContext(
            backend=raw.get("backend") if raw.get("backend") in _PREFIX else "eval",
            evaluation_id=_identifier(raw.get("evaluation_id"), "ev"),
            attempt_id=_identifier(raw.get("attempt_id"), "at"),
            phase=raw.get("phase") if raw.get("phase") in _PHASE else "job",
        )
    except (ValueError, TypeError):
        return ProcessContext()


@lru_cache(maxsize=1)
def _prctl():
    try:
        function = ctypes.CDLL(None).prctl
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_ulong,
                             ctypes.c_ulong, ctypes.c_ulong]
        function.restype = ctypes.c_int
        return function
    except (OSError, AttributeError):
        return None


def set_process_title(title, *, detail=None):
    """Set comm without an optional dependency; full ps title is best effort."""
    compact = title.encode("utf-8", "replace")[:15].decode("utf-8", "ignore")
    if detail is not None:
        try:
            import setproctitle

            setproctitle.setproctitle(detail)
        except Exception:
            pass
    try:
        setter = _prctl()
        if setter is not None:
            setter(15, compact.encode("utf-8"), 0, 0, 0)
    except Exception:
        pass


def _display(context):
    phase = _PHASE.get(context.phase, "Job")
    if context.role == "worker":
        phase = _WORKER_PHASE.get(context.phase, phase)
    elif context.case is not None and context.phase in _CASES:
        phase = f"{_CASES[context.phase]}{context.case:03d}"
    suffix = "-" + context.evaluation_id[-4:] if context.evaluation_id else ""
    title = f"{_PREFIX.get(context.backend, 'Eval')}-{phase}{suffix}"
    detail = (
        f"ascend-eval {context.role} backend={context.backend} phase={context.phase}"
        f" evaluation={context.evaluation_id or '-'} attempt={context.attempt_id or '-'}"
        f" case={context.case if context.case is not None else '-'}"
    )
    set_process_title(title, detail=detail)


def set_stage(phase, *, case=None, backend=None, initialize=False):
    if not initialize and _CONTEXT.get() is None and CONTEXT_ENV not in os.environ:
        return
    context = current_context()
    context = replace(
        context, phase=phase if phase in _PHASE else "job",
        case=case if type(case) is int and 1 <= case <= 999 else None,
        backend=backend if backend in _PREFIX else context.backend,
    )
    _CONTEXT.set(context)
    _display(context)


def process_environment():
    context = _CONTEXT.get()
    if context is None:
        return {}
    return {CONTEXT_ENV: json.dumps({
        "backend": context.backend, "evaluation_id": context.evaluation_id,
        "attempt_id": context.attempt_id, "phase": context.phase,
    }, separators=(",", ":"))}


def sanitized_context(value):
    context = _decode_context(value)
    return json.dumps({
        "backend": context.backend, "evaluation_id": context.evaluation_id,
        "attempt_id": context.attempt_id, "phase": context.phase,
    }, separators=(",", ":"))


def infer_backend(*, implementation="comparison", native=False):
    """Fallback for direct CLI use; never override the worker's request identity."""
    context = current_context()
    if context.backend == "eval":
        set_stage(context.phase, case=context.case, backend=(
            "ascendc" if native or implementation == "native" else
            "torch" if implementation == "torch" else "triton"
        ))


def labelled_inputs(iterable):
    """Label lazy materialization without holding the previous case's tensors."""
    iterator = iter(iterable)
    while True:
        set_stage("inputs")
        try:
            # An unbound yield matters: consumers may start another pass while
            # this iterator is still suspended, so retain no workload locally.
            yield next(iterator)
        except StopIteration:
            return


@contextmanager
def evaluation_process(evaluation_id, attempt_id):
    try:
        previous = Path("/proc/thread-self/comm").read_text().strip()
    except OSError:
        previous = "Eval-Idle"
    try:
        import setproctitle

        previous_detail = setproctitle.getproctitle()
    except Exception:
        previous_detail = None
    context = ProcessContext(
        evaluation_id=_identifier(evaluation_id, "ev"),
        attempt_id=_identifier(attempt_id, "at"), role="worker",
    )
    token = _CONTEXT.set(context)
    _display(context)
    try:
        yield
    finally:
        _CONTEXT.reset(token)
        set_process_title(previous, detail=previous_detail)


def identify_request(request):
    if _CONTEXT.get() is None:
        return
    backend = (
        "method" if getattr(request, "method_execution", None) is not None else
        "ascendc" if request.native_candidate is not None else
        "torch" if request.implementation == "torch" else "triton"
    )
    set_stage("job", backend=backend)
    context = current_context()
    logging.getLogger(__name__).info(
        "process task pid=%s backend=%s evaluation=%s attempt=%s",
        os.getpid(), backend, context.evaluation_id, context.attempt_id,
    )


def task_stage(check):
    if _CONTEXT.get() is not None:
        set_stage({"compile": "load", "correctness": "verify",
                   "performance": "benchmark", "profile": "profile", "method": "method"}[check])


@contextmanager
def process_phase(phase, *, case=None):
    if _CONTEXT.get() is None and CONTEXT_ENV not in os.environ:
        yield
        return
    previous = current_context()
    token = _CONTEXT.set(previous)
    set_stage(phase, case=case)
    try:
        yield
    finally:
        _CONTEXT.reset(token)
        _display(previous)
