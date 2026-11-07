"""Durable evaluation worker entrypoint: CPU prechecks or one pinned NPU."""
import argparse
import logging
import os
import signal
from functools import partial

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from ascend_op_eval.config import Settings, command_environment
from ascend_op_eval.control.broker import EvaluationStore
from ascend_op_eval.control.metrics import RedisMetrics
from ascend_op_eval.evaluators.base import run_script
from ascend_op_eval.evaluators.benchmark import BenchmarkEvaluator
from ascend_op_eval.evaluators.evaluation import EvaluationEvaluator
from ascend_op_eval.evaluators.method import MethodEvaluator
from ascend_op_eval.evaluators.profile import ProfileEvaluator
from ascend_op_eval.evaluators.verify import VerifyEvaluator
from ascend_op_eval.execution.baseline_cache import BaselineCache
from ascend_op_eval.execution.process_title import set_process_title as _set_process_title
from ascend_op_eval.execution.verdict_cache import VerdictCache
from ascend_op_eval.execution.worker import Worker
from ascend_op_eval.versioning import startup_identity

logger = logging.getLogger(__name__)

# Process title shown in `npu-smi info` / ps; 15-char /proc/<pid>/comm limit.
_PROCESS_TITLE = "Eval-Idle"

# Keeps the startup device-hold tensor alive for the process lifetime.
_DEVICE_HOLD = None


def set_process_title() -> None:
    """Name the idle worker even without the optional setproctitle package."""
    _set_process_title(_PROCESS_TITLE, detail="ascend-eval worker idle")


def build_worker(card: int | None, settings: Settings | None = None) -> Worker:
    settings = settings or Settings.from_env()
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = "" if card is None else str(card)
    durable_client = redis.Redis.from_url(settings.redis_url, decode_responses=False)
    cache_client = redis.Redis.from_url(
        settings.redis_url, decode_responses=False,
        socket_connect_timeout=0.25, socket_timeout=0.25,
        retry=Retry(NoBackoff(), 0), retry_on_timeout=False, retry_on_error=[],
    )
    baseline_cache = BaselineCache(
        cache_client, prefix=settings.redis_prefix, namespace=settings.baseline_cache_namespace,
    )
    metrics = RedisMetrics(cache_client, settings.redis_prefix)
    store = EvaluationStore(durable_client, settings, metrics=metrics)
    runner = partial(run_script, environment=command_environment(settings))
    evaluator = EvaluationEvaluator(
        verify=VerifyEvaluator(
            settings.engine_dir, budget_cap_seconds=settings.verify_budget_cap_seconds,
            reference_device_policy=settings.reference_device_policy, runner=runner,
        ),
        benchmark=BenchmarkEvaluator(
            settings.engine_dir, timeout_seconds=settings.benchmark_timeout_seconds,
            baseline_cache=baseline_cache, runner=runner,
        ),
        profile=ProfileEvaluator(settings.engine_dir, runner=runner),
        method=MethodEvaluator(runner=runner, settings=settings),
    )
    return Worker(
        store, evaluator, device_id=card, settings=settings, metrics=metrics,
        verdict_cache=VerdictCache(cache_client, prefix=settings.redis_prefix),
        script_runner=runner,
    )


def hold_device(settings: Settings, card: int) -> None:
    """Open the pinned NPU and keep a small allocation alive so `npu-smi info`
    shows this worker continuously, not only while a job's engine subprocess
    is running. Best effort: a failure is logged and serving continues.
    """
    global _DEVICE_HOLD
    if settings.device_hold_mb <= 0:
        return
    try:
        import torch
        import torch_npu  # noqa: F401 — registers the NPU backend on import

        # ASCEND_RT_VISIBLE_DEVICES pins this process to one physical card,
        # which becomes logical device 0.
        torch.npu.set_device(0)
        _DEVICE_HOLD = torch.empty(
            settings.device_hold_mb * 1024 * 1024,  # MB → bytes (uint8 elements)
            dtype=torch.uint8,
            device="npu",
        )
        logger.info(
            "holding %d MB on card %d for npu-smi visibility",
            settings.device_hold_mb, card,
        )
    except Exception as error:  # noqa: BLE001 — visibility is best effort
        _DEVICE_HOLD = None
        logger.warning(
            "device hold failed (%s); worker serves but npu-smi may not "
            "show it while idle",
            type(error).__name__,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    execution = parser.add_mutually_exclusive_group(required=True)
    execution.add_argument(
        "--card", type=int, help="Physical NPU card id to pin this worker to"
    )
    execution.add_argument("--cpu", action="store_true", help="Execute compile-only attempts")
    args = parser.parse_args()
    if args.card is not None and args.card < 0:
        parser.error("--card must be nonnegative")
    set_process_title()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Formal worker startup: verify the release before claiming any attempt.
    startup_identity(Settings.from_env())
    worker = build_worker(args.card)
    if args.card is not None:
        hold_device(worker.settings, args.card)
    stop = _install_signal_handlers()
    worker.serve_forever(stop_event=stop)


def _install_signal_handlers():
    import threading

    stop = threading.Event()

    def _handle(signum, frame):
        stop.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    return stop


if __name__ == "__main__":
    main()
