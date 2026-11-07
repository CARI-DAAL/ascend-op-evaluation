#!/usr/bin/env python3
"""Package, submit and recover custom-method-v1 work using only the standard library."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import ExitStack
from pathlib import Path, PurePosixPath

CONTRACT = "custom-method-v1"
__version__ = "0.1.0"
MAX_BLOB = 1024 * 1024
MAX_JSON = 4 * 1024 * 1024
MAX_RESPONSE = 12 * 1024 * 1024
EVALUATION_ID = re.compile(r"ev_[0-9a-f]{32}\Z")
REF = re.compile(r"sha256:[0-9a-f]{64}\Z")
ALIAS = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z")
TERMINAL = {"completed", "failed", "timed_out", "cancelled"}


class ClientError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def client_setting(name, legacy):
    """Accept the documented old setting without exposing credential values."""
    current = "ASCEND_OP_EVAL_CLIENT_" + name
    value, previous = os.environ.get(current), os.environ.get(legacy)
    if value is not None and previous is not None and value != previous:
        raise ClientError("CONFIG_CONFLICT", f"conflicting settings: {current}, {legacy}")
    return value if value is not None else previous


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ClientError("INVALID_ARGUMENT", "invalid arguments; use --help")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def positive(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("expected a finite positive value")
    return result


def read_bytes(path, limit):
    try:
        with Path(path).open("rb") as stream:
            value = stream.read(limit + 1)
    except OSError:
        raise ClientError("LOCAL_IO", "cannot read requested local file") from None
    if len(value) > limit:
        raise ClientError("SIZE_LIMIT", "requested local file exceeds its size limit")
    return value


def read_json(path):
    try:
        value = json.loads(read_bytes(path, MAX_JSON))
        json.dumps(value, allow_nan=False)
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise ClientError("INVALID_JSON", "file must contain finite JSON") from None


def safe_name(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or "\\" in value
        or "\0" in value
    ):
        raise ClientError("INVALID_PATH", "expected a relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(p in {".", ".."} for p in path.parts):
        raise ClientError("INVALID_PATH", "expected a normalized relative POSIX path")
    return path


def read_source(root, name):
    path = safe_name(name)
    try:
        with ExitStack() as stack:
            parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, parent)
            for part in path.parts[:-1]:
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                stack.callback(os.close, parent)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            stack.callback(os.close, fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ClientError("INVALID_PATH", "method files must be ordinary files")
            with os.fdopen(os.dup(fd), "rb") as source:
                data = source.read(MAX_BLOB + 1)
        if len(data) > MAX_BLOB:
            raise ClientError("SIZE_LIMIT", "method source exceeds 1 MiB")
        return data.decode("utf-8")
    except (OSError, UnicodeError):
        raise ClientError(
            "INVALID_PATH", "method source must be UTF-8 without symlink traversal"
        ) from None


def package_manifest(path):
    path = Path(path).absolute()
    manifest = read_json(path)
    if not isinstance(manifest, dict) or set(manifest) - {
        "contract_version",
        "descriptor",
        "files",
    }:
        raise ClientError("INVALID_MANIFEST", "invalid method manifest fields")
    files = manifest.get("files")
    if (
        not isinstance(manifest.get("descriptor"), dict)
        or not isinstance(files, list)
        or not files
        or len(files) > 128
        or any(not isinstance(f, str) for f in files)
        or len(set(files)) != len(files)
    ):
        raise ClientError("INVALID_MANIFEST", "manifest requires descriptor and unique file list")
    if manifest.get("contract_version", CONTRACT) != CONTRACT:
        raise ClientError("INVALID_MANIFEST", "unsupported method contract")
    sources = {name: read_source(path.parent, name) for name in files}
    if sum(len(source.encode()) for source in sources.values()) > MAX_BLOB:
        raise ClientError("SIZE_LIMIT", "method sources exceed 1 MiB in total")
    return {"contract_version": CONTRACT, "descriptor": manifest["descriptor"], "files": sources}


def write_private(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".method-client-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def encoded(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()


def endpoint_url(value):
    if not isinstance(value, str):
        raise ClientError("INVALID_URL", "provide --url or EVALUATION_URL")
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ClientError("INVALID_URL", "service URL must be HTTP(S) without credentials/query")
    return value.rstrip("/")


class Client:
    def __init__(self, url, capability_file, timeout=15):
        self.url = endpoint_url(url)
        if capability_file is None:
            raise ClientError("MISSING_CAPABILITY", "provide a capability file")
        self.token = read_bytes(capability_file, 16384).decode("utf-8").strip()
        if not self.token or "\n" in self.token or "\r" in self.token:
            raise ClientError("INVALID_CAPABILITY", "capability must be a nonempty single line")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, path, body=None, *, headers=None):
        request = urllib.request.Request(
            self.url + path,
            data=None if body is None else encoded(body),
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
                **(headers or {}),
            },
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
                status = response.status
        except urllib.error.HTTPError as error:
            raise ClientError("HTTP_ERROR", f"service returned HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ClientError(
                "TRANSPORT_ERROR", "request failed; recover accepted work on its owner"
            ) from None
        if len(raw) > MAX_RESPONSE:
            raise ClientError("INVALID_RESPONSE", "service response exceeds client limit")
        try:
            value = json.loads(raw)
            encoded(value)
        except (ValueError, UnicodeError, RecursionError):
            raise ClientError("INVALID_RESPONSE", "service returned invalid JSON") from None
        if not isinstance(value, dict):
            raise ClientError("INVALID_RESPONSE", "service response must be an object")
        return status, value


def reference(value):
    if not REF.fullmatch(value):
        raise ClientError("INVALID_REFERENCE", "expected an immutable sha256 reference")
    return urllib.parse.quote(value, safe="")


def evaluation_id(value):
    if not EVALUATION_ID.fullmatch(value):
        raise ClientError("INVALID_ID", "invalid evaluation id")
    return value


def check_resource(value, expected=None):
    found = value.get("evaluation_id", "")
    evaluation_id(found)
    if expected is not None and found != expected:
        raise ClientError("INVALID_RESPONSE", "service returned a different evaluation")
    if value.get("state") not in TERMINAL | {"queued", "running"}:
        raise ClientError("INVALID_RESPONSE", "unknown evaluation state")
    return value


def wait_resource(client, resource, timeout, interval):
    deadline = time.monotonic() + timeout
    identifier = resource["evaluation_id"]
    while resource["state"] not in TERMINAL:
        if time.monotonic() >= deadline:
            raise ClientError("WAIT_EXPIRED", "client wait expired; execution was not cancelled")
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
        _, resource = client.request("GET", "/evaluations/" + identifier)
        check_resource(resource, identifier)
    return resource


def verify_artifact(artifact):
    try:
        raw = base64.b64decode(artifact["content_base64"], validate=True)
        digest = hashlib.sha256(raw).hexdigest()
        if (
            len(raw) > MAX_BLOB
            or type(artifact["size_bytes"]) is not int
            or artifact["size_bytes"] != len(raw)
            or artifact["sha256"] != digest
            or artifact["artifact_ref"] != "sha256:" + digest
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ClientError(
            "INVALID_ARTIFACT", "artifact content does not match its identity"
        ) from None
    return raw


def arguments(argv):
    parser = Parser(description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("pack")
    pack.add_argument("--manifest", type=Path, required=True)
    pack.add_argument("--output", type=Path)
    for name in [
        "upload",
        "method",
        "alias",
        "artifact-upload",
        "artifact-get",
        "submit",
        "get",
        "progress",
        "cancel",
        "recover",
        "output",
        "materials",
        "runtimes",
    ]:
        sub = commands.add_parser(name)
        sub.add_argument("--url", default=client_setting("URL", "EVALUATION_URL"))
        sub.add_argument(
            "--capability-file",
            type=Path,
            default=client_setting("CAPABILITY_FILE", "EVALUATION_CAPABILITY_FILE"),
        )
        sub.add_argument("--timeout", type=positive, default=15.0)
        sub.add_argument("--wait-seconds", type=positive, default=300.0)
        sub.add_argument("--poll-interval", type=positive, default=1.0)
        sub.add_argument("--no-wait", action="store_true")
        if name == "upload":
            source = sub.add_mutually_exclusive_group(required=True)
            source.add_argument("--manifest", type=Path)
            source.add_argument("--package", type=Path)
            sub.add_argument("--expected-digest")
        elif name == "method":
            sub.add_argument("method_ref")
        elif name == "alias":
            sub.add_argument("name")
            sub.add_argument("method_ref")
        elif name == "artifact-upload":
            sub.add_argument("--file", type=Path, required=True)
            sub.add_argument("--media-type", default="application/octet-stream")
        elif name == "artifact-get":
            sub.add_argument("artifact_ref")
            sub.add_argument("--output", type=Path, required=True)
        elif name == "submit":
            sub.add_argument("--method", dest="method_ref", required=True)
            sub.add_argument("--parameters", type=Path)
            sub.add_argument("--inputs", type=Path)
            sub.add_argument("--limits", type=Path)
            sub.add_argument("--deadline-seconds", type=int, default=300)
            sub.add_argument("--idempotency-key")
            sub.add_argument("--save-handle", type=Path, required=True)
        elif name == "recover":
            sub.add_argument("--handle", type=Path, required=True)
        elif name != "runtimes":
            sub.add_argument("evaluation_id")
            if name == "output":
                sub.add_argument("name")
            if name in {"output", "materials"}:
                sub.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def execute(args):
    if args.command == "pack":
        package = package_manifest(args.manifest)
        if args.output:
            write_private(args.output, encoded(package) + b"\n")
        return package
    handle = read_json(args.handle) if args.command == "recover" else None
    if handle is not None:
        if not isinstance(handle, dict) or handle.get("contract_version") != CONTRACT:
            raise ClientError("INVALID_HANDLE", "invalid recovery handle")
        owner = endpoint_url(handle.get("url"))
        if args.url is not None and endpoint_url(args.url) != owner:
            raise ClientError("OWNER_MISMATCH", "recover against the original instance")
        args.url = owner
    client = Client(args.url, args.capability_file, args.timeout)
    if args.command == "runtimes":
        return client.request("GET", "/method-runtimes")[1]
    if args.command == "materials":
        identifier = evaluation_id(args.evaluation_id)
        materials = client.request("GET", "/evaluations/" + identifier + "/method-materials")[1]
        if materials.get("contract_version") != CONTRACT or not REF.fullmatch(
            materials.get("method_ref", "")
        ):
            raise ClientError("INVALID_RESPONSE", "invalid frozen method material")
        for group in ("inputs", "dependencies"):
            for artifact in materials.get(group, {}).values():
                verify_artifact(artifact)
        write_private(args.output, encoded(materials) + b"\n")
        return {"evaluation_id": identifier, "method_ref": materials["method_ref"], "saved": True}
    if args.command == "upload":
        body = package_manifest(args.manifest) if args.manifest else read_json(args.package)
        headers = {}
        if args.expected_digest:
            reference(args.expected_digest)
            headers["X-Expected-Digest"] = args.expected_digest
        return client.request("POST", "/methods", body, headers=headers)[1]
    if args.command == "method":
        value = client.request("GET", "/methods/" + reference(args.method_ref))[1]
        if value.get("method_ref") != args.method_ref:
            raise ClientError("INVALID_RESPONSE", "service returned a different method")
        return value
    if args.command == "alias":
        if not ALIAS.fullmatch(args.name):
            raise ClientError("INVALID_ALIAS", "invalid method alias")
        reference(args.method_ref)
        return client.request(
            "PUT",
            "/method-aliases/" + args.name,
            {"contract_version": CONTRACT, "method_ref": args.method_ref},
        )[1]
    if args.command == "artifact-upload":
        raw = read_bytes(args.file, MAX_BLOB)
        artifact = client.request(
            "POST",
            "/method-artifacts",
            {
                "contract_version": CONTRACT,
                "media_type": args.media_type,
                "content_base64": base64.b64encode(raw).decode(),
            },
        )[1]
        if verify_artifact(artifact) != raw:
            raise ClientError("INVALID_ARTIFACT", "upload response differs from supplied bytes")
        return {key: value for key, value in artifact.items() if key != "content_base64"}
    if args.command in {"artifact-get", "output"}:
        path = (
            "/method-artifacts/" + reference(args.artifact_ref)
            if args.command == "artifact-get"
            else "/evaluations/"
            + evaluation_id(args.evaluation_id)
            + "/artifacts/"
            + urllib.parse.quote(str(safe_name(args.name)), safe="")
        )
        artifact = client.request("GET", path)[1]
        if args.command == "artifact-get" and artifact.get("artifact_ref") != args.artifact_ref:
            raise ClientError("INVALID_ARTIFACT", "service returned a different artifact")
        write_private(args.output, verify_artifact(artifact))
        return {key: value for key, value in artifact.items() if key != "content_base64"}
    if args.command == "submit":
        submission = {
            "contract_version": CONTRACT,
            "method_ref": args.method_ref,
            "parameters": read_json(args.parameters) if args.parameters else {},
            "inputs": read_json(args.inputs) if args.inputs else {},
            "deadline_seconds": args.deadline_seconds,
        }
        if args.limits:
            submission["limits"] = read_json(args.limits)
        handle = {
            "contract_version": CONTRACT,
            "url": client.url,
            "evaluation_id": None,
            "idempotency_key": args.idempotency_key or uuid.uuid4().hex,
            "submission": submission,
        }
        write_private(args.save_handle, encoded(handle) + b"\n")
    if args.command in {"submit", "recover"}:
        target = args.save_handle if args.command == "submit" else args.handle
        if handle.get("evaluation_id"):
            identifier = evaluation_id(handle["evaluation_id"])
            resource = check_resource(
                client.request("GET", "/evaluations/" + identifier)[1], identifier
            )
        else:
            resource = check_resource(
                client.request(
                    "POST",
                    "/method-evaluations",
                    handle["submission"],
                    headers={"Idempotency-Key": handle["idempotency_key"]},
                )[1]
            )
            handle["evaluation_id"] = resource["evaluation_id"]
            write_private(target, encoded(handle) + b"\n")
    else:
        identifier = evaluation_id(args.evaluation_id)
        path = "/evaluations/" + identifier
        if args.command == "progress":
            return client.request("GET", path + "/progress")[1]
        if args.command == "cancel":
            resource = check_resource(client.request("POST", path + "/cancel", {})[1], identifier)
        else:
            resource = check_resource(client.request("GET", path)[1], identifier)
    if args.no_wait:
        return resource
    return wait_resource(client, resource, args.wait_seconds, args.poll_interval)


def outcome_code(value):
    if value.get("state") == "cancelled":
        return 3
    if value.get("state") in {"failed", "timed_out"}:
        return 2
    result = value.get("result")
    if not isinstance(result, dict):
        return 2 if value.get("state") == "completed" else 0
    method = result.get("method")
    if not isinstance(method, dict):
        return 2 if value.get("state") == "completed" else 0
    if method.get("status") != "succeeded":
        return 2
    outcome = (method.get("data") or {}).get("outcome")
    return 1 if outcome == "failed" else 0 if outcome in {"passed", "completed"} else 2


def main(argv=None):
    try:
        value = execute(arguments(argv))
        print(encoded(value).decode())
        return outcome_code(value)
    except ClientError as error:
        print(encoded({"error": {"code": error.code, "message": error.message}}).decode())
        return 2
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print('{"error":{"code":"INVALID_DATA","message":"invalid local data or response"}}')
        return 2


if __name__ == "__main__":
    sys.exit(main())
