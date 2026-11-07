"""Deployment-owned registry limits cover each caller's immutable storage."""

import base64

import pytest
from test_api import TRIAL_TOKEN_2, build_app, trial_headers
from test_method_registry_api import package

pytestmark = pytest.mark.anyio


def upload(value):
    return {"media_type": "text/plain", "content_base64": base64.b64encode(value).decode()}


async def test_packages_artifacts_and_aliases_share_a_record_budget(tmp_path):
    app = build_app(tmp_path, None)
    app.settings.method_registry_max_records = 3
    async with app.http as client:
        method = (await client.post("/methods", json=package(), headers=trial_headers())).json()
        assert (
            await client.post("/method-artifacts", json=upload(b"one"), headers=trial_headers())
        ).status_code == 201
        alias = {"method_ref": method["method_ref"]}
        assert (
            await client.put("/method-aliases/current", json=alias, headers=trial_headers())
        ).status_code == 200
        refused = await client.post(
            "/method-artifacts", json=upload(b"two"), headers=trial_headers()
        )
        assert refused.status_code == 413, refused.text
        assert refused.json()["error"]["code"] == "METHOD_REGISTRY_LIMIT_EXCEEDED"


async def test_reuploads_are_free_and_other_callers_have_independent_budget(tmp_path):
    app = build_app(tmp_path, None)
    app.settings.method_registry_max_records = 1
    async with app.http as client:
        first = await client.post("/method-artifacts", json=upload(b"one"), headers=trial_headers())
        repeated = await client.post(
            "/method-artifacts", json=upload(b"one"), headers=trial_headers()
        )
        assert repeated.status_code == 201 and repeated.json() == first.json()
        assert (
            await client.post("/method-artifacts", json=upload(b"two"), headers=trial_headers())
        ).status_code == 413
        other = {**trial_headers(), "Authorization": "Bearer " + TRIAL_TOKEN_2}
        assert (
            await client.post("/method-artifacts", json=upload(b"two"), headers=other)
        ).status_code == 201


async def test_registry_bytes_are_bounded_separately_from_record_count(tmp_path):
    app = build_app(tmp_path, None)
    app.settings.method_registry_max_bytes = 400
    async with app.http as client:
        first = await client.post("/method-artifacts", json=upload(b"one"), headers=trial_headers())
        assert first.status_code == 201, first.text
        second = await client.post(
            "/method-artifacts", json=upload(b"two"), headers=trial_headers()
        )
        assert second.status_code == 413, second.text


async def test_alias_update_does_not_allocate_another_record(tmp_path):
    app = build_app(tmp_path, None)
    app.settings.method_registry_max_records = 3
    async with app.http as client:
        one = (
            await client.post("/methods", json=package("first = True"), headers=trial_headers())
        ).json()
        two = (
            await client.post("/methods", json=package("second = True"), headers=trial_headers())
        ).json()
        assert (
            await client.put(
                "/method-aliases/current",
                json={"method_ref": one["method_ref"]},
                headers=trial_headers(),
            )
        ).status_code == 200
        changed = await client.put(
            "/method-aliases/current",
            json={"method_ref": two["method_ref"]},
            headers=trial_headers(),
        )
        assert changed.status_code == 200, changed.text
        assert (await client.get("/methods/current", headers=trial_headers())).json() == two
        assert (
            await client.put(
                "/method-aliases/another",
                json={"method_ref": one["method_ref"]},
                headers=trial_headers(),
            )
        ).status_code == 413


async def test_expired_registry_data_releases_its_quota(tmp_path):
    from ascend_op_eval.serialization import canonical_json_bytes

    app = build_app(tmp_path, None)
    app.settings.method_registry_max_records = 1
    async with app.http as client:
        first = await client.post("/method-artifacts", json=upload(b"one"), headers=trial_headers())
        assert first.status_code == 201
        record = canonical_json_bytes(first.json())
        # Simulate Redis expiring this data key while the caller ledger remains.
        # Assertions below observe the public artifact/registration interface.
        for key in app.store._r.scan_iter():
            if app.store._r.type(key) == b"string" and app.store._r.get(key) == record:
                app.store._r.expire(key, 0)
        assert (
            await client.get(
                "/method-artifacts/" + first.json()["artifact_ref"], headers=trial_headers()
            )
        ).status_code == 404
        next_artifact = await client.post(
            "/method-artifacts", json=upload(b"two"), headers=trial_headers()
        )
        assert next_artifact.status_code == 201, next_artifact.text


async def test_concurrent_uploads_cannot_overbook_record_budget(tmp_path):
    import asyncio

    app = build_app(tmp_path, None)
    app.settings.method_registry_max_records = 1
    async with app.http as client:
        responses = await asyncio.gather(
            *[
                client.post(
                    "/method-artifacts", json=upload(bytes([number])), headers=trial_headers()
                )
                for number in range(8)
            ]
        )
    assert [response.status_code for response in responses].count(201) == 1
    assert [response.status_code for response in responses].count(413) == 7


async def test_admitted_materials_remain_readable_after_registry_expiry(tmp_path):
    from ascend_op_eval.serialization import canonical_json_bytes
    from test_api import seed_worker

    app = build_app(tmp_path, None)
    seed_worker(app, execution_class="cpu")
    body = package(inputs={"actual": {"media_type": "text/plain"}})
    async with app.http as client:
        artifact = (
            await client.post("/method-artifacts", json=upload(b"inputs"), headers=trial_headers())
        ).json()
        method = (await client.post("/methods", json=body, headers=trial_headers())).json()
        admitted = await client.post(
            "/method-evaluations",
            json={
                "method_ref": method["method_ref"],
                "inputs": {"actual": artifact["artifact_ref"]},
            },
            headers=trial_headers(),
        )
        assert admitted.status_code == 202, admitted.text
        values = {canonical_json_bytes(artifact), canonical_json_bytes(method)}
        for key in app.store._r.scan_iter():
            if app.store._r.type(key) == b"string" and app.store._r.get(key) in values:
                app.store._r.expire(key, 0)
        assert (
            await client.get("/methods/" + method["method_ref"], headers=trial_headers())
        ).status_code == 404
        materials = await client.get(
            admitted.headers["Location"] + "/method-materials", headers=trial_headers()
        )
        assert materials.status_code == 200, materials.text
        assert materials.json()["package"]["files"] == body["files"]
        assert materials.json()["inputs"]["actual"] == artifact
        other = {**trial_headers(), "Authorization": "Bearer " + TRIAL_TOKEN_2}
        assert (
            await client.get(admitted.headers["Location"] + "/method-materials", headers=other)
        ).status_code == 404


async def test_required_outputs_cannot_exceed_declared_count_budget(tmp_path):
    from test_api import seed_worker

    app = build_app(tmp_path, None)
    seed_worker(app, execution_class="cpu")
    async with app.http as client:
        method = (
            await client.post(
                "/methods",
                json=package(
                    output_artifacts={
                        "trace.csv": {"required": True},
                    }
                ),
                headers=trial_headers(),
            )
        ).json()
        response = await client.post(
            "/method-evaluations",
            json={
                "method_ref": method["method_ref"],
                "limits": {"artifact_count": 0},
            },
            headers=trial_headers(),
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_METHOD_LIMITS"
