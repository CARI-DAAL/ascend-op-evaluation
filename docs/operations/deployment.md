---
status: current
applies_to: legacy-evaluation-and-custom-method-v1
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# Deploy an evaluation instance

Run the setup commands below from the repository root. Docker-specific assets
live in `deploy/`; the build context remains the repository root:

```bash
docker build -f deploy/images/Dockerfile -t ascend-op-eval:local .
```

For deployment, publish the image and use its immutable digest as described below.
The Compose wrapper uses `deploy/compose/compose.yaml` with an explicit repository project
directory. This preserves the default project name, root `logs/` mount and Redis
volume identity when moving the Compose file. `.dockerignore` stays at the build
context root. The wrapper can also be called by absolute path from another directory.
Custom `ASCEND_OP_EVAL_COMPOSE_FILE` paths use the same repository project directory.

Run one independent instance per host, each with its own API, local durable
Redis and card list. The image contains the declared Python stack; CANN and
driver come from the host. Bind each instance to an explicit private IPv4
address. The driver reaches that address; task-agent containers reach only
the driver's session facade.

Copy [`deploy/compose/.env.example`](../../deploy/compose/.env.example) to `deploy/compose/.env` and replace
its placeholders before starting. Existing env files can remain at their current
location; point `ASCEND_OP_EVAL_ENV_FILE` at that absolute path:

| Setting | Value to supply |
| --- | --- |
| `ASCEND_OP_EVAL_API_HOST` | This host's private IPv4 address; API port is `11907` |
| `ASCEND_OP_EVAL_IMAGE`, `ASCEND_OP_EVAL_EVALUATOR_BUILD` | Immutable image reference and its matching `sha256:…` digest |
| `ASCEND_OP_EVAL_RELEASE_MANIFEST_HOST` | Manifest generated and bound for that exact image, mounted read-only |
| `CANN_HOST`, `ASCEND_OP_EVAL_WORKER_*` | Host toolkit path and actual hardware/toolchain inventory |
| `ASCEND_OP_EVAL_CARDS` | Unique physical card IDs, e.g. `0` or `0,1,3` |
| `ASCEND_OP_EVAL_CAPABILITY_SECRET_PATH` | Caller registry JSON, permissions no broader than `0600` |

The registry format is defined in [capability loading](../../packages/ascend-op-eval/src/ascend_op_eval/control/security.py).
Catalog files and dataset registration are not deployment inputs. For upgrades first follow [the cutover guide](../migration/rename-and-cutover.md). Set `ASCEND_OP_EVAL_COMPOSE_PROJECT_NAME` to the actual existing project name; changing it changes volume selection. After editing `deploy/compose/.env`:

```bash
set -a
source deploy/compose/.env
set +a
export ASCEND_OP_EVAL_ENV_FILE="$PWD/deploy/compose/.env"
deploy/compose/compose.sh pull
deploy/compose/compose.sh up -d --force-recreate
deploy/compose/compose.sh logs -f
```

Preflight validates the exact configuration being launched, locally available
pinned images, private bind, mounted capability registry, release-mode startup
bound to the deployed image's [release manifest](../reference/release-identity.md), and Redis AOF
settings.
Export the env file before invoking the wrapper, as above. Use `up` to apply
configuration changes; `start` and `restart` reuse existing containers.
`ASCEND_OP_EVAL_CARDS` selects worker processes; the privileged Ascend container
has host device access, so this list is scheduling rather than a container
security boundary. Restrict network access to trusted drivers. For access
outside the private network, use a separately managed TLS gateway and put its
HTTPS URL in the consumer pool.

For a single-card smoke deployment, use this same Compose file with
`ASCEND_OP_EVAL_CARDS=0`. Card lists are unique nonnegative integers, such as
`0,1,3`. Redis uses the local server on port 6379, with database 7 by default.
`ASCEND_OP_EVAL_CPU_WORKERS` defaults to 1 and accepts 0–32. Setting it to 0
disables compile-only capacity unless separate
`ascend-op-eval-server worker --cpu` processes join the same instance. CPU workers do not claim cards or run card recovery.

For host execution without Docker, install `.[npu]` in an isolated environment
(with the Ascend wheel index if needed), configure [`.env.example`](../../deploy/host/.env.example)
as `.env`, then use `bash deploy/host/start.sh` / `bash deploy/host/stop.sh`. Supply Redis
with `--appendonly yes --appendfsync always`, as Compose does. The engine is
bundled and needs no external checkout.

Before creating logs or starting processes, the host launcher checks that the
configured worker interpreter can import `ascend_op_eval` from a temporary
attempt directory. It inherits the worker environment verbatim: a relative
`PYTHONPATH` that only works from the repository root is insufficient. Install
the project into that interpreter (after installing its runtime dependencies):

```bash
"$PYTHON_BIN" -m pip install -e packages/ascend-op-eval --no-deps
"$PYTHON_BIN" scripts/deployment_preflight.py --engine-import-context
```

Set `PYTHON_BIN` to the worker interpreter and run these commands from the
repository root. The probe reports a failure before startup rather than letting
every correctness task fail to import runtime helpers. It does not install
anything automatically. For configured sandboxes the host-only probe is skipped;
package mounts and the declared child `PYTHONPATH` must instead be correct inside
the sandbox. A sandbox setting alone does not prove that package visibility.


The API owns HTTP admission and recovery; workers execute leased attempts with
separate CPU/NPU assignments and lifecycles. Their entrypoints remain separate
under `scripts/`. For manual startup, use separate terminals from the repository
root with the same exported instance configuration:

```bash
ascend-op-eval-server api
ascend-op-eval-server worker --cpu
ascend-op-eval-server worker --card 0
```

Run one NPU worker per configured physical card. The host launcher and Compose
manage these processes together. For a single HTTP listener, the API can also
run as `uvicorn ascend_op_eval.entrypoints.run_api:app --host "$ASCEND_OP_EVAL_API_HOST" --port 11907`.
Use `ascend-op-eval-server api` for the configured
[native HTTP/TLS listeners](../guides/evaluate-an-operator.md#native-http-and-https).

Candidate code needs an operating-system boundary when evaluations must not
read other attempts or service credentials. Subprocesses alone do not provide
that boundary. Set `ASCEND_OP_EVAL_ENGINE_SANDBOX_CONFIG` on each worker to an
operator-owned runtime manifest, and pin its digest with
`ASCEND_OP_EVAL_ENGINE_SANDBOX_SHA256`, to enable the fail-closed Linux engine sandbox.
See [engine isolation](../explanation/execution-isolation.md) for deployment and
device requirements. Bind changes to this execution environment to a new
evaluator build; do not combine its measurements with a previous environment
without declaring the change.

For a deployed CANN profiler with a missing `libsqlite3.so` name, see
[the pinned profiler runtime](profiler-runtime.md). Preparation, immutable
file binding and the actual worker/device gates are separate steps.

Correctness defaults to the existing CPU-first reference with NPU fallback for
reference execution errors. To declare an NPU reference experiment, set
`ASCEND_OP_EVAL_REFERENCE_DEVICE_POLICY=npu-strict` on the API and every worker.
This mode always selects the assigned NPU and never changes reference device
after seeing a candidate outcome. It adds `:npu-strict-v1` to the published
correctness algorithm identity automatically. Bind the policy to a new evaluator
build and experiment; numerical rounding can differ even though the comparison
formula and tolerances are unchanged. See [reference policy and observations](../reference/reference-device-policy.md)
for provenance, retention and admission checks.

## Evaluation time budgets

New requests default to a `3600`-second resource deadline, shared by queue time
and all requested checks. The default whole-run caps are also one hour:

```bash
ASCEND_OP_EVAL_VERIFY_BUDGET_CAP_SECONDS=3600
ASCEND_OP_EVAL_BENCHMARK_TIMEOUT_SECONDS=3600
```

Each stage is still bounded by the resource's remaining time. Explicit shorter
request deadlines and deployment caps remain supported. Client waiting is
separate: the bundled CLI and smoke client wait up to `3660` seconds by default;
a longer client wait does not extend admitted work.

**Existing deployments must update explicit environment overrides.** Rebuilding
the service does not replace values already set in `.env`, `deploy/compose/.env`, or
the worker environment. Apply the new values to API/worker deployments using
the deployment procedure above; Compose requires `up --force-recreate`, while
host workers need to restart with the updated environment. Existing admitted
resources retain their recorded deadlines. Profiler sub-step limits, health
checks, leases and transport timeouts keep their separate settings.

## Runtime dependencies and observability

API and worker entrypoints explicitly assemble their metrics adapters. Observers
can read `/internal/metrics`; authentication and bounded label rules still apply.
Metrics and advisory caches use connections with 0.25-second connect/read timeouts
and no retries, separate from the durable store client. Redis metrics reads and
error counting run off the HTTP event loop. Observability failures do not change
admission, lease renewal or terminal publication outcomes.

Worker checks share a startup environment built from `Settings` and inherited
toolchain variables. Settings take precedence for runtime fields; absent optional
settings remove stale inherited values. Precheck honors `ASCEND_OP_EVAL_ENGINE_DIR`.
Apply environment changes by restarting workers, including CPU workers. Sandbox
configuration and SHA must be supplied together. Changes to source-pinned runtime
helpers require renewed deployment pins and an updated evaluator build before
running the device release checks.

## Torch baseline cache

For two-source comparisons, workers use the existing instance Redis to retain
per-case Torch baseline latency scalars. Single-source measurements bypass this
cache entirely.
No additional database or precomputation service is needed. Entries use
`<redis_prefix>:baseline:<sha256>` keys; they contain a case count and measured
latencies, not source code or tensors. Storage grows with distinct tasks and
measurement protocols, with up to 128 latency values per task/protocol entry.
Redis metadata and persistence overhead add to those values.

Entries have no TTL or automatic drift detection. Their lifetime follows Redis
persistence and explicit operator cleanup. Compose stores Redis AOF data in the
`triton-eval-redis-v2` volume, including these cache entries. Cache connection
errors are advisory; durable evaluation state still requires working Redis.

Use the same `ASCEND_OP_EVAL_BASELINE_CACHE_NAMESPACE` on all workers of an instance
(default `torch-baseline-v1`). This scope assumes equivalent fixed hardware and
runtime across its cards. Change it when hardware, runtime or measurement behavior
changes, then restart workers. New evaluations populate a fresh scope; old keys
remain until explicitly removed. Never clear the entire Redis database to clear
baseline timings: it also owns durable evaluations. A cache namespace change does
not replace the required evaluator build update for runtime changes.

Benchmark requests bypass the older pinned timing caches, regardless of the new
cache switch. Legacy reference-output settings remain a separate correctness
feature; see [pinned reference caches](reference-cache.md).

## Multiple hosts

Set `EVALUATION_POOL_FILE` on the consumer driver to a JSON file:

```json
{"endpoints": [
  {"id": "ascend-a", "url": "http://10.0.0.11:11907", "capability_file": "/run/secrets/eval-a"},
  {"id": "ascend-b", "url": "http://10.0.0.12:11907", "capability_file": "/run/secrets/eval-b"}
]}
```

Each consumer capability file contains one opaque token; the service secret
contains its caller registry. These are different formats, both kept outside
agent containers. A single endpoint uses `ASCEND_OP_EVAL_CLIENT_URL` and
`ASCEND_OP_EVAL_CLIENT_CAPABILITY_FILE` instead.

The client uses rendezvous hashing of session ID and stable endpoint ID.
Submission, ambiguous retries and GET recovery retain the original instance.
Unavailable owners produce recoverable infrastructure failures; accepted
work is never automatically resubmitted onto another host. Pool changes affect
new sessions. Keep old owners available while their evaluation handles exist.
Quotas, card health and caches are per instance. Never share one namespace
between machines with overlapping card IDs.
