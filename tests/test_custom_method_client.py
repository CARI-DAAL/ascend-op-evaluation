"""The custom method CLI packages data and uses real HTTP without service imports."""

import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/custom-method-eval/skills/custom-method-eval/scripts/custom_method_eval.py"
TOKEN = "method-client-secret-capability"
METHOD = "sha256:" + "a" * 64
EID = "ev_" + "1" * 32


@contextmanager
def server(responder):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def request(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            calls.append((self.command, self.path, dict(self.headers), raw))
            status, body, headers = responder(calls)
            encoded = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        do_GET = do_POST = do_PUT = request

        def log_message(self, *args):
            pass

    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{instance.server_port}", calls
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join()


def invoke(tmp_path, url, *args):
    capability = tmp_path / "capability"
    capability.write_text(TOKEN)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(SCRIPT),
            *args,
            "--url",
            url,
            "--capability-file",
            str(capability),
            "--poll-interval",
            "0.01",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        env={k: v for k, v in os.environ.items() if not k.startswith("EVALUATION_")},
    )
    assert TOKEN not in result.stdout + result.stderr
    return result, json.loads(result.stdout)


def completed(outcome="passed"):
    return {
        "evaluation_id": EID,
        "state": "completed",
        "result": {"method": {"status": "succeeded", "data": {"outcome": outcome}}},
    }


def artifact(data):
    digest = hashlib.sha256(data).hexdigest()
    return {
        "contract_version": "custom-method-v1",
        "artifact_ref": "sha256:" + digest,
        "sha256": digest,
        "size_bytes": len(data),
        "media_type": "application/json",
        "content_base64": base64.b64encode(data).decode(),
    }


def test_pack_reads_explicit_files_without_importing_method(tmp_path):
    (tmp_path / "entry.py").write_text("raise RuntimeError('must never run on client')\n")
    descriptor = {"name": "test", "version": "1", "kind": "checker", "entrypoint": "entry:run"}
    manifest = tmp_path / "method.json"
    manifest.write_text(json.dumps({"descriptor": descriptor, "files": ["entry.py"]}))
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(SCRIPT), "pack", "--manifest", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    package = json.loads(result.stdout)
    assert package["contract_version"] == "custom-method-v1"
    assert package["descriptor"] == descriptor
    assert package["files"] == {"entry.py": "raise RuntimeError('must never run on client')\n"}


def test_submit_preserves_values_and_recovers_on_original_owner(tmp_path):
    params = tmp_path / "params.json"
    params.write_text('{"zero":0,"disabled":false,"empty":null}')
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"actual": METHOD}))
    handle = tmp_path / "handle.json"

    def respond(calls):
        if len(calls) == 1:
            assert handle.exists(), "handle must exist before a potentially ambiguous POST"
            return (
                202,
                {"evaluation_id": EID, "state": "queued", "result": None},
                {"Location": "https://untrusted.invalid/credentials"},
            )
        return 200, completed(), {}

    with server(respond) as (url, calls):
        result, output = invoke(
            tmp_path,
            url,
            "submit",
            "--method",
            "sample-profile",
            "--parameters",
            str(params),
            "--inputs",
            str(inputs),
            "--save-handle",
            str(handle),
        )
        assert result.returncode == 0
        assert output["state"] == "completed"
        recovered, _ = invoke(tmp_path, url, "recover", "--handle", str(handle))
        assert recovered.returncode == 0
    assert [(c[0], c[1]) for c in calls] == [
        ("POST", "/method-evaluations"),
        ("GET", "/evaluations/" + EID),
        ("GET", "/evaluations/" + EID),
    ]
    body = json.loads(calls[0][3])
    assert body["parameters"] == {"zero": 0, "disabled": False, "empty": None}
    assert body["inputs"] == {"actual": METHOD}
    saved = json.loads(handle.read_text())
    assert saved["url"] == url and saved["evaluation_id"] == EID
    assert TOKEN not in handle.read_text()
    assert handle.stat().st_mode & 0o777 == 0o600


def test_ambiguous_submit_handle_replays_same_submission_and_key(tmp_path):
    handle = tmp_path / "handle.json"
    handle.write_text(
        json.dumps(
            {
                "contract_version": "custom-method-v1",
                "url": "unused",
                "evaluation_id": None,
                "idempotency_key": "stable-key",
                "submission": {"method_ref": "alias", "parameters": {}},
            }
        )
    )
    with server(lambda _: (200, completed(), {})) as (url, calls):
        saved = json.loads(handle.read_text())
        saved["url"] = url
        handle.write_text(json.dumps(saved))
        result, _ = invoke(tmp_path, url, "recover", "--handle", str(handle))
    assert result.returncode == 0
    assert calls[0][2]["Idempotency-Key"] == "stable-key"
    assert json.loads(calls[0][3]) == saved["submission"]


def test_recover_refuses_different_owner_before_network(tmp_path):
    handle = tmp_path / "handle.json"
    handle.write_text(
        json.dumps(
            {
                "contract_version": "custom-method-v1",
                "url": "https://original.invalid",
                "evaluation_id": EID,
            }
        )
    )
    with server(lambda _: (500, {}, {})) as (url, calls):
        result, output = invoke(tmp_path, url, "recover", "--handle", str(handle))
    assert result.returncode == 2 and output["error"]["code"] == "OWNER_MISMATCH"
    assert calls == []


@pytest.mark.parametrize(
    "outcome,code",
    [
        ("passed", 0),
        ("failed", 1),
        ("completed", 0),
        ("protocol_error", 2),
        ("environment_unavailable", 2),
    ],
)
def test_method_outcomes_remain_distinct(tmp_path, outcome, code):
    with server(lambda _: (200, completed(outcome), {})) as (url, calls):
        result, output = invoke(tmp_path, url, "get", EID)
    assert result.returncode == code
    assert output["result"]["method"]["data"]["outcome"] == outcome


def test_cancel_waits_for_cleanup_ack(tmp_path):
    def respond(calls):
        return (
            200,
            {
                "evaluation_id": EID,
                "state": "running" if len(calls) == 1 else "cancelled",
                "cancel_requested": True,
                "result": None,
            },
            {},
        )

    with server(respond) as (url, calls):
        result, output = invoke(tmp_path, url, "cancel", EID)
    assert result.returncode == 3 and output["state"] == "cancelled"
    assert [c[0] for c in calls] == ["POST", "GET"]


def test_alias_and_artifact_upload_download(tmp_path):
    data = b'{"data":[1,2,3]}'
    path, output = tmp_path / "input.json", tmp_path / "download.json"
    path.write_bytes(data)

    def respond(calls):
        return 200, ({"method_ref": METHOD} if calls[-1][0] == "PUT" else artifact(data)), {}

    with server(respond) as (url, calls):
        aliased, _ = invoke(tmp_path, url, "alias", "stable", METHOD)
        uploaded, meta = invoke(
            tmp_path,
            url,
            "artifact-upload",
            "--file",
            str(path),
            "--media-type",
            "application/json",
        )
        downloaded, _ = invoke(
            tmp_path, url, "artifact-get", meta["artifact_ref"], "--output", str(output)
        )
    assert aliased.returncode == uploaded.returncode == downloaded.returncode == 0
    assert json.loads(calls[0][3])["contract_version"] == "custom-method-v1"
    assert json.loads(calls[1][3])["content_base64"] == base64.b64encode(data).decode()
    assert output.read_bytes() == data


def test_bad_artifact_digest_does_not_overwrite_output(tmp_path):
    value = artifact(b"hello")
    value["content_base64"] = base64.b64encode(b"changed").decode()
    output = tmp_path / "saved"
    output.write_bytes(b"preserve")
    with server(lambda _: (200, value, {})) as (url, _):
        result, data = invoke(
            tmp_path, url, "artifact-get", value["artifact_ref"], "--output", str(output)
        )
    assert result.returncode == 2 and data["error"]["code"] == "INVALID_ARTIFACT"
    assert output.read_bytes() == b"preserve"


def test_materials_exports_frozen_inputs_privately(tmp_path):
    material = {
        "contract_version": "custom-method-v1",
        "method_ref": METHOD,
        "inputs": {"actual": artifact(b"[1,2]")},
        "dependencies": {},
        "package": {"files": {"checker.py": "def run(request): return {'passed': True}"}},
    }
    output = tmp_path / "material.json"
    with server(lambda _: (200, material, {})) as (url, calls):
        result, response = invoke(tmp_path, url, "materials", EID, "--output", str(output))
    assert result.returncode == 0 and response["saved"] is True
    assert calls[0][1] == "/evaluations/" + EID + "/method-materials"
    assert json.loads(output.read_text()) == material
    assert output.stat().st_mode & 0o777 == 0o600


def test_runtime_discovery_is_a_read_only_operation(tmp_path):
    value = {"contract_version": "custom-method-v1", "runtime_id": "worker-python-v1"}
    with server(lambda _: (200, value, {})) as (url, calls):
        result, output = invoke(tmp_path, url, "runtimes")
    assert result.returncode == 0 and output == value
    assert [(c[0], c[1]) for c in calls] == [("GET", "/method-runtimes")]


def test_redirect_is_not_followed_and_error_body_does_not_leak_token(tmp_path):
    with server(lambda _: (302, TOKEN.encode(), {"Location": "https://untrusted.invalid"})) as (
        url,
        calls,
    ):
        result, data = invoke(tmp_path, url, "get", EID)
    assert result.returncode == 2 and data["error"]["code"] == "HTTP_ERROR"
    assert len(calls) == 1


@pytest.mark.parametrize("name", ["../outside.py", "/absolute.py", "link.py"])
def test_pack_rejects_escape_and_symlink(tmp_path, name):
    outside = tmp_path / "outside.py"
    outside.write_text("sensitive")
    root = tmp_path / "project"
    root.mkdir()
    (root / "link.py").symlink_to(outside)
    manifest = root / "method.json"
    manifest.write_text(json.dumps({"descriptor": {}, "files": [name]}))
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(SCRIPT), "pack", "--manifest", str(manifest)],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "sensitive" not in result.stdout
