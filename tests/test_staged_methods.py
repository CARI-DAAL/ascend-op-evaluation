"""Staged custom methods: a CPU build stage hands files to a separately leased NPU stage."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from ascend_op_eval.api.contract import EvaluationResource
from ascend_op_eval.config import Settings
from ascend_op_eval.evaluators.base import run_script
from ascend_op_eval.evaluators.evaluation import EvaluationEvaluator
from ascend_op_eval.evaluators.method import MethodEvaluator
from ascend_op_eval.execution.method_execution import execute_method
from ascend_op_eval.methods.contracts import (
    MethodDescriptor,
    MethodExecution,
    MethodPackage,
    MethodStageRecord,
    RegisteredMethod,
    package_identity,
)
from ascend_op_eval.methods.registry import runtime_fingerprint
from test_api import trial_headers
from test_compile_check import app_with_precheck, cpu_worker
from test_worker import build_worker

pytestmark = pytest.mark.anyio

WHEEL_BYTES = b"w" * (2 * 1024 * 1024)  # larger than the 1 MiB artifact cap
WHEEL = "dist/pkg-1.0-py3-none-any.whl"

SOURCE = '''
import hashlib
from pathlib import Path

def build(request):
    if request["parameters"]["fail_build"]:
        return {"completed": False, "phase": "build"}
    wheel = Path(request["handoff_dir"], "dist", "pkg-1.0-py3-none-any.whl")
    wheel.parent.mkdir()
    wheel.write_bytes(b"w" * (2 * 1024 * 1024))
    return {"phase": "build"}

def run(request):
    [(name, item)] = request["handoff"].items()
    data = Path(item["path"]).read_bytes()
    return {"completed": True, "phase": "run", "wheel": name,
            "sha256": hashlib.sha256(data).hexdigest(), "stage": request["stage"]}
'''


def staged_package(**descriptor):
    return {
        "contract_version": "custom-method-v1",
        "descriptor": {
            "name": "staged-fixture", "version": "1", "kind": "harness",
            "entrypoint": "stages:run",
            "parameters_schema": {
                "type": "object", "additionalProperties": False,
                "properties": {"fail_build": {"type": "boolean", "default": False}},
            },
            "output_schema": {"type": "object", "required": ["completed", "phase"]},
            "requirements": {"device": "npu"},
            "stages": [
                {"device": "cpu", "entrypoint": "stages:build"},
                {"device": "npu", "entrypoint": "stages:run"},
            ],
            **descriptor,
        },
        "files": {"stages.py": SOURCE},
    }


def cpu_standin_for_npu(command, work_dir, device_id, *args, **kwargs):
    """This host has no torch_npu: run the NPU stage's child on CPU."""
    request_path = Path(command[2])
    request = json.loads(request_path.read_text())
    assert request["device"] == "npu:0"
    request["device"] = "cpu"
    request_path.chmod(0o600)
    request_path.write_text(json.dumps(request))
    return run_script(command, work_dir, None, *args, **kwargs)


def npu_worker(app, device_id=0):
    evaluator = EvaluationEvaluator(
        verify=None, benchmark=None, profile=None,
        method=MethodEvaluator(runner=cpu_standin_for_npu, settings=app.settings),
    )
    return build_worker(
        app.store, app.settings, evaluator, app.clock, device_id=device_id,
        canary=lambda **kwargs: True,
    )


def staged_app(tmp_path, release_catalog_files):
    return app_with_precheck(
        tmp_path, release_catalog_files, stage_spool_dir=tmp_path / "spool",
    )


async def submit(client, parameters=None, deadline_seconds=300):
    registered = await client.post("/methods", headers=trial_headers(), json=staged_package())
    assert registered.status_code in (200, 201), registered.text
    response = await client.post(
        "/method-evaluations", headers=trial_headers(), json={
            "contract_version": "custom-method-v1",
            "method_ref": registered.json()["method_ref"],
            "parameters": parameters or {},
            "deadline_seconds": deadline_seconds,
        },
    )
    assert response.status_code == 202, response.text
    return response.headers["Location"]


async def read(client, location):
    return (await client.get(location, headers=trial_headers())).json()


async def test_build_stage_on_cpu_hands_wheel_to_separately_leased_npu_stage(
    tmp_path, release_catalog_files,
):
    app = staged_app(tmp_path, release_catalog_files)
    cpu, npu = cpu_worker(app), npu_worker(app)
    async with app.http as client:
        location = await submit(client, deadline_seconds=60)
        evaluation_id = location.rsplit("/", 1)[-1]
        submitted = await read(client, location)
        assert not npu.run_once()  # the build stage never occupies a card

        app.clock.advance_ms(50_000)
        assert cpu.run_once()
        between = await read(client, location)
        assert between["state"] == "running" and between["result"] is None
        # Each stage gets its own deadline, starting when it is queued.
        moved = EvaluationResource.model_validate_json(json.dumps(between)).deadline_at - (
            EvaluationResource.model_validate_json(json.dumps(submitted)).deadline_at
        )
        assert moved == timedelta(seconds=50)
        spooled = app.settings.stage_spool_dir / evaluation_id
        assert (spooled / hashlib.sha256(WHEEL_BYTES).hexdigest()).read_bytes() == WHEEL_BYTES
        assert not cpu.run_once()  # the run stage is NPU work

        app.clock.advance_ms(50_000)  # past the build stage's original deadline
        assert npu.run_once()
        record = await read(client, location)

    assert record["state"] == "completed", record
    data = record["result"]["method"]["data"]
    assert data["outcome"] == "completed", data
    assert data["report"] == {
        "completed": True, "phase": "run", "wheel": WHEEL,
        "sha256": hashlib.sha256(WHEEL_BYTES).hexdigest(), "stage": {"index": 1, "count": 2},
    }
    build, run = data["stages"]
    assert (build["index"], build["device"], build["outcome"]) == (0, "cpu", "completed")
    assert build["handoff"] == {
        WHEEL: {"sha256": hashlib.sha256(WHEEL_BYTES).hexdigest(), "size_bytes": len(WHEEL_BYTES)},
    }
    assert (run["index"], run["device"], run["handoff"]) == (1, "npu", {})
    assert not spooled.exists()  # removed once the final stage committed


async def test_build_without_handoff_terminates_without_entering_npu_queue(
    tmp_path, release_catalog_files,
):
    app = staged_app(tmp_path, release_catalog_files)
    cpu, npu = cpu_worker(app), npu_worker(app)
    async with app.http as client:
        location = await submit(client, {"fail_build": True})
        assert cpu.run_once()
        record = await read(client, location)
        assert not npu.run_once()
    assert record["state"] == "completed", record
    data = record["result"]["method"]["data"]
    assert data["report"] == {"completed": False, "phase": "build"}
    [build] = data["stages"]
    assert (build["device"], build["handoff"]) == ("cpu", {})


async def test_lost_npu_stage_is_retried_from_the_spooled_handoff(
    tmp_path, release_catalog_files,
):
    app = staged_app(tmp_path, release_catalog_files)
    cpu, npu, other_card = cpu_worker(app), npu_worker(app), npu_worker(app, device_id=1)
    async with app.http as client:
        location = await submit(client)
        assert cpu.run_once()
        lease = app.store.claim_next(npu.identity, card=0)  # this worker then dies
        assert len(lease.method_stage_records) == 1
        app.clock.advance_ms((app.settings.lease_seconds + 1) * 1000)
        assert app.store.recover_expired_leases().requeued == 1
        assert not cpu.run_once()  # recovery keeps the NPU placement
        assert other_card.run_once()
        record = await read(client, location)
    assert record["state"] == "completed", record
    assert [stage["device"] for stage in record["result"]["method"]["data"]["stages"]] == [
        "cpu", "npu",
    ]


async def test_staged_method_requires_a_configured_spool(tmp_path, release_catalog_files):
    app = app_with_precheck(tmp_path, release_catalog_files)
    cpu_worker(app)
    async with app.http as client:
        registered = await client.post(
            "/methods", headers=trial_headers(), json=staged_package(),
        )
        response = await client.post("/method-evaluations", headers=trial_headers(), json={
            "contract_version": "custom-method-v1",
            "method_ref": registered.json()["method_ref"],
        })
    assert response.status_code >= 400, response.text
    assert response.json()["error"]["code"] == "ENVIRONMENT_UNAVAILABLE", response.text
    assert "stage spool" in response.text


def test_single_stage_descriptor_identity_is_unchanged():
    descriptor = MethodDescriptor.model_validate(
        {**staged_package()["descriptor"], "stages": None}
    )
    assert "stages" not in descriptor.model_dump(mode="json")
    assert [stage.device for stage in descriptor.stage_plan] == ["npu"]


BUILD_CPU = {"device": "cpu", "entrypoint": "stages:build"}
RUN_CPU = {"device": "cpu", "entrypoint": "stages:run"}
RUN_NPU = {"device": "npu", "entrypoint": "stages:run"}


@pytest.mark.parametrize("stages", [[BUILD_CPU, RUN_CPU], [RUN_NPU, BUILD_CPU], [RUN_NPU]])
def test_final_stage_must_match_descriptor_entrypoint_and_device(stages):
    with pytest.raises(ValueError):
        MethodDescriptor.model_validate({**staged_package()["descriptor"], "stages": stages})


def test_corrupt_spooled_handoff_is_an_environment_failure(tmp_path):
    frozen = MethodPackage.model_validate(staged_package())
    registered = RegisteredMethod(package=frozen, **package_identity(frozen))
    execution = MethodExecution(
        **registered.model_dump(),
        requested_parameters={}, effective_parameters={"fail_build": False},
        inputs={}, dependencies={}, runtime_id="worker-python-v1",
        runtime_fingerprint=runtime_fingerprint(Settings()), capabilities=["python"],
        submission={"method_ref": registered.method_ref}, limits={},
    )
    spool = tmp_path / "spool"
    spool.mkdir()
    digest = hashlib.sha256(WHEEL_BYTES).hexdigest()
    (spool / digest).write_bytes(b"tampered")
    build = MethodStageRecord(
        index=0, device="cpu", entrypoint="stages:build", outcome="completed",
        duration_ms=1, handoff={WHEEL: {"sha256": digest, "size_bytes": len(WHEEL_BYTES)}},
    )
    work = tmp_path / "work"
    work.mkdir()
    result = execute_method(
        execution, work, device_id=0,
        deadline_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        lease_valid=lambda: True, runner=lambda *a, **k: pytest.fail("must not run"),
        stage_records=[build], spool_dir=spool,
    )
    assert result.outcome == "environment_unavailable", result
    assert [stage.index for stage in result.stages] == [0, 1]
