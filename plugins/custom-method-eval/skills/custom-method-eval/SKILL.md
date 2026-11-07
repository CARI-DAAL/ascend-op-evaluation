---
name: custom-method-eval
description: Register and run versioned external checker, measurement or harness methods through an evaluation service. Use for custom-method package upload, parameterized execution, artifacts, cancellation and recovery; use the adapter-design skill for design-only work.
---

# Run external evaluation methods

Use the bundled [standard-library CLI](scripts/custom_method_eval.py). Resolve
its path from this skill directory; it needs no service or Torch installation.
The service must implement `custom-method-v1`.

## Method and input preparation

`pack --manifest method.json --output package.json` reads a descriptor and explicit
relative source-file list. It never imports or executes those files locally.
`upload --manifest method.json` packages and registers in one step, or use
`upload --package package.json`. Record the returned immutable method reference.

Upload binary/JSON inputs and dependency resources with
`artifact-upload --file PATH --media-type TYPE`. Use the returned artifact refs
in the method descriptor's dependencies or submission's named input map. Register
dependencies before the method. `alias NAME METHOD_REF` sets a caller-owned alias;
the service freezes its target during admission.

## Execute and recover

Set `EVALUATION_URL` and `EVALUATION_CAPABILITY_FILE`; credentials are never stored
in handles. Use:

```bash
python3 /path/to/custom_method_eval.py submit --method METHOD_REF_OR_ALIAS \
  --parameters parameters.json --inputs input-refs.json --save-handle handle.json
python3 /path/to/custom_method_eval.py recover --handle handle.json
python3 /path/to/custom_method_eval.py get EVALUATION_ID
python3 /path/to/custom_method_eval.py progress EVALUATION_ID
python3 /path/to/custom_method_eval.py cancel EVALUATION_ID
python3 /path/to/custom_method_eval.py output EVALUATION_ID report.json --output report.json
python3 /path/to/custom_method_eval.py materials EVALUATION_ID --output frozen-method.json
```

The handle is saved before POST and updated when an ID is received. Keep the
owner, key and request unchanged after transport ambiguity. Recovery rejects a
different owner URL; polling ignores arbitrary response Location headers.
Wait expiry does not cancel work. Running cancellation is complete only after
the service acknowledges cleanup; preserve that distinction in reporting.
`materials` exports the admitted package, dependencies, inputs and effective
configuration privately; it remains the recovery source if a registry alias or
registry TTL changes. Treat that export as source/data material, not credentials.

## Interpret evidence

Inspect `result.method`, its outcome, method identity, requested/effective
parameters, report, logs and artifacts. A valid checker report with passed=false
is a comparison failure; method/protocol/environment errors are different outcomes.
Caller-supplied method reports are not service-certified candidate correctness.
Full harnesses may share a process with candidate code; do not claim stronger
judge isolation than the actual runtime provides.

Preserve units, samples, aggregation and raw artifact identities for measurement.
Do not substitute built-in mean timing for an upstream protocol. A CPU parser
test on synthetic captures is not an NPU timing or leaderboard-parity result.

For detailed invocation flags, run the corresponding subcommand's `--help`.
