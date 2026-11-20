---
status: current
applies_to: legacy-evaluation-and-custom-method-v1
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# Verify, benchmark and profile an operator

The shortcuts use the same definition/workloads request as
[`POST /evaluations`](evaluations.md). `workloads` and at least one source are
required; correctness additionally needs both sources. Each uses the same
`Authorization: Bearer` capability and returns the same durable evaluation
resource with HTTP 200 or 202.

| Endpoint | Selected checks |
| --- | --- |
| `POST /verify` | Correctness; requires both PyTorch and Triton |
| `POST /benchmark` | Performance for one source; correctness and comparison for both |
| `POST /profile` | Profiling; accepts one or both sources |

Create `request.json` using the [comparison example](evaluations.md#submit), then:

```bash
curl -sS -i "$ASCEND_OP_EVAL_CLIENT_URL/verify?wait_seconds=0" \
  -H "Authorization: Bearer $(cat "$ASCEND_OP_EVAL_CLIENT_CAPABILITY_FILE")" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: verify-example-1' \
  --data-binary @request.json
```

Change the endpoint and key to benchmark or profile. The endpoint selects checks
after request validation; if `checks` is supplied in the body, it must be valid
but the shortcut overrides it. Use `/evaluations` to choose checks explicitly.
Performance and profile options use the same request model shown in `/docs`.
`/benchmark` supports [Torch timing reuse](evaluations.md#reuse-torch-baseline-timings)
through `performance.use_baseline_cache`; the client exposes
`--use-baseline-cache` and `--no-baseline-cache`. These control the PyTorch
baseline in a two-source comparison. Single-source benchmarks always measure
fresh and neither read nor write the baseline cache.

`Idempotency-Key` and `X-Session-ID` are optional. With a key, identical retries
on the same instance and session recover the same evaluation. Without a key,
each call submits new work. Poll `/evaluations/{evaluation_id}` to recover the
resource after the HTTP wait ends. There is no task catalog, separate tool token,
trial-turn budget or observation-text envelope on these endpoints.

## CPU preflight during candidate iteration

Use the deployed CPU worker to get compiler feedback before spending a card lease.
The request contains only the candidate and an optional deadline.

```bash
ascend-op-eval preflight --triton candidate.py
```

For Triton, `POST /preflight` accepts `{"triton_code": "..."}`. The service returns
`compile_mode="python_bytecode"`. The worker's Python interpreter compiles the supplied
candidate module to bytecode without importing it, creating inputs, or running
any workload. A syntax failure returns the Python diagnostic in
`result.compile.data.error_excerpt`, including location when available.
A pass establishes Python frontend compilation. Import resolution, Triton JIT,
numerical correctness and latency each require separate evidence.
The existing `evaluate --checks compile` includes import resolution.

For native projects, replace `--triton candidate.py` with
`--native-project project/native.json`. This runs the declared build on the CPU
worker and returns the build log and artifact digest under `result.native_build`.
Use a CPU worker with the target cross-toolchain. A later independent verify
request builds again. For expensive builds, a staged method can hand the built
artifact directly to its NPU stage. [Staged methods](custom-methods.md#staged-methods)

For a terminal preflight response, CLI exit 0 indicates the requested compiler check passed. Exit 1 reports a
candidate failure. Exit 2 reports missing evidence or a service/client failure.
Inspect the returned outcome before changing the candidate. After a pass,
submit the full workloads to `verify` or a two-source `benchmark` for device evidence.

For an in-flight native evaluation, `GET /evaluations/{id}/progress` exposes
`native_build` once the current attempt publishes it. A replacement attempt
must publish its own build. The terminal result contains the final build evidence.

## PyTorch profiling scope

PyTorch-only profiling observes the profiling process, including initialization;
it cannot isolate every reported launch to the supplied `run` function. The
service limits op mode to 100 launches using supported native-name prefixes, so its case
reports are partial and carry coverage warnings. Deep mode also observes the whole process and reports partial coverage. Preserve these warnings
when interpreting results; neither mode promises complete operator coverage.
For the underlying profiler's filtering and launch-count options, see
[msprof op parameters](https://www.hiascend.com/document/detail/en/canncommercial/850/devaids/optool/atlasopdev_16_0082.html).

## Recovering cases after a profiling timeout

On services advertising `profile-case-checkpoints`, poll the evaluation's
progress for `profile_checkpoint` during an op or deep check. Its `observed`
contains validated case results and tallies for that subset. Its
`pending_case_indices` identifies the remaining requested cases, and
`total_cases` describes the full input inventory. Check the attempt ID when
polling. A replacement starts with its own evidence.

A timed-out resource can retain this last published checkpoint at
`result.profile_checkpoint`. The profile check still reports `timeout`.
For example, if cases 0 and 1 are present and the pending list is `[2]`,
submit the same inputs and profiling options with `--case-indices 2` to the
`profile` command. An absent checkpoint means no validated subset was retained.
Case-level partial or failed outcomes in the observed subset retain their own status.

## Interpreting an op profile

Services advertising `op-profile-capture-scope` accept `profile.launch_limit`
(1–100, op mode only). The default is one matching launch for named kernels and
100 for the PyTorch application filter. Use `capture_scope` to inspect the
effective limit, name prefixes and number of parsed kernel records before
display truncation. Whole-case launch coverage is unknown. An op kernel's
percentage uses the sum of the displayed durations. Historical results can
omit scope. An execution failure before export can also leave scope unavailable.

## Interpreting a deep profile hotspot

Deep mode groups matching tasks by full kernel name in the first requested metric
pass with usable durations, following backend metric order. It selects the name
with the greatest cumulative task duration. The case's
`raw_metrics.target_selection` reports the metric group, the winner's timed row
count, total and maximum duration, and total duration across all matching names
in that pass. Durations are in microseconds. Overlapping tasks count separately,
so this share describes captured device work and can differ from wall time.

The optional `bound_rule` records the classifier rule associated with the ratios.
Each metric pass contributes counters from its longest timed row for the selected
name. When multiple passes contribute and that name repeats, a partial result
flags the ambiguity in relating those counters to an individual launch.

## Bundled client

The [Ascend Op Eval plugin](../../plugins/ascend-op-eval/README.md) provides `verify`,
`benchmark`, `profile` and `get` commands through its skill's standalone Python
script. It reads source files and a JSON array of cases, sends the same public
request, and polls the durable resource. For example, with the client path in
`ASCEND_OP_EVAL_CLI` and URL/capability configured:

```bash
python3 "$ASCEND_OP_EVAL_CLI" benchmark --definition definition.json --workloads workload.jsonl
python3 "$ASCEND_OP_EVAL_CLI" profile --definition definition.json --workloads workload.jsonl \
  --triton triton_impl.py --triton-only
```

These measure one implementation with `correctness_verified: false`; a zero
exit status means the requested measurement succeeded. Its recovery workflow keeps
the original instance and idempotency key after transport failures.

## Native HTTP and HTTPS

Use `ascend-op-eval-server api` to serve the configured HTTP listener and an
optional HTTPS listener from one process. For example:

```dotenv
ASCEND_OP_EVAL_API_HOST=10.0.0.11
ASCEND_OP_EVAL_API_PORT=11907
ASCEND_OP_EVAL_API_TLS_HOST=127.0.0.1
ASCEND_OP_EVAL_API_TLS_PORT=11909
ASCEND_OP_EVAL_API_TLS_CERTFILE=/absolute/service-tls/server.crt
ASCEND_OP_EVAL_API_TLS_KEYFILE=/absolute/service-tls/server.key
```

Use the installed interpreter followed by `-m ascend_op_eval.entrypoints.run_api`
for a service unit's `ExecStart`. The
`uvicorn ascend_op_eval.entrypoints.run_api:app` CLI serves one listener and does not activate the
paired-listener mode. Keep private keys outside the checkout with restricted
permissions; clients must trust the certificate authority.

Both listeners share authentication, one evaluation instance, Redis and one
ASGI lifespan. TLS settings and sockets are checked before serving, and failure
to bind the HTTPS listener does not leave an HTTP-only instance. Shutdown joins
both servers before maintenance cleanup. Local HTTP/TLS tests establish listener
behavior; each deployment must validate its own certificates and network path.
