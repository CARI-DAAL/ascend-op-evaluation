"""Native projects cross durable HTTP admission and a real CPU build attempt."""

import sys

import pytest
from test_api import post, trial_headers
from test_compile_check import app_with_precheck, cpu_worker
from test_openapi import body_schema, validate

pytestmark = pytest.mark.anyio


def native_payload(build_code):
    return {
        "definition": {"inputs": {}, "reference": "def run(): return 1"},
        "workloads": [{"inputs": {}}],
        "candidate": {
            "kind": "native",
            "files": {"build.py": build_code, "entry.py": "def run(): return 1\n"},
            "build": [sys.executable, "build.py"],
            "entrypoint": "entry:run",
        },
        "checks": ["compile"],
    }


async def test_native_build_runs_after_admission_and_recovers_once(
    tmp_path, release_catalog_files,
):
    app = app_with_precheck(tmp_path, release_catalog_files)
    worker = cpu_worker(app)
    marker = tmp_path / "build-count"
    payload = native_payload(
        "from pathlib import Path\n"
        f"p = Path({str(marker)!r})\n"
        "p.write_text(p.read_text() + 'built\\n' if p.exists() else 'built\\n')\n"
        "print('native build completed')\n"
    )
    async with app.http as client:
        accepted = await post(client, payload)
        assert accepted.status_code == 202, accepted.text
        assert not marker.exists()
        assert worker.run_once()
        result = await client.get(accepted.headers["Location"], headers=trial_headers())
        assert result.status_code == 200
        record = result.json()
        assert record["state"] == "completed"
        assert record["result"]["compile"]["data"]["outcome"] == "compiled"
        assert "native build completed" in str(record["result"]["native_build"])
        replay = await post(client, payload)
        assert replay.json() == record
        assert not worker.run_once()
        assert marker.read_text() == "built\n"


async def test_native_compile_failure_retains_diagnostics(
    tmp_path, release_catalog_files,
):
    app = app_with_precheck(tmp_path, release_catalog_files)
    worker = cpu_worker(app)
    payload = native_payload(
        "import sys\nprint('native compiler diagnostic', file=sys.stderr)\nsys.exit(2)\n"
    )
    async with app.http as client:
        accepted = await post(client, payload)
        assert accepted.status_code == 202, accepted.text
        assert worker.run_once()
        record = (await client.get(
            accepted.headers["Location"], headers=trial_headers(),
        )).json()
    assert record["result"]["compile"]["data"]["outcome"] == "compile_error"
    assert "native compiler diagnostic" in str(record["result"]["native_build"])


async def test_native_source_change_conflicts_with_admitted_idempotency_key(
    tmp_path, release_catalog_files,
):
    app = app_with_precheck(tmp_path, release_catalog_files)
    cpu_worker(app)
    async with app.http as client:
        original = await post(client, native_payload("print('one')\n"))
        assert original.status_code == 202, original.text
        changed = await post(client, native_payload("print('two')\n"))
        assert changed.status_code == 409


async def test_native_request_is_described_by_live_openapi(tmp_path, release_catalog_files):
    app = app_with_precheck(tmp_path, release_catalog_files)
    async with app.http as client:
        document = (await client.get("/openapi.json")).json()
    validate(document, body_schema(document["paths"]["/evaluations"]["post"]),
             native_payload("print('build')\n"))


async def test_native_build_progress_is_scoped_to_its_attempt(tmp_path, release_catalog_files):
    from ascend_op_eval.api.contract import NativeBuildEvidence

    app = app_with_precheck(tmp_path, release_catalog_files)
    worker = cpu_worker(app)
    async with app.http as client:
        submitted = await post(client, native_payload("print('build')"))
        path = submitted.headers["Location"] + "/progress"
        lease = app.store.claim_next(worker.identity)
        before = (await client.get(path, headers=trial_headers())).json()
        assert "native_build" not in before
        evidence = NativeBuildEvidence(outcome="compiled", duration_ms=2, exit_code=0)
        assert app.store.save_native_build(lease, evidence)
        ready = (await client.get(path, headers=trial_headers())).json()
        assert ready["native_build"] == evidence.model_dump(mode="json")
        assert ready["progress_revision"] > before["progress_revision"]
        assert ready["completed_checks"]["compile"] is None
        app.clock.advance_ms(app.settings.lease_seconds * 1000 + 1)
        assert app.store.recover_expired_leases().requeued == 1
        assert "native_build" not in (await client.get(path, headers=trial_headers())).json()
        assert app.store.claim_next(worker.identity).attempt_id != lease.attempt_id
        assert "native_build" not in (await client.get(path, headers=trial_headers())).json()


async def test_source_only_preflight_runs_native_build(tmp_path, release_catalog_files):
    app = app_with_precheck(tmp_path, release_catalog_files)
    worker = cpu_worker(app)
    project = native_payload("print('CPU build')")["candidate"]
    async with app.http as client:
        submitted = await client.post("/preflight", json={"candidate": project},
                                      headers=trial_headers())
        assert submitted.status_code == 202, submitted.text
        assert worker.run_once()
        result = (await client.get(submitted.headers["Location"], headers=trial_headers())).json()
        build = result["result"]["native_build"]
        assert build["outcome"] == "compiled" and build["artifact_sha256"]
        assert result["result"]["correctness"] is None
