"""Cancellation crosses the real HTTP, lease keeper and subprocess lifecycle."""

import threading
import time

import pytest
from test_api import trial_headers
from test_compile_check import app_with_precheck, cpu_worker

pytestmark = pytest.mark.anyio


async def test_running_method_cancel_kills_child_before_terminal_ack(
    tmp_path, release_catalog_files
):
    app = app_with_precheck(tmp_path, release_catalog_files)
    worker = cpu_worker(app)
    marker = tmp_path / "child-heartbeat"
    child = (
        "import sys,time; from pathlib import Path; p=Path(sys.argv[1]); i=0\n"
        "while True:\n p.write_text(str(i)); i+=1; time.sleep(0.02)"
    )
    source = f"""
import subprocess,sys,time

def run(request):
    subprocess.Popen([sys.executable, '-c', {child!r}, {str(marker)!r}])
    time.sleep(30)
    return {{'passed':True}}
"""
    package = {
        "descriptor": {
            "name": "cancel-fixture",
            "version": "1",
            "kind": "checker",
            "entrypoint": "checker:run",
            "parameters_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        "files": {"checker.py": source},
    }
    async with app.http as client:
        registered = await client.post("/methods", headers=trial_headers(), json=package)
        assert registered.status_code in (200, 201), registered.text
        submitted = await client.post(
            "/method-evaluations",
            headers=trial_headers(),
            json={
                "contract_version": "custom-method-v1",
                "method_ref": registered.json()["method_ref"],
            },
        )
        assert submitted.status_code == 202, submitted.text
        location = submitted.headers["Location"]
        thread = threading.Thread(target=worker.run_once, daemon=True)
        thread.start()
        for _ in range(200):
            if marker.exists():
                break
            time.sleep(0.01)
        assert marker.exists(), "method child did not start"
        cancelled = await client.post(location + "/cancel", headers=trial_headers())
        assert cancelled.status_code in (200, 202), cancelled.text
        thread.join(timeout=5)
        assert not thread.is_alive()
        resource = (await client.get(location, headers=trial_headers())).json()
        assert resource["state"] == "cancelled", resource
        assert resource["method_identity"]["method_ref"] == registered.json()["method_ref"]
        after = marker.read_bytes()
        time.sleep(0.15)
        assert marker.read_bytes() == after
        repeated = await client.post(location + "/cancel", headers=trial_headers())
        assert repeated.json()["state"] == "cancelled"
