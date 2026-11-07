"""Pinned external examples traverse real admission, CPU worker and artifact recovery."""

import base64
import importlib.util
import json
from pathlib import Path

import pytest
from test_api import trial_headers
from test_compile_check import app_with_precheck, cpu_worker

ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = (
    ROOT / "plugins/custom-method-eval/skills/custom-method-eval/scripts/custom_method_eval.py"
)
spec = importlib.util.spec_from_file_location("packaged_method_cli", CLI_PATH)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "kind,params,outcome,value",
    [
        ("checker", {}, "failed", None),
        ("checker", {"custom_thresholds": {"float32": 0.1}}, "passed", None),
        ("measurement", {}, "completed", 200),
    ],
)
async def test_pinned_examples_execute_as_methods_over_public_api(
    tmp_path,
    release_catalog_files,
    kind,
    params,
    outcome,
    value,
):
    app = app_with_precheck(tmp_path, release_catalog_files)
    worker = cpu_worker(app)
    example = ROOT / "adapters/cannbench/src/ascend_op_eval_adapter_cannbench/bundle"
    package = cli.package_manifest(example / (kind + ".method.json"))
    names = ["actual", "reference", "native"] if kind == "checker" else ["kernel_details"]
    async with app.http as client:
        registered = await client.post("/methods", headers=trial_headers(), json=package)
        assert registered.status_code == 201, registered.text
        refs = {}
        for name in names:
            suffix, media_type = (
                (".json", "application/json") if kind == "checker" else (".csv", "text/csv")
            )
            content = (example / (name + suffix)).read_bytes()
            stored = await client.post(
                "/method-artifacts",
                headers=trial_headers(),
                json={
                    "contract_version": "custom-method-v1",
                    "media_type": media_type,
                    "content_base64": base64.b64encode(content).decode(),
                },
            )
            assert stored.status_code == 201, stored.text
            refs[name] = stored.json()["artifact_ref"]
        submitted = await client.post(
            "/method-evaluations",
            headers=trial_headers(),
            json={
                "contract_version": "custom-method-v1",
                "method_ref": registered.json()["method_ref"],
                "parameters": params,
                "inputs": refs,
            },
        )
        assert submitted.status_code == 202, submitted.text
        assert worker.run_once()
        resource = (await client.get(submitted.headers["Location"], headers=trial_headers())).json()
        result = resource["result"]["method"]
        assert result["status"] == "succeeded", resource
        data = result["data"]
        assert data["outcome"] == outcome, data
        assert data["authority"] == "caller_method"
        assert resource["result"]["correctness"] is None
        assert data["method_ref"] == registered.json()["method_ref"]
        if value is not None:
            assert data["report"]["value"] == value
            artifact_name = "measurement.json"
        else:
            assert data["report"]["passed"] is (outcome == "passed")
            artifact_name = "comparison.json"
        saved = await client.get(
            submitted.headers["Location"] + "/artifacts/" + artifact_name, headers=trial_headers()
        )
        assert saved.status_code == 200, saved.text
        assert json.loads(cli.verify_artifact(saved.json())) == data["report"]
        frozen = await client.get(
            submitted.headers["Location"] + "/method-materials", headers=trial_headers()
        )
        assert frozen.status_code == 200
        assert frozen.json()["inputs"][names[0]]["artifact_ref"] == refs[names[0]]
