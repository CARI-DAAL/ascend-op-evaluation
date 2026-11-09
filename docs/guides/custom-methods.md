---
status: current
applies_to: legacy-evaluation-and-custom-method-v1
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# External checker, measurement and harness methods

The `custom-method-v1` interface registers immutable method packages, seals their
parameters and input resources at admission, and executes them through the same
evaluation queue, lease, deadline and recovery mechanisms as native/Triton work.
The existing operator endpoints remain available with their existing defaults.

A method is a Python `module:function` called in a worker child with one request
dictionary. It receives effective `parameters`, named `inputs` and `dependencies`
as file descriptors (`path`, `sha256`, `media_type`), a private `output_dir`, the
assigned `device`, and parent budget/deadline information. The function returns a
JSON report; additional files under output_dir are collected as bounded artifacts.
The service does not import submitted code to read its descriptor.

## Interfaces

| Operation | Endpoint |
| --- | --- |
| Register source package | `POST /methods` |
| Discover declared runtimes and registry limits | `GET /method-runtimes` |
| Read frozen package | `GET /methods/{method_ref}` |
| Set caller-owned alias | `PUT /method-aliases/{alias}` |
| Upload/read input or dependency | `POST /method-artifacts`, `GET /method-artifacts/{artifact_ref}` |
| Submit method and parameters | `POST /method-evaluations` |
| Recover execution/progress | `GET /evaluations/{id}`, `GET /evaluations/{id}/progress` |
| Request cancellation | `POST /evaluations/{id}/cancel` |
| Read an output artifact | `GET /evaluations/{id}/artifacts/{name}` |
| Export frozen admitted materials | `GET /evaluations/{id}/method-materials` |

All routes require the caller capability. Method aliases and artifacts are scoped
to their caller, not made public by knowing a SHA. Aliases freeze at admission;
same-key replay preserves the original accepted execution even after an alias moves.

Method and submission JSON explicitly carry `contract_version: "custom-method-v1"`.
The outer evaluation resource continues to use the existing envelope; its custom
`method_identity` and `result.method` do not retrofit method claims onto old records.

Use `custom_method_eval.py runtimes` to inspect deployment-declared capabilities
and registry budgets before preparing a package. Registry limits are caller-scoped
and include package, input artifact and alias storage; re-uploading identical
materials does not create an unlimited second copy.

## A runnable checker example

The [checker](../../examples/custom_methods/checker/method.json) compares JSON
trees from distinct actual/reference files. Its tolerance changes the real result:
the supplied values fail at atol=0.01 and pass at atol=0.2.

```bash
export ASCEND_OP_EVAL_CLIENT_URL=http://YOUR_TEST_INSTANCE:11907
export ASCEND_OP_EVAL_CLIENT_CAPABILITY_FILE=/path/to/caller-capability
CLI=plugins/custom-method-eval/skills/custom-method-eval/scripts/custom_method_eval.py

python3 "$CLI" upload --manifest examples/custom_methods/checker/method.json
python3 "$CLI" artifact-upload --file examples/custom_methods/checker/actual.json --media-type application/json
python3 "$CLI" artifact-upload --file examples/custom_methods/checker/reference.json --media-type application/json
```

Save the returned refs in `input-refs.json` as
`{"actual":"sha256:...","reference":"sha256:..."}`, then use the returned method ref:

```bash
python3 "$CLI" submit --method sha256:METHOD_DIGEST \
  --parameters examples/custom_methods/checker/parameters.json \
  --inputs input-refs.json --save-handle checker-handle.json
python3 "$CLI" recover --handle checker-handle.json
python3 "$CLI" output ev_EVALUATION_ID comparison.json --output comparison.json
python3 "$CLI" materials ev_EVALUATION_ID --output frozen-method.json
```

Parameters are validated by the frozen schema, including unknown fields and
constraints. Missing values receive declared defaults; explicit 0, false and null
retain their distinct meanings. The result records requested and effective values.
The first contract supports a bounded Draft 2020-12 schema vocabulary; external
references, regex/pattern keywords, other dialects and ambiguous conditional
defaults are rejected. Schema validation is metadata-only and never imports the
method. Defaults inside named properties, array items and dynamic object members
are applied recursively where the schema permits them.
Package descriptor, source, dependency and runtime identities remain visible on
queued and terminal method resources. Changing the method or parameters does not
reuse built-in correctness or baseline evidence.

## Measurement examples

The [CPU callable timer](../../examples/custom_methods/cpu_timer/method.json)
actually invokes its packaged target function with configurable warmup/repeat
and aggregation, retaining raw timing samples and call counts. It measures a
CPU callable window, not NPU kernel duration.

The [launch aggregation method](../../examples/custom_methods/measurement/method.json)
accepts explicit invocation/launch observations. It sums repeated same-name target
launches within each invocation and excludes declared preparation/warmup roles.
The fixture's invocation totals are [101,101,200] us: `median_call_total` gives
101, `mean_call_total` gives 134, and `sum_kernel_medians` gives 200. Conditional
absence is excluded from a kernel's per-name distribution, which is stated in
this example's method semantics. Raw observations and the aggregate report are
saved independently. These are controlled observations, not device measurements.

The [CANNBench examples](../../adapters/cannbench/src/ascend_op_eval_adapter_cannbench/bundle/README.md) invoke
byte-identical modules from a fixed public upstream revision. They exercise its
actual numeric comparator and kernel-details strategy; the full NPU harness
bridge is separately provided with an explicit device qualification gap.

## Outcomes, cancellation and raw data

Checker passed/failed, method exception, invalid protocol, missing environment and
timeout are distinct outcomes. A completed method is not automatic operator
correctness: `authority: caller_method` identifies the caller-supplied protocol.
A full harness report can contain an upstream nonzero exit or failed benchmark
even when the wrapper itself returned a valid report. Inspect its original data.

Queued cancellation can finish immediately. Running cancellation first records
intent and invalidates further work; the resource remains running with
`cancel_requested` until child cleanup is acknowledged or recovery handles the
lost worker. Cancellation is idempotent and never creates another evaluation.
The CLI saves a private recovery handle before POST and never follows another
instance's Location to retry accepted work.

Uploads are bounded at 1 MiB per artifact and 1 MiB of method text (128 files).
Method descriptors support at most eight dependency artifacts and sixteen named
inputs. Frozen admission is bounded at 8 MiB. Default output limits are 64 KiB
logs, 1 MiB artifacts and 32 files; selected limits and truncation/missing states
are explicit. Large upstream tasks or profiler exports must fit these documented
limits; do not silently drop requested tasks or trace data to fit.

The registry defaults to 64 MiB of serialized records and 256 records per caller,
including packages, input artifacts and aliases. Operators can configure
`ASCEND_OP_EVAL_METHOD_REGISTRY_MAX_BYTES` and
`ASCEND_OP_EVAL_METHOD_REGISTRY_MAX_RECORDS`; reuploading existing bytes does not
double-charge storage. Frozen admitted materials remain readable through the
evaluation handle for its retention window, even when a registry entry expires.
Output artifacts belong to the execution's retained evidence. To use one as a
later method input, download it and register those bytes with artifact-upload;
the service verifies the same content digest. An output ref is not automatically
a global input-registry entry.

## Staged methods

A descriptor may split one evaluation into separately leased stages, for
example a CPU build followed by an NPU run, so a long build does not hold a card:

```json
"entrypoint": "stages:run",
"requirements": {"device": "npu"},
"stages": [
  {"device": "cpu", "entrypoint": "stages:build"},
  {"device": "npu", "entrypoint": "stages:run"}
]
```

There are two to four stages. The last one must equal `entrypoint` and
`requirements.device`. Without `stages`, a method is one stage and its identity
is unchanged. Callers still submit once and read one evaluation resource. It
stays `running` between stages.

Each stage request carries `stage` (`index`, `count`) and `handoff`, the previous
stage's files as `{path, sha256, size_bytes}`. A non-final stage also receives
`handoff_dir`. If it completes with files there (at most 32 regular files,
256 MiB in total), the worker copies them into the stage spool by content digest
and queues the next stage on its device class. The next stage receives
digest-verified copies. A non-final stage that leaves no handoff files ends the
evaluation: its report must satisfy `output_schema`, which is how a failed build
returns its report without entering the NPU queue. Continuing stages' reports
are recorded but not validated as final reports. Only the stage that ends the
evaluation publishes output artifacts.

`deadline_seconds` applies to each stage, starting when the stage is queued.
Each stage has its own lease-recovery retry budget. A missing or corrupt
spooled handoff is `environment_unavailable`. `result.method.data.stages`
lists every executed stage with its device, outcome, `duration_ms` and handoff
digests. The `method_stage_duration_seconds` metric splits CPU and NPU time.

Set `ASCEND_OP_EVAL_STAGE_SPOOL_DIR` to an absolute directory shared by every
CPU and NPU worker, and set it on the API as well. Admission rejects staged
methods while it is unset. The final stage's worker removes an evaluation's spool directory
when it commits the result. Workers also remove spool directories older than 25
hours. Handoff files are build data, not registry artifacts. They are neither
charged to the caller's registry quota nor downloadable.

## Runtime and trust

Runtime IDs/capabilities are deployment configuration, not rights granted by a
method descriptor. Declared Python distributions require exact versions and tool
requirements must exist. The method does not install dependencies into the shared
service interpreter. Missing runtime/capability/dependency produces an explicit
failure, never a different checker or timing fallback.

Deploy matching verified API and worker builds. A development all-zero build ID
is not evidence of compatibility with an older worker. Set
`ASCEND_OP_EVAL_METHOD_CAPABILITIES` only to capabilities the configured runtime
provides, for example `["python","npu","process-isolation","soc-ascend910_93"]`
for a server that has separately qualified those requirements. `process-isolation`
also requires the existing engine sandbox configuration and digest; a caller
cannot enable it merely by listing it in the method descriptor.

The runtime fingerprint identifies deployment-declared runtime configuration;
it is not blanket hardware attestation. Package-version/tool checks are separate
observations made before method invocation. Keep their actual scope visible.

Host execution is not a judge isolation boundary. Configure the existing engine
sandbox and read-only runtime mounts for untrusted work. A method importing a
candidate into its own Python process does not protect the judge from that code.
Input files use non-executable JSON in the simple checker example; arbitrary
pickle deserialization is not a service protocol. The full CANNBench bridge asks
for `process-isolation` because its child workers can create new sessions.
