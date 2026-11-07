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
