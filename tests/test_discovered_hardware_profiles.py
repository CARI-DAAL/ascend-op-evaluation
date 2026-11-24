"""Hardware identity is observed from worker hosts, not declared by operators."""

import json
from dataclasses import replace

import pytest
from ascend_op_eval.control.broker import EvaluationStore
from ascend_op_eval.control.instance import (
    EvaluationInstance,
    UnsupportedHardwareProfileError,
)
from ascend_op_eval.control.models import AlgorithmVersions
from ascend_op_eval.deployment import HardwareProfileDescriptor, derive_hardware_profile
from ascend_op_eval.execution.worker_environment import (
    HardwarePreflightError,
    ObservedWorkerStack,
    discover_worker_environment,
)
from ascend_op_eval.serialization import canonical_json_bytes
from conftest import FakeClock, make_caller, make_request
from pydantic import ValidationError


def observed_stack(**overrides):
    payload = {
        "hardware_model": "Ascend 910B1",
        "driver_version": "26.1.1",
        "runtime_version": "9.2.0",
        "python_version": "3.12.13",
        "torch_version": "2.10.0+cpu",
        "torch_npu_version": "2.10.0.post4",
        "triton_ascend_version": "3.6.0",
    }
    payload.update(overrides)
    return ObservedWorkerStack(**payload)


def changed_hardware(**changes):
    fields = {
        key: value
        for key, value in {
            "hardware_model": "Ascend910B1",
            "driver_version": "26.1.1",
            "runtime_version": "CANN-9.2.0",
            "toolchain_version": (
                "CANN 9.2.0 / python 3.12.13 / torch 2.10.0+cpu / "
                "torch_npu 2.10.0.post4 / triton_ascend 3.6.0"
            ),
        }.items()
    }
    fields.update(changes)
    return HardwareProfileDescriptor(
        hardware_profile=derive_hardware_profile(**fields),
        default=False,
        **fields,
    )


def test_profile_descriptor_rejects_an_id_not_derived_from_its_fields():
    fields = {
        "hardware_model": "Ascend910B1",
        "driver_version": "26.1.1",
        "runtime_version": "CANN-9.2.0",
        "toolchain_version": "observed-toolchain",
    }

    with pytest.raises(ValidationError, match="does not derive"):
        HardwareProfileDescriptor(
            hardware_profile="hw_" + "d" * 32,
            default=False,
            **fields,
        )


def test_worker_discovery_derives_a_complete_profile_from_the_actual_stack():
    profile = discover_worker_environment(card=3, observe=lambda _: observed_stack())

    assert profile == HardwareProfileDescriptor(
        hardware_profile=profile.hardware_profile,
        hardware_model="Ascend 910B1",
        driver_version="26.1.1",
        runtime_version="CANN-9.2.0",
        toolchain_version=(
            "CANN 9.2.0 / python 3.12.13 / torch 2.10.0+cpu / "
            "torch_npu 2.10.0.post4 / triton_ascend 3.6.0"
        ),
        default=False,
    )
    assert profile.hardware_profile == profile.derived_hardware_profile


def test_worker_discovery_preserves_observed_runtime_characters():
    profile = discover_worker_environment(
        card=3,
        observe=lambda _: observed_stack(runtime_version="9.2.0.RC1"),
    )

    assert profile.runtime_version == "CANN-9.2.0.RC1"
    assert profile.toolchain_version.startswith("CANN 9.2.0.RC1 / ")


@pytest.mark.parametrize("field", ("hardware_model", "driver_version"))
def test_worker_discovery_fails_closed_when_a_required_identity_is_missing(field):
    with pytest.raises(HardwarePreflightError, match=field):
        discover_worker_environment(
            card=0,
            observe=lambda _: observed_stack(**{field: None}),
        )


def test_cpu_worker_discovery_uses_host_hardware_rather_than_guessing_it():
    profile = discover_worker_environment(card=None, observe=lambda _: observed_stack())

    assert profile.hardware_model == "Ascend 910B1"
    assert profile.driver_version == "26.1.1"


def test_heartbeats_publish_only_profiles_with_fresh_cpu_and_npu_workers(
    settings, redis_client, make_worker
):
    store = EvaluationStore(redis_client, settings, clock=FakeClock())
    cpu = replace(make_worker(), execution_class="cpu")
    store.heartbeat(make_worker())
    assert store.active_hardware_profiles() == []

    store.heartbeat(cpu)
    assert [profile.model_dump() for profile in store.active_hardware_profiles()] == [
        make_worker().hardware.model_copy(update={"default": True}).model_dump()
    ]


def test_profile_publication_expires_with_its_worker_heartbeats(
    settings, store, clock, make_worker
):
    store.heartbeat(make_worker())
    store.heartbeat(replace(make_worker(), execution_class="cpu"))
    assert len(store.active_hardware_profiles()) == 1

    clock.advance_ms(settings.lease_seconds * 1000 + 1)

    assert store.active_hardware_profiles() == []


def test_persisted_heartbeat_cannot_redeclare_its_observed_profile(
    settings, redis_client, make_worker
):
    store = EvaluationStore(redis_client, settings, clock=FakeClock())
    worker = make_worker()
    store.heartbeat(worker)
    store.heartbeat(replace(make_worker(), execution_class="cpu"))
    key = store._key("worker-heartbeats")
    payload = json.loads(redis_client.hget(key, worker.worker_id))
    payload["hardware_profile"] = "hw_" + "c" * 32
    redis_client.hset(
        key, worker.worker_id, canonical_json_bytes(payload),
    )

    assert store.active_hardware_profiles() == []


def test_deployment_profiles_ignore_malformed_persisted_heartbeat_records(
    settings, redis_client, make_worker
):
    store = EvaluationStore(redis_client, settings, clock=FakeClock())
    store.heartbeat(make_worker())
    store.heartbeat(replace(make_worker(), execution_class="cpu"))
    redis_client.hset(store._key("worker-heartbeats"), "corrupt", b"[]")

    assert len(store.active_hardware_profiles()) == 1


def test_incomplete_pools_do_not_remove_the_only_complete_default(
    settings, store, make_worker
):
    incomplete = changed_hardware(hardware_model="Ascend910C")
    store.heartbeat(make_worker())
    store.heartbeat(replace(make_worker(), execution_class="cpu"))
    store.heartbeat(replace(
        make_worker(),
        hardware_profile=incomplete.hardware_profile,
        hardware=incomplete,
    ))

    profiles = store.active_hardware_profiles()

    assert [profile.default for profile in profiles] == [True]


def test_deployment_profiles_require_the_current_evaluator_build(
    settings, store, make_worker
):
    old = replace(make_worker(), evaluator_build="git:" + "1" * 40)
    store.heartbeat(old)
    store.heartbeat(replace(
        make_worker(), evaluator_build="git:" + "1" * 40, execution_class="cpu",
    ))

    assert store.active_hardware_profiles() == []


def test_readiness_requires_at_least_one_observed_profile(settings, store):
    instance = EvaluationInstance(settings=settings, store=store)

    assert not instance.is_ready()


def test_deployment_profiles_use_effective_algorithm_identity(
    settings, redis_client, make_worker
):
    settings = settings.model_copy(update={"reference_device_policy": "npu-strict"})
    store = EvaluationStore(redis_client, settings, clock=FakeClock())
    algorithms = AlgorithmVersions(
        correctness=settings.effective_correctness_algorithm_version,
        decoy=settings.decoy_algorithm_version,
        benchmark=settings.benchmark_algorithm_version,
        profiler=settings.profiler_algorithm_version,
    )
    worker = replace(make_worker(), algorithms=algorithms)
    store.heartbeat(worker)
    store.heartbeat(replace(
        make_worker(), algorithms=algorithms, execution_class="cpu",
    ))

    assert len(store.active_hardware_profiles()) == 1


def test_admission_qualifies_only_profiles_published_by_real_workers(
    settings, store, make_worker
):
    other_hardware = changed_hardware(hardware_model="Ascend910C")
    other_worker = replace(
        make_worker(), hardware_profile=other_hardware.hardware_profile,
        hardware=other_hardware,
    )
    cpu = replace(make_worker(), execution_class="cpu")
    other_cpu = replace(
        make_worker(), hardware_profile=other_hardware.hardware_profile,
        hardware=other_hardware, execution_class="cpu",
    )
    store.heartbeat(cpu)
    store.heartbeat(make_worker())
    store.heartbeat(other_cpu)
    store.heartbeat(other_worker)
    instance = EvaluationInstance(settings=settings, store=store)

    assert instance.submit(
        make_request(hardware_profile=make_worker().hardware_profile),
        make_caller(), session_id="local", idempotency_key="local",
    ).decision == "created"
    assert instance.submit(
        make_request(hardware_profile=other_hardware.hardware_profile),
        make_caller(), session_id="remote", idempotency_key="remote",
    ).decision == "created"
    with pytest.raises(UnsupportedHardwareProfileError):
        instance.submit(
            make_request(hardware_profile="hw_" + "b" * 32),
            make_caller(), session_id="unknown", idempotency_key="unknown",
        )

    assert store.claim_next(make_worker()).pinned.hardware_profile == (
        make_worker().hardware_profile
    )
    assert (
        store.claim_next(other_worker).pinned.hardware_profile
        == other_hardware.hardware_profile
    )


def test_admission_does_not_choose_among_multiple_observed_profiles(
    settings, store, make_worker
):
    other_hardware = changed_hardware(
        hardware_model="Ascend910C",
        driver_version="26.2.0",
        runtime_version="CANN-9.2.1",
        toolchain_version=(
            "CANN 9.2.1 / python 3.12.13 / torch 2.10.0+cpu / "
            "torch_npu 2.10.0.post4 / triton_ascend 3.6.0"
        ),
    )
    for hardware in (make_worker().hardware, other_hardware):
        for execution_class in ("cpu", "npu"):
            store.heartbeat(replace(
                make_worker(),
                hardware_profile=hardware.hardware_profile,
                hardware=hardware,
                execution_class=execution_class,
            ))
    instance = EvaluationInstance(settings=settings, store=store)

    with pytest.raises(UnsupportedHardwareProfileError):
        instance.submit(
            make_request(), make_caller(), session_id="s", idempotency_key="k",
        )
