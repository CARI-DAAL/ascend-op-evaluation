#!/usr/bin/env python3
"""Exercise custom-method-v1 through a real test instance; retain every response.

The default checks use CPU methods and synthetic observations. Optional pinned
CANNBench component checks require its declared CPU Torch runtime. This script
does not claim device timing or full leaderboard equivalence.
"""

import argparse
import importlib.util
import json
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = (
    ROOT / "plugins/custom-method-eval/skills/custom-method-eval/scripts/custom_method_eval.py"
)
spec = importlib.util.spec_from_file_location("custom_method_client", CLIENT_PATH)
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--capability-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-cannbench-components", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=300)
    args = parser.parse_args()
    client = client_module.Client(args.url, args.capability_file)
    report = {
        "contract_version": "custom-method-v1",
        "owner": client.url,
        "scope": "CPU method protocol and pinned parser components; no NPU claim",
        "started_at_unix": time.time(),
        "checks": [],
        "passed": False,
    }

    def save():
        client_module.write_private(args.output, client_module.encoded(report) + b"\n")

    def upload_file(path, media_type="application/json"):
        import base64

        data = Path(path).read_bytes()
        _, stored = client.request(
            "POST",
            "/method-artifacts",
            {
                "contract_version": client_module.CONTRACT,
                "media_type": media_type,
                "content_base64": base64.b64encode(data).decode(),
            },
        )
        if client_module.verify_artifact(stored) != data:
            raise ValueError("input upload changed bytes")
        return stored["artifact_ref"]

    def register(path):
        _, registered = client.request("POST", "/methods", client_module.package_manifest(path))
        return registered["method_ref"]

    def run_case(name, method, inputs, parameters, expected, *, key=None, wait=True):
        body = {
            "contract_version": client_module.CONTRACT,
            "method_ref": method,
            "parameters": parameters,
            "inputs": inputs,
            "deadline_seconds": 120,
        }
        key = key or uuid.uuid4().hex
        _, resource = client.request(
            "POST", "/method-evaluations", body, headers={"Idempotency-Key": key}
        )
        entry = {
            "name": name,
            "submission": body,
            "idempotency_key": key,
            "evaluation_id": resource["evaluation_id"],
            "accepted": resource,
        }
        report["checks"].append(entry)
        save()
        if wait:
            resource = client_module.wait_resource(client, resource, args.wait_seconds, 0.25)
            entry["resource"] = resource
            data = resource.get("result", {}).get("method", {}).get("data")
            entry["passed"] = bool(data and data["outcome"] == expected)
            save()
            if not entry["passed"]:
                raise ValueError("method outcome differs from expected: " + name)
        return resource, entry

    try:
        base = ROOT / "examples/custom_methods"
        cannbench = ROOT / "adapters/cannbench/src/ascend_op_eval_adapter_cannbench/bundle"
        checker = register(base / "checker/method.json")
        inputs = {
            name: upload_file(base / f"checker/{name}.json") for name in ("actual", "reference")
        }
        run_case("checker rejects tight tolerance", checker, inputs, {"atol": 0.01}, "failed")
        resource, _ = run_case(
            "checker accepts changed parameter", checker, inputs, {"atol": 0.2, "rtol": 0}, "passed"
        )
        _, output = client.request(
            "GET", "/evaluations/" + resource["evaluation_id"] + "/artifacts/comparison.json"
        )
        content = client_module.verify_artifact(output)
        if json.loads(content)["passed"] is not True:
            raise ValueError("downloaded comparison report disagrees")
        measurement = register(base / "measurement/method.json")
        observed = {"launches": upload_file(base / "measurement/launches.json")}
        for name, expected_value in [
            ("median_call_total", 101),
            ("mean_call_total", 134),
            ("sum_kernel_medians", 200),
        ]:
            resource, entry = run_case(
                name, measurement, observed, {"aggregation": name}, "completed"
            )
            if resource["result"]["method"]["data"]["report"]["value"] != expected_value:
                entry["passed"] = False
                raise ValueError("aggregation result differs from known literal")
        # No device work is needed to prove cancellation and owner recovery.
        sleeping = client_module.package_manifest(base / "checker/method.json")
        sleeping["descriptor"].update(
            name="acceptance-sleeper",
            kind="harness",
            inputs={},
            parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
            output_schema={"type": "object"},
            output_artifacts={},
        )
        sleeping["files"] = {
            "checker.py": "import time\ndef run(request):\n time.sleep(300)\n return {}\n"
        }
        _, registered = client.request("POST", "/methods", sleeping)
        resource, entry = run_case(
            "cancel and recover", registered["method_ref"], {}, {}, None, wait=False
        )
        _, cancelled = client.request(
            "POST", "/evaluations/" + resource["evaluation_id"] + "/cancel", {}
        )
        cancelled = client_module.wait_resource(client, cancelled, args.wait_seconds, 0.25)
        entry["resource"], entry["passed"] = cancelled, cancelled["state"] == "cancelled"
        if not entry["passed"]:
            raise ValueError("cancellation did not reach acknowledged cancelled state")
        if args.include_cannbench_components:
            method = register(cannbench / "checker.method.json")
            inputs = {
                name: upload_file(cannbench / f"{name}.json")
                for name in ("actual", "reference", "native")
            }
            run_case("pinned comparator default rejects", method, inputs, {}, "failed")
            run_case(
                "pinned comparator threshold changes",
                method,
                inputs,
                {"custom_thresholds": {"float32": 0.1}},
                "passed",
            )
            method = register(cannbench / "measurement.method.json")
            data = {
                "kernel_details": upload_file(cannbench / "kernel_details.csv", "text/csv")
            }
            resource, entry = run_case("pinned CSV aggregation", method, data, {}, "completed")
            if resource["result"]["method"]["data"]["report"]["value"] != 200:
                entry["passed"] = False
                raise ValueError("upstream CSV parser result differs")
        report["passed"] = all(check.get("passed") for check in report["checks"])
    except (client_module.ClientError, ValueError, KeyError, TypeError, OSError) as error:
        report["failure"] = {
            "type": type(error).__name__,
            "message": getattr(error, "message", str(error)),
        }
    finally:
        report["finished_at_unix"] = time.time()
        save()
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "checks": len(report["checks"]),
                "report": str(args.output),
            }
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
