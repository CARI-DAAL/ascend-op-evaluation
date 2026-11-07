"""Public custom-method regressions found during independent review."""

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_api import trial_headers
from test_compile_check import app_with_precheck, cpu_worker


def package(source, schema=None):
    return {
        "descriptor": {
            "name": "review-method",
            "version": "1",
            "kind": "checker",
            "entrypoint": "checker:run",
            "parameters_schema": schema
            or {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        "files": {"checker.py": source},
    }


@pytest.mark.anyio
async def test_atomic_raw_output_rename_during_live_guard_is_valid(
    tmp_path,
    release_catalog_files,
    monkeypatch,
):
    from ascend_op_eval.execution import method_execution

    app = app_with_precheck(tmp_path, release_catalog_files)
    worker = cpu_worker(app)
    release, renamed = tmp_path / "release", tmp_path / "renamed"
    source = f"""
import time
from pathlib import Path

def run(request):
    temporary=Path(request['output_dir'],'report.tmp')
    temporary.write_text('{{"sample":1}}')
    for _ in range(400):
        if Path({str(release)!r}).exists():break
        time.sleep(0.005)
    assert Path({str(release)!r}).exists()
    temporary.replace(Path(request['output_dir'],'report.json'))
    Path({str(renamed)!r}).touch()
    return {{'passed':True}}
"""
    original_stat = os.stat
    intercepted = []

    def stat_after_atomic_rename(path, *args, **kwargs):
        if path == "report.tmp" and kwargs.get("dir_fd") is not None and not intercepted:
            intercepted.append(True)
            release.touch()
            for _ in range(400):
                if renamed.exists():
                    break
                time.sleep(0.005)
            assert renamed.exists(), "method did not perform its atomic rename"
        return original_stat(path, *args, **kwargs)

    async with app.http as client:
        registered = await client.post("/methods", headers=trial_headers(), json=package(source))
        assert registered.status_code == 201, registered.text
        submitted = await client.post(
            "/method-evaluations",
            headers=trial_headers(),
            json={
                "method_ref": registered.json()["method_ref"],
            },
        )
        assert submitted.status_code == 202, submitted.text
        with monkeypatch.context() as patch:
            patch.setattr(method_execution.os, "stat", stat_after_atomic_rename)
            assert worker.run_once()
        assert intercepted, "the transient disappearance was not exercised"
        record = (await client.get(submitted.headers["Location"], headers=trial_headers())).json()
        result = record["result"]["method"]["data"]
        assert result["outcome"] == "passed", result
        raw = await client.get(
            submitted.headers["Location"] + "/artifacts/report.json", headers=trial_headers()
        )
        assert raw.status_code == 200, raw.text
        assert json.loads(base64.b64decode(raw.json()["content_base64"])) == {"sample": 1}


@pytest.mark.anyio
async def test_dynamic_parameter_members_receive_nested_defaults_in_real_worker(
    tmp_path,
    release_catalog_files,
):
    app = app_with_precheck(tmp_path, release_catalog_files)
    worker = cpu_worker(app)
    source = """
def run(request):
    group=request['parameters']['groups']['float32']
    threshold=group['threshold']
    return {'passed': threshold is None or .2<=threshold, 'effective':group}
"""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["groups"],
        "properties": {
            "groups": {
                "type": "object",
                "additionalProperties": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "threshold": {"type": ["number", "null"], "default": 0.25},
                        "enabled": {"type": "boolean", "default": True},
                        "cap": {"type": ["number", "null"], "default": 3},
                    },
                },
            }
        },
    }
    async with app.http as client:
        registered = await client.post(
            "/methods", headers=trial_headers(), json=package(source, schema)
        )
        assert registered.status_code == 201, registered.text
        for index, (members, outcome, expected) in enumerate(
            [
                ({}, "passed", {"threshold": 0.25, "enabled": True, "cap": 3}),
                (
                    {"threshold": 0, "enabled": False, "cap": None},
                    "failed",
                    {"threshold": 0, "enabled": False, "cap": None},
                ),
                ({"threshold": None}, "passed", {"threshold": None, "enabled": True, "cap": 3}),
            ]
        ):
            submitted = await client.post(
                "/method-evaluations",
                headers=trial_headers(key=f"dynamic-{index}"),
                json={
                    "method_ref": registered.json()["method_ref"],
                    "parameters": {"groups": {"float32": members}},
                },
            )
            assert submitted.status_code == 202, submitted.text
            assert worker.run_once()
            record = (
                await client.get(submitted.headers["Location"], headers=trial_headers())
            ).json()
            result = record["result"]["method"]["data"]
            assert result["outcome"] == outcome, result
            assert result["effective_parameters"]["groups"]["float32"] == expected
            assert result["report"]["effective"] == expected


def test_runtime_module_imports_in_a_fresh_interpreter():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from ascend_op_eval.execution.method_execution import execute_method; "
            "print(callable(execute_method))",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_final_collection_remains_strict_when_a_file_disappears(tmp_path, monkeypatch):
    from ascend_op_eval.execution import method_execution
    from ascend_op_eval.methods.contracts import MethodLimits

    (tmp_path / "report.json").write_text("{}")
    original_stat = os.stat

    def disappeared(path, *args, **kwargs):
        if path == "report.json" and kwargs.get("dir_fd") is not None:
            raise FileNotFoundError("simulated concurrent disappearance")
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(method_execution.os, "stat", disappeared)
        assert method_execution.collect_outputs(tmp_path, MethodLimits(), read=False) == {}
        with pytest.raises(FileNotFoundError):
            method_execution.collect_outputs(tmp_path, MethodLimits(), read=True)


@pytest.mark.parametrize("kind", ["symlink", "fifo", "oversize"])
def test_live_guard_still_rejects_unsafe_or_oversized_outputs(tmp_path, kind):
    from ascend_op_eval.execution.method_execution import OutputProtocolError, collect_outputs
    from ascend_op_eval.methods.contracts import MethodLimits

    path = tmp_path / "unsafe"
    if kind == "symlink":
        path.symlink_to(tmp_path / "absent")
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.write_bytes(b"12345")
    with pytest.raises(OutputProtocolError):
        collect_outputs(tmp_path, MethodLimits(artifact_bytes=4), read=False)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), object()])
def test_explicit_json_schema_keeps_finite_json_runtime_validation(value):
    from ascend_op_eval.methods.contracts import MethodSubmission
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MethodSubmission(method_ref="sha256:" + "a" * 64, parameters={"nested": [value]})


@pytest.mark.anyio
async def test_alias_and_runtime_responses_match_explicit_live_schemas(
    tmp_path, release_catalog_files
):
    from test_openapi import response_schema, validate

    app = app_with_precheck(tmp_path, release_catalog_files)
    async with app.http as client:
        registered = await client.post(
            "/methods",
            headers=trial_headers(),
            json=package("def run(request): return {'passed':True}\n"),
        )
        assert registered.status_code == 201, registered.text
        alias = await client.put(
            "/method-aliases/latest",
            headers=trial_headers(),
            json={
                "method_ref": registered.json()["method_ref"],
            },
        )
        runtimes = await client.get("/method-runtimes", headers=trial_headers())
        document = (await client.get("/openapi.json")).json()
    for path, method, response in [
        ("/method-aliases/{alias}", "put", alias),
        ("/method-runtimes", "get", runtimes),
    ]:
        assert response.status_code == 200, response.text
        schema = response_schema(document["paths"][path][method], 200)
        assert schema
        validate(document, schema, response.json())


@pytest.mark.anyio
async def test_dynamic_defaults_cannot_expand_beyond_parameter_budget(
    tmp_path, release_catalog_files
):
    app = app_with_precheck(tmp_path, release_catalog_files)
    cpu_worker(app)
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "groups": {
                "type": "object",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "samples": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "default": [0] * 8000,
                        }
                    },
                },
            },
        },
    }
    async with app.http as client:
        registered = await client.post(
            "/methods",
            headers=trial_headers(),
            json=package("def run(request): return {'passed':True}\n", schema),
        )
        assert registered.status_code == 201, registered.text
        refused = await client.post(
            "/method-evaluations",
            headers=trial_headers(),
            json={
                "method_ref": registered.json()["method_ref"],
                "parameters": {"groups": {str(index): {} for index in range(5)}},
            },
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "INVALID_METHOD_PARAMETERS"
