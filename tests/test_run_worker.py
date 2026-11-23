"""Worker command line selects one execution resource without opening another."""
from types import SimpleNamespace
from unittest import mock

import pytest
import redis
from ascend_op_eval.entrypoints import run_worker


def test_cpu_cli_never_holds_an_npu(monkeypatch):
    worker = SimpleNamespace(
        settings=SimpleNamespace(worker_hardware_profile="hw_" + "1" * 32),
        serve_forever=mock.Mock(),
    )
    build = mock.Mock(return_value=worker)
    monkeypatch.setattr("sys.argv", ["run_worker.py", "--cpu"])
    monkeypatch.setattr(run_worker, "build_worker", build)
    monkeypatch.setattr(run_worker, "hold_device", mock.Mock(side_effect=AssertionError))
    monkeypatch.setattr(run_worker, "set_process_title", lambda: None)
    monkeypatch.setattr(run_worker, "_install_signal_handlers", lambda: "stop")
    verify = mock.Mock()
    monkeypatch.setattr(run_worker, "verify_worker_environment", verify)
    run_worker.main()
    build.assert_called_once()
    assert build.call_args.args[0] is None
    verify.assert_called_once()
    assert verify.call_args.args[1] is None
    worker.serve_forever.assert_called_once_with(stop_event="stop")


def test_worker_cli_verifies_environment_before_connecting_to_storage(monkeypatch):
    settings = SimpleNamespace(worker_hardware_profile="hw_" + "2" * 32)
    worker = SimpleNamespace(
        settings=settings,
        serve_forever=mock.Mock(),
    )
    events = []
    build = mock.Mock(return_value=worker)
    build.side_effect = lambda *args: (events.append("build"), worker)[1]
    verify = mock.Mock(side_effect=lambda *_: events.append("verify"))
    startup = mock.Mock(side_effect=lambda _: events.append("release"))
    monkeypatch.setattr("sys.argv", ["run_worker.py", "--card", "5"])
    settings_type = mock.Mock(from_env=mock.Mock(return_value=settings))
    monkeypatch.setattr(run_worker, "Settings", settings_type)
    monkeypatch.setattr(run_worker, "startup_identity", startup)
    monkeypatch.setattr(run_worker, "verify_worker_environment", verify)
    monkeypatch.setattr(run_worker, "build_worker", build)
    monkeypatch.setattr(run_worker, "hold_device", mock.Mock())
    monkeypatch.setattr(run_worker, "set_process_title", lambda: None)
    monkeypatch.setattr(run_worker, "_install_signal_handlers", lambda: "stop")
    run_worker.main()
    assert events == ["release", "verify", "build"]
    startup.assert_called_once_with(settings)
    verify.assert_called_once_with(settings, 5)
    build.assert_called_once_with(5, settings)
    worker.serve_forever.assert_called_once_with(stop_event="stop")


@pytest.mark.parametrize("options", [[], ["--cpu", "--card", "0"], ["--card", "-1"]])
def test_worker_cli_requires_exactly_one_valid_execution_resource(monkeypatch, options):
    monkeypatch.setattr("sys.argv", ["run_worker.py", *options])
    with pytest.raises(SystemExit) as error:
        run_worker.main()
    assert error.value.code == 2


def test_worker_assembles_independent_dependencies_and_shared_runner(monkeypatch, tmp_path):
    import fakeredis
    from ascend_op_eval.config import Settings

    settings = Settings(
        redis_url="redis://localhost:6380/2", redis_prefix="test-owner",
        baseline_cache_namespace="changed-hardware", engine_dir=str(tmp_path),
        reference_device_policy="npu-strict", card_canary_on_startup=False,
    )
    durable, advisory = fakeredis.FakeRedis(), fakeredis.FakeRedis()
    redis_factory = mock.Mock(side_effect=[durable, advisory, durable, advisory])
    monkeypatch.setattr(redis.Redis, "from_url", redis_factory)
    monkeypatch.setenv("TRITON_EVAL_REFERENCE_DEVICE_POLICY", "cpu-first")
    worker = run_worker.build_worker(3, settings)
    other_hardware = run_worker.build_worker(
        4, settings.model_copy(update={"worker_hardware_model": "Ascend910C"})
    )
    assert redis_factory.call_args_list[0] == mock.call(settings.redis_url, decode_responses=False)
    cache_options = redis_factory.call_args_list[1].kwargs
    assert cache_options["socket_connect_timeout"] == 0.25
    assert cache_options["socket_timeout"] == 0.25
    assert cache_options["retry"].get_retries() == 0
    assert cache_options["retry_on_timeout"] is False
    assert cache_options["retry_on_error"] == []
    cache = worker.evaluator.benchmark.baseline_cache
    key = cache.key_for("torch", method="event", warmup=5, repeats=50)
    other_key = other_hardware.evaluator.benchmark.baseline_cache.key_for(
        "torch", method="event", warmup=5, repeats=50
    )
    assert other_key != key
    worker.verdict_cache.put("shared-verdict", "compile_error", 60)
    other_hardware.verdict_cache.put("other-verdict", "precheck_passed", 60)
    assert other_hardware.verdict_cache.get("shared-verdict") is None
    assert worker.verdict_cache.get("other-verdict") is None
    cache.publish(key, 1, {1: 2.0})
    assert advisory.exists(key)
    assert not durable.exists(key)
    worker.verdict_cache.put("candidate", "compile_error", 60)
    verdict_key = (
        f"test-owner:{settings.worker_hardware_profile}:verdict:candidate"
    )
    assert advisory.exists(verdict_key)
    assert not durable.exists(verdict_key)
    worker.metrics.increment("worker_attempts_total", {})
    assert advisory.hget("test-owner:metrics:data:worker_attempts_total", "total") == b"1"
    assert not durable.exists("test-owner:metrics:data:worker_attempts_total")
    assert worker.store._metrics is worker.metrics
    assert worker._health._metrics is worker.metrics
    for check in (worker.evaluator.verify, worker.evaluator.benchmark, worker.evaluator.profile):
        assert check.engine_dir == str(tmp_path)
        assert check.runner is worker.script_runner
    assert worker.evaluator.verify.reference_device_policy == "npu-strict"
    captured = worker.script_runner.keywords["environment"]
    assert captured["TRITON_EVAL_REFERENCE_DEVICE_POLICY"] == "npu-strict"
    assert captured["TRITON_EVAL_ENGINE_DIR"] == str(tmp_path)
    monkeypatch.setenv("TRITON_EVAL_REFERENCE_DEVICE_POLICY", "changed-later")
    assert captured["TRITON_EVAL_REFERENCE_DEVICE_POLICY"] == "npu-strict"


def test_baseline_cache_namespace_can_be_set_from_environment(monkeypatch):
    from ascend_op_eval.config import Settings

    monkeypatch.setenv("TRITON_EVAL_BASELINE_CACHE_NAMESPACE", "runtime-2026")
    assert Settings().baseline_cache_namespace == "runtime-2026"


def test_scalar_baseline_reuse_has_explicit_algorithm_identity():
    from ascend_op_eval.config import Settings

    assert Settings().benchmark_algorithm_version == "geometric-mean-baseline-v2"
