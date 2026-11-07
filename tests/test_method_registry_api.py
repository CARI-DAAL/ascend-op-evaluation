"""Caller-owned method packages and artifacts over the public HTTP contract."""

import base64

import pytest
from ascend_op_eval.control.models import WorkerIdentity, new_worker_id
from test_api import TRIAL_TOKEN_2, algorithms, build_app, seed_worker, trial_headers

pytestmark = pytest.mark.anyio


def package(source="raise RuntimeError('must not import at registration')\n", **parameters):
    return {
        "contract_version": "custom-method-v1",
        "descriptor": {
            "name": "threshold-check",
            "version": "1",
            "kind": "checker",
            "entrypoint": "checker:run",
            "parameters_schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"threshold": {"type": "number", "minimum": 0, "default": 1}},
            },
            **parameters,
        },
        "files": {"checker.py": source},
    }


async def test_registration_seals_bytes_without_importing_user_code(tmp_path):
    app = build_app(tmp_path, None)
    async with app.http as client:
        first = await client.post("/methods", json=package(), headers=trial_headers())
        assert first.status_code == 201, first.text
        method = first.json()
        assert method["method_ref"].startswith("sha256:")
        replay = await client.post("/methods", json=package(), headers=trial_headers())
        assert replay.json() == method
        fetched = await client.get("/methods/" + method["method_ref"], headers=trial_headers())
        assert fetched.json() == method


async def test_artifact_upload_is_content_addressed(tmp_path):
    app = build_app(tmp_path, None)
    async with app.http as client:
        response = await client.post(
            "/method-artifacts",
            json={
                "contract_version": "custom-method-v1",
                "media_type": "application/json",
                "content_base64": base64.b64encode(b'{"x":1}').decode(),
            },
            headers=trial_headers(),
        )
        assert response.status_code == 201, response.text
        artifact = response.json()
        got = await client.get(
            "/method-artifacts/" + artifact["artifact_ref"], headers=trial_headers()
        )
        assert got.json() == artifact


async def test_method_identity_and_artifacts_are_caller_scoped(tmp_path):
    app = build_app(tmp_path, None)
    async with app.http as client:
        method = (await client.post("/methods", json=package(), headers=trial_headers())).json()
        other = {**trial_headers(), "Authorization": "Bearer " + TRIAL_TOKEN_2}
        hidden = await client.get("/methods/" + method["method_ref"], headers=other)
        assert hidden.status_code == 404
        mismatch = await client.post(
            "/methods",
            json=package(),
            headers={
                **trial_headers(),
                "X-Expected-Digest": "sha256:" + "0" * 64,
            },
        )
        assert mismatch.status_code == 422
        assert mismatch.json()["error"]["code"] == "METHOD_DIGEST_MISMATCH"


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object"},
        {
            "type": "object",
            "additionalProperties": False,
            "$schema": "http://json-schema.org/draft-07/schema#",
        },
        {"type": "object", "additionalProperties": False, "$ref": "https://invalid.test/schema"},
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {"x": {"pattern": "(a+)+"}},
        },
        {"type": "object", "additionalProperties": False, "allOf": [{"default": {}}]},
    ],
)
async def test_method_schema_rejects_unbounded_or_ambiguous_features(tmp_path, schema):
    app = build_app(tmp_path, None)
    async with app.http as client:
        response = await client.post(
            "/methods", json=package(parameters_schema=schema), headers=trial_headers()
        )
    assert response.status_code == 422


async def test_unknown_parameters_and_missing_capability_fail_before_admission(tmp_path):
    app = build_app(tmp_path, None)
    seed_worker(app, execution_class="cpu")
    async with app.http as client:
        method = (await client.post("/methods", json=package(), headers=trial_headers())).json()
        bad = await client.post(
            "/method-evaluations",
            json={
                "method_ref": method["method_ref"],
                "parameters": {"typo": 1},
            },
            headers=trial_headers(),
        )
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_METHOD_PARAMETERS"
        unsupported = (
            await client.post(
                "/methods",
                json=package(
                    requirements={
                        "runtime": "worker-python-v1",
                        "capabilities": ["unavailable-tool"],
                    }
                ),
                headers=trial_headers(),
            )
        ).json()
        bad = await client.post(
            "/method-evaluations",
            json={"method_ref": unsupported["method_ref"]},
            headers=trial_headers(),
        )
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "ENVIRONMENT_UNAVAILABLE"


async def test_alias_retry_recovers_frozen_admission_after_alias_changes(tmp_path):
    app = build_app(tmp_path, None)
    seed_worker(app, execution_class="cpu")
    async with app.http as client:
        first = (
            await client.post(
                "/methods",
                json=package("def run(request): return {'passed': True}"),
                headers=trial_headers(),
            )
        ).json()
        second = (
            await client.post(
                "/methods",
                json=package("def run(request): return {'passed': False}"),
                headers=trial_headers(),
            )
        ).json()
        await client.put(
            "/method-aliases/current",
            json={"method_ref": first["method_ref"]},
            headers=trial_headers(),
        )
        submission = {"method_ref": "current", "parameters": {"threshold": 0}}
        admitted = await client.post(
            "/method-evaluations", json=submission, headers=trial_headers()
        )
        assert admitted.status_code == 202, admitted.text
        await client.put(
            "/method-aliases/current",
            json={"method_ref": second["method_ref"]},
            headers=trial_headers(),
        )
        recovered = await client.post(
            "/method-evaluations", json=submission, headers=trial_headers()
        )
        assert recovered.json() == admitted.json()
        conflict = await client.post(
            "/method-evaluations",
            json={
                **submission,
                "parameters": {"threshold": 2},
            },
            headers=trial_headers(),
        )
        assert conflict.status_code == 409


async def test_queued_method_cancellation_is_terminal_and_idempotent(tmp_path):
    app = build_app(tmp_path, None)
    seed_worker(app, execution_class="cpu")
    async with app.http as client:
        method = (await client.post("/methods", json=package(), headers=trial_headers())).json()
        admitted = await client.post(
            "/method-evaluations",
            json={"method_ref": method["method_ref"]},
            headers=trial_headers(),
        )
        assert admitted.status_code == 202, admitted.text
        url = admitted.headers["Location"]
        cancelled = await client.post(url + "/cancel", headers=trial_headers())
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["state"] == "cancelled"
        assert cancelled.json()["result"]["method"]["error"]["code"] == "CANCELLED"
        again = await client.post(url + "/cancel", headers=trial_headers())
        assert again.json() == cancelled.json()


async def test_running_cancel_waits_for_cleanup_then_fences_old_attempt(tmp_path):
    app = build_app(tmp_path, None)
    seed_worker(app, execution_class="cpu")
    async with app.http as client:
        method = (await client.post("/methods", json=package(), headers=trial_headers())).json()
        admitted = await client.post(
            "/method-evaluations",
            json={"method_ref": method["method_ref"]},
            headers=trial_headers(),
        )
        worker = WorkerIdentity(
            new_worker_id(),
            app.settings.evaluator_build,
            algorithms(app.settings),
            execution_class="cpu",
        )
        lease = app.store.claim_next(worker)
        assert lease is not None
        url = admitted.headers["Location"]
        intent = await client.post(url + "/cancel", headers=trial_headers())
        assert intent.status_code == 202
        assert intent.json()["state"] == "running" and intent.json()["cancel_requested"]
        assert not app.store.renew_lease(lease)
        assert app.store.is_cancel_requested(lease)
        assert app.store.finish_cancelled(lease)
        assert not app.store.finish_cancelled(lease)
        done = await client.get(url, headers=trial_headers())
        assert done.json()["state"] == "cancelled"


async def test_same_artifact_bytes_cannot_change_sealed_media_type(tmp_path):
    app = build_app(tmp_path, None)
    data = {"content_base64": base64.b64encode(b"abc").decode(), "media_type": "text/plain"}
    async with app.http as client:
        assert (
            await client.post("/method-artifacts", json=data, headers=trial_headers())
        ).status_code == 201
        other = await client.post(
            "/method-artifacts", json={**data, "media_type": "x/other"}, headers=trial_headers()
        )
        assert other.status_code == 409


async def test_public_identity_preserves_zero_false_null_and_defaults(tmp_path):
    app = build_app(tmp_path, None)
    seed_worker(app, execution_class="cpu")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "zero": {"type": "number", "default": 5},
            "flag": {"type": "boolean", "default": True},
            "nullable": {"type": ["number", "null"], "default": 7},
            "absent": {"type": "integer", "default": 9},
        },
    }
    async with app.http as client:
        method = (
            await client.post(
                "/methods", json=package(parameters_schema=schema), headers=trial_headers()
            )
        ).json()
        response = await client.post(
            "/method-evaluations",
            json={
                "method_ref": method["method_ref"],
                "parameters": {"zero": 0, "flag": False, "nullable": None},
            },
            headers=trial_headers(),
        )
        assert response.status_code == 202, response.text
        identity = response.json()["method_identity"]
        assert identity["requested_parameters"] == {"zero": 0, "flag": False, "nullable": None}
        assert identity["effective_parameters"] == {
            "zero": 0,
            "flag": False,
            "nullable": None,
            "absent": 9,
        }
        cancelled = await client.post(
            response.headers["Location"] + "/cancel", headers=trial_headers()
        )
        assert cancelled.json()["method_identity"] == identity


async def test_cancelled_lost_worker_is_not_requeued(tmp_path):
    app = build_app(tmp_path, None)
    seed_worker(app, execution_class="cpu")
    async with app.http as client:
        method = (await client.post("/methods", json=package(), headers=trial_headers())).json()
        response = await client.post(
            "/method-evaluations",
            json={"method_ref": method["method_ref"]},
            headers=trial_headers(),
        )
        worker = WorkerIdentity(
            new_worker_id(),
            app.settings.evaluator_build,
            algorithms(app.settings),
            execution_class="cpu",
        )
        lease = app.store.claim_next(worker)
        await client.post(response.headers["Location"] + "/cancel", headers=trial_headers())
        app.clock.advance_ms((app.settings.lease_seconds + 1) * 1000)
        recovered = app.store.recover_expired_leases()
        assert recovered.requeued == 0
        result = (await client.get(response.headers["Location"], headers=trial_headers())).json()
        assert result["state"] == "cancelled"
        assert result["method_identity"]["method_ref"] == method["method_ref"]
        assert not app.store.finish_cancelled(lease)


async def test_method_artifacts_are_attempt_bound_across_recovery(tmp_path):
    from ascend_op_eval.methods.contracts import StoredArtifact

    app = build_app(tmp_path, None)
    seed_worker(app, execution_class="cpu")
    async with app.http as client:
        method = (await client.post("/methods", json=package(), headers=trial_headers())).json()
        response = await client.post(
            "/method-evaluations",
            json={"method_ref": method["method_ref"]},
            headers=trial_headers(),
        )
        worker = WorkerIdentity(
            new_worker_id(),
            app.settings.evaluator_build,
            algorithms(app.settings),
            execution_class="cpu",
        )
        first = app.store.claim_next(worker)
        old = StoredArtifact.from_bytes(b"first", "text/plain")
        assert app.store.save_method_artifacts(first, {"trace.txt": old})
        artifact_url = response.headers["Location"] + "/artifacts/trace.txt"
        assert (await client.get(artifact_url, headers=trial_headers())).json() == old.model_dump()
        app.clock.advance_ms((app.settings.lease_seconds + 1) * 1000)
        assert app.store.recover_expired_leases().requeued == 1
        assert (await client.get(artifact_url, headers=trial_headers())).status_code == 404
        second = app.store.claim_next(worker)
        assert second is not None
        assert not app.store.save_method_artifacts(first, {"trace.txt": old})
        fresh = StoredArtifact.from_bytes(b"second", "text/plain")
        assert app.store.save_method_artifacts(second, {"trace.txt": fresh})
        assert (
            await client.get(artifact_url, headers=trial_headers())
        ).json() == fresh.model_dump()


async def test_alias_resolution_race_returns_the_admitted_request(tmp_path, monkeypatch):
    app = build_app(tmp_path, None)
    seed_worker(app, execution_class="cpu")
    instance = app.app.state.context.instance
    original_submit = instance.submit
    async with app.http as client:
        first = (
            await client.post("/methods", json=package("first = True"), headers=trial_headers())
        ).json()
        second = (
            await client.post("/methods", json=package("second = True"), headers=trial_headers())
        ).json()
        await client.put(
            "/method-aliases/current",
            json={"method_ref": first["method_ref"]},
            headers=trial_headers(),
        )

        def concurrent_winner(request, caller, **kwargs):
            instance.methods.alias(caller, "current", second["method_ref"])
            frozen = instance.methods.freeze(caller, request.method_execution.submission)
            original_submit(
                request.model_copy(update={"method_execution": frozen}), caller, **kwargs
            )
            return original_submit(request, caller, **kwargs)

        monkeypatch.setattr(instance, "submit", concurrent_winner)
        submission = {"method_ref": "current"}
        response = await client.post(
            "/method-evaluations", json=submission, headers=trial_headers()
        )
        assert response.status_code == 202, response.text
        assert response.json()["method_identity"]["method_ref"] == second["method_ref"]
        different_session = await client.post(
            "/method-evaluations", json=submission, headers=trial_headers(session="other")
        )
        assert different_session.status_code == 409


async def test_runtime_discovery_does_not_claim_unconfigured_isolation(tmp_path):
    app = build_app(tmp_path, None)
    app.settings.method_capabilities = ["python", "process-isolation"]
    seed_worker(app, execution_class="cpu")
    async with app.http as client:
        runtimes = (await client.get("/method-runtimes", headers=trial_headers())).json()
        assert runtimes["runtimes"][0]["capabilities"] == ["python"]
        method = (
            await client.post(
                "/methods",
                json=package(
                    requirements={
                        "capabilities": ["process-isolation"],
                    }
                ),
                headers=trial_headers(),
            )
        ).json()
        response = await client.post(
            "/method-evaluations",
            json={"method_ref": method["method_ref"]},
            headers=trial_headers(),
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "ENVIRONMENT_UNAVAILABLE"
