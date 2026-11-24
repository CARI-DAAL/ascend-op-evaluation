"""Admission creates recoverable work before any candidate execution."""
from dataclasses import replace

import pytest
from ascend_op_eval.control.instance import (
    EvaluationInstance,
    UnsupportedHardwareProfileError,
)
from ascend_op_eval.control.models import WorkerIdentity, new_worker_id
from ascend_op_eval.deployment import HardwareProfileDescriptor, derive_hardware_profile
from conftest import TEST_HARDWARE, make_caller, make_request, ready_key
from test_api import (
    algorithms,
    build_app,
    make_test_settings,
    post,
    request_payload,
    seed_worker,
    trial_headers,
)


def cpu_worker(settings):
    return WorkerIdentity(
        new_worker_id(),
        settings.evaluator_build,
        algorithms(settings),
        TEST_HARDWARE.hardware_profile,
        hardware=TEST_HARDWARE,
        execution_class="cpu",
    )


def observed_hardware(**changes):
    fields = {
        "hardware_model": "Ascend910C",
        "driver_version": "26.1.1",
        "runtime_version": "CANN-9.2.0",
        "toolchain_version": TEST_HARDWARE.toolchain_version,
    }
    fields.update(changes)
    return HardwareProfileDescriptor(
        hardware_profile=derive_hardware_profile(**fields),
        default=False,
        **fields,
    )


@pytest.mark.anyio
async def test_admission_replay_conflict_and_rejection_never_execute_candidate(
    tmp_path, release_catalog_files,
):
    settings = make_test_settings(tmp_path).model_copy(update={
        "trial_rate_limit_per_minute": 1,
    })
    app = build_app(tmp_path, release_catalog_files, settings=settings)
    seed_worker(app)
    marker = tmp_path / "candidate-executed"
    payload = request_payload(triton_code=(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "class ModelNew: pass\n"
    ))
    async with app.http as client:
        first = await post(client, payload)
        replay = await post(client, payload)
        conflict = await post(client, {**payload, "triton_code": "class Other: pass"})
        limited = await post(client, payload, headers=trial_headers(key="second"))
    assert [r.status_code for r in (first, replay, conflict, limited)] == [202, 202, 409, 429]
    assert first.json()["evaluation_id"] == replay.json()["evaluation_id"]
    assert not marker.exists(), "candidate execution must belong to a leased Attempt"


@pytest.mark.anyio
async def test_cpu_only_pool_publishes_no_selectable_profile(
    tmp_path, release_catalog_files,
):
    app = build_app(tmp_path, release_catalog_files)
    app.store.heartbeat(cpu_worker(app.settings))
    async with app.http as client:
        compile_response = await post(client, request_payload(checks=["compile"]))
        correctness_response = await post(client, headers=trial_headers(key="npu"))
    assert compile_response.status_code == 503, compile_response.text
    assert compile_response.json()["error"]["code"] == "NOT_READY"
    assert correctness_response.status_code == 503
    assert correctness_response.json()["error"]["code"] == "NOT_READY"


@pytest.mark.anyio
async def test_compile_obeys_normal_inflight_limit(tmp_path, release_catalog_files):
    settings = make_test_settings(tmp_path).model_copy(update={"session_max_inflight": 1})
    app = build_app(tmp_path, release_catalog_files, settings=settings)
    seed_worker(app)
    async with app.http as client:
        first = await post(client, request_payload(checks=["compile"]))
        second = await post(client, request_payload(checks=["compile"]),
                            headers=trial_headers(key="second"))
    assert first.status_code == 202, first.text
    assert second.status_code == 413, second.text
    error = second.json()["error"]
    assert error["code"] == "LIMIT_EXCEEDED"
    assert error["retryable"] is True
    assert second.headers["Retry-After"] == "1"


def test_cpu_claim_and_recovery_keep_the_same_execution_class(
    store, settings, clock, make_command, make_worker,
):
    command = make_command(request=make_request(checks=["compile"]))
    store.create_or_replay(command)
    assert store.claim_next(make_worker(), card=3) is None
    first = store.claim_next(cpu_worker(settings), card=3)
    assert first is not None
    stored = store._r.hgetall(f"{settings.redis_prefix}:resource:{command.evaluation_id}")
    assert stored[b"attempt_card"] == b""
    assert stored[b"execution_class"] == b"cpu"
    clock.advance_ms(settings.lease_seconds * 1000 + 1)
    assert store.recover_expired_leases().requeued == 1
    assert store.claim_next(make_worker(), card=3) is None
    second = store.claim_next(cpu_worker(settings))
    assert second is not None and second.evaluation_id == first.evaluation_id
    assert second.attempt_id != first.attempt_id
    assert store.get_visible(command.evaluation_id, make_caller()).state == "running"


def test_claim_requires_the_admitted_build_and_algorithms(store, make_command, make_worker):
    command = make_command()
    store.create_or_replay(command)
    worker = make_worker()
    assert store.claim_next(replace(worker, evaluator_build="different-build")) is None
    assert store.claim_next(replace(
        worker, algorithms=replace(worker.algorithms, correctness="different-version"),
    )) is None
    assert store.claim_next(worker).evaluation_id == command.evaluation_id


def test_claim_requires_the_admitted_hardware_profile(store, make_command, make_worker):
    command = make_command()
    store.create_or_replay(command)
    worker = make_worker()
    other_profile = replace(worker, hardware_profile="hw_" + "1" * 32)
    assert store.claim_next(other_profile) is None
    lease = store.claim_next(worker)
    assert lease.evaluation_id == command.evaluation_id
    assert lease.pinned.hardware_profile == command.hardware_profile


def test_one_instance_routes_two_qualified_hardware_pools(
    store, settings, make_worker
):
    other_hardware = observed_hardware()
    other_worker = replace(
        make_worker(),
        hardware_profile=other_hardware.hardware_profile,
        hardware=other_hardware,
    )
    other_cpu = replace(cpu_worker(settings), hardware=other_hardware,
                        hardware_profile=other_hardware.hardware_profile)
    for worker in (make_worker(), cpu_worker(settings), other_worker, other_cpu):
        store.heartbeat(worker)
    instance = EvaluationInstance(settings=settings, store=store)

    local = instance.submit(
        make_request(hardware_profile=TEST_HARDWARE.hardware_profile),
        make_caller(), session_id="local", idempotency_key="local",
    )
    remote = instance.submit(
        make_request(hardware_profile=other_hardware.hardware_profile),
        make_caller(), session_id="remote", idempotency_key="remote",
    )

    local_lease = store.claim_next(make_worker())
    remote_lease = store.claim_next(other_worker)
    assert local_lease.evaluation_id == local.resource.evaluation_id
    assert local_lease.pinned.hardware_profile == TEST_HARDWARE.hardware_profile
    assert remote_lease.evaluation_id == remote.resource.evaluation_id
    assert (
        remote_lease.pinned.hardware_profile
        == other_hardware.hardware_profile
    )


def test_incomplete_pools_do_not_degrade_readiness_for_complete_profiles(
    store, settings, make_worker
):
    other_hardware = observed_hardware()
    instance = EvaluationInstance(settings=settings, store=store)

    assert instance.is_ready() is False
    store.heartbeat(make_worker())
    store.heartbeat(cpu_worker(settings))
    assert instance.is_ready() is True

    store.heartbeat(replace(
        make_worker(), hardware_profile=other_hardware.hardware_profile,
        hardware=other_hardware,
    ))
    assert instance.is_ready() is True
    store.heartbeat(replace(
        cpu_worker(settings), hardware_profile=other_hardware.hardware_profile,
        hardware=other_hardware,
    ))
    assert instance.is_ready() is True


def test_instance_rejects_an_unqualified_hardware_profile(
    store, settings, make_worker
):
    store.heartbeat(make_worker())
    instance = EvaluationInstance(settings=settings, store=store)
    request = make_request(hardware_profile="hw_" + "b" * 32)
    with pytest.raises(UnsupportedHardwareProfileError):
        instance.submit(request, make_caller(), session_id="s", idempotency_key="k")


def test_cpu_deadline_removes_dispatch_and_releases_quota(
    store, settings, clock, make_command,
):
    command = make_command(request=make_request(checks=["compile"], deadline_seconds=30))
    store.create_or_replay(command)
    clock.advance_ms(30_001)
    assert store.expire_due_resources() == 1
    assert store.claim_next(cpu_worker(settings)) is None
    resource = store.get_visible(command.evaluation_id, make_caller())
    assert resource.state == "timed_out"
    assert resource.result.compile.status == "timeout"
    assert store._r.zcard(ready_key(settings, execution_class="cpu")) == 0
    # A fresh admission in the same session has capacity after the deadline.
    assert store.create_or_replay(make_command(
        request=make_request(checks=["compile"]), idempotency_key="after-deadline",
    )).decision == "created"


def test_recovery_keeps_grade_binding_when_canonical_source_is_corrupt(
    store, settings, clock, make_command,
):
    from conftest import make_grade_caller, make_grade_request

    caller = make_grade_caller()
    request = make_grade_request(checks=["compile"], deadline_seconds=30)
    command = make_command(caller=caller, request=request)
    store.create_or_replay(command)
    store._r.hset(
        f"{settings.redis_prefix}:resource:{command.evaluation_id}",
        "canonical_request", b"not valid JSON",
    )
    lease = store.claim_next(cpu_worker(settings))
    assert lease.requested_checks == ("compile",)
    assert lease.pinned.manifest_id == request.grade_context.manifest_id
    clock.advance_ms(30_001)
    assert store.expire_due_resources() == 1
    resource = store.get_visible(command.evaluation_id, caller)
    assert resource.result.compile.status == "timeout"
    assert resource.result.provenance.manifest_id == request.grade_context.manifest_id
    assert resource.result.provenance.problem_id == request.grade_context.problem_id
    assert resource.result.provenance.grade_eligible is False
