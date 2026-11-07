"""External methods execute through the same public admission and worker lifecycle."""

import base64
import hashlib
import json
from pathlib import Path

import pytest
from test_api import trial_headers
from test_compile_check import app_with_precheck, cpu_worker

pytestmark = pytest.mark.anyio

CHECKER = '''
import json
from pathlib import Path

def run(request):
    actual = json.loads(Path(request["inputs"]["actual"]["path"]).read_text())
    reference = json.loads(Path(request["inputs"]["reference"]["path"]).read_text())
    params = request["parameters"]
    errors = [abs(a - b) for a, b in zip(actual, reference)]
    maximum = max(errors, default=0)
    passed = len(actual) == len(reference) and maximum <= (0 if params["exact"] else params["atol"])
    if params["cap"] is not None:
        passed = passed and maximum <= params["cap"]
    Path(request["output_dir"], "errors.json").write_text(json.dumps(errors))
    return {"passed": passed, "effective": params}
'''


def checker_package(source=CHECKER):
    return {
        "contract_version": "custom-method-v1",
        "descriptor": {
            "name": "fixture-checker", "version": "1", "kind": "checker",
            "entrypoint": "checker:run",
            "parameters_schema": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "atol": {"type": "number", "minimum": 0, "default": 0},
                    "exact": {"type": "boolean", "default": False},
                    "cap": {"type": ["number", "null"], "minimum": 0, "default": None},
                },
            },
            "inputs": {name: {"media_type": "application/json"}
                       for name in ("actual", "reference")},
            "output_schema": {
                "type": "object", "required": ["passed", "effective"],
                "properties": {"passed": {"type": "boolean"}, "effective": {"type": "object"}},
                "additionalProperties": False,
            },
        },
        "files": {"checker.py": source},
    }


async def upload_json(client, value):
    response = await client.post("/method-artifacts", headers=trial_headers(), json={
        "contract_version": "custom-method-v1", "media_type": "application/json",
        "content_base64": base64.b64encode(json.dumps(value).encode()).decode(),
    })
    assert response.status_code in (200, 201), response.text
    return response.json()["artifact_ref"]


async def prepare_checker(client):
    registered = await client.post("/methods", headers=trial_headers(), json=checker_package())
    assert registered.status_code in (200, 201), registered.text
    return registered.json()["method_ref"], {
        "actual": await upload_json(client, [10.125]),
        "reference": await upload_json(client, [10.0]),
    }


async def test_checker_parameters_and_output_artifacts_survive_worker_cleanup(
    tmp_path, release_catalog_files,
):
    app = app_with_precheck(tmp_path, release_catalog_files)
    worker = cpu_worker(app)
    async with app.http as client:
        method_ref, inputs = await prepare_checker(client)
        ids = []
        for index, (parameters, outcome) in enumerate([
            ({"atol": 0.25, "exact": False, "cap": None}, "passed"),
            ({"atol": 0.0625}, "failed"),
            ({"atol": 0.25, "exact": True}, "failed"),
            ({"atol": 0.25, "cap": 0}, "failed"),
        ]):
            response = await client.post(
                "/method-evaluations", headers=trial_headers(key=str(index)),
                json={"contract_version": "custom-method-v1", "method_ref": method_ref,
                      "parameters": parameters, "inputs": inputs},
            )
            assert response.status_code == 202, response.text
            ids.append(response.json()["evaluation_id"])
            assert worker.run_once()
            record = (await client.get(
                response.headers["Location"], headers=trial_headers(),
            )).json()
            assert record["state"] == "completed", record
            assert record["result"]["provenance"]["correctness_algorithm"] == "custom-method-v1"
            assert record["result"]["provenance"]["reference_device_policy"] is None
            assert record["result"]["provenance"]["grade_eligible"] is False
            check = record["result"]["method"]
            assert check["status"] == "succeeded", check
            data = check["data"]
            assert data["outcome"] == outcome, data
            assert data["authority"] == "caller_method"
            assert data["method_ref"] == method_ref
            assert data["requested_parameters"] == parameters
            assert data["report"]["effective"] == data["effective_parameters"]
            assert data["effective_parameters"]["cap"] == (None if index < 3 else 0)
            artifact = await client.get(
                f"/evaluations/{ids[-1]}/artifacts/errors.json", headers=trial_headers(),
            )
            assert artifact.status_code == 200, artifact.text
            blob = artifact.json()
            content = base64.b64decode(blob["content_base64"])
            assert json.loads(content) == [0.125]
            assert hashlib.sha256(content).hexdigest() == blob["sha256"]
        assert len(set(ids)) == 4


def example_package(relative):
    directory = Path(__file__).resolve().parents[1] / "examples" / "custom_methods" / relative
    package = json.loads((directory / "method.json").read_text())
    package["files"] = {name: (directory / name).read_bytes().decode("utf-8")
                        for name in package["files"]}
    return package


async def test_external_measurement_controls_real_warmup_and_invocation_counts(
    tmp_path, release_catalog_files,
):
    app = app_with_precheck(tmp_path, release_catalog_files)
    worker = cpu_worker(app)
    async with app.http as client:
        registered = await client.post("/methods", headers=trial_headers(),
                                       json=example_package("cpu_timer"))
        assert registered.status_code == 201, registered.text
        method_ref = registered.json()["method_ref"]
        for index, (warmup, repeat, aggregation, calls) in enumerate([
            (0, 3, "mean", 3), (2, 4, "median", 6),
        ]):
            response = await client.post(
                "/method-evaluations", headers=trial_headers(key=f"timer-{index}"), json={
                    "method_ref": method_ref,
                    "parameters": {"warmup": warmup, "repeat": repeat, "aggregation": aggregation},
                },
            )
            assert response.status_code == 202, response.text
            assert worker.run_once()
            record = (await client.get(
                response.headers["Location"], headers=trial_headers(),
            )).json()
            data = record["result"]["method"]["data"]
            assert data["outcome"] == "completed", data
            report = data["report"]
            assert report["metric"] == "cpu_call_wall_time"
            assert report["unit"] == "ns" and report["value"] > 0
            assert len(report["samples"]) == repeat
            assert report["calls"] == calls
            assert report["checksum"] == 499500
            assert report["aggregation"] == aggregation
            assert data["method_ref"] == method_ref
