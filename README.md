# Ascend Op Eval

Evaluate Ascend operators with Triton, native AscendC, or packaged custom methods.
Submit work to a separately deployed Ascend instance and recover the same admitted
request after a client disconnect. Correctness, timing, profiling and execution
failures retain their distinct evidence.

The project name is **ascend-op-eval** and the Python namespace is
`ascend_op_eval`. The Git remote retains its existing URL until the repository
owner performs the remote rename. [Upgrade instructions](docs/migration/rename-and-cutover.md)
cover the former Triton names and existing durable state.

## Quick start

Install the lightweight client and default operator adapter from a checkout:

```bash
python -m pip install ./packages/ascend-op-eval-client ./adapters/default
export ASCEND_OP_EVAL_CLIENT_URL=http://YOUR_ASCEND_INSTANCE:11907
export ASCEND_OP_EVAL_CLIENT_CAPABILITY_FILE=/path/to/caller-capability
```

Prepare a definition, workloads and a candidate exporting `run(*args)`:

```bash
ascend-op-eval verify --definition definition.json --workloads workloads.jsonl \
  --triton candidate.py --save-handle evaluation-handle.json
ascend-op-eval get ev_EVALUATION_ID
```

Use `--native-project project/native.json` for a multi-file AscendC candidate.
`benchmark` accepts one implementation or a reference/candidate comparison;
`profile` collects profiling evidence. Single-source measurements are explicitly
correctness-unverified. See the [operator guide](docs/guides/evaluate-an-operator.md)
and [native guide](docs/guides/native-projects.md) for complete inputs and limits.

Custom methods use immutable packages with explicit parameters and runtime
requirements. The client package can use them without the default adapter:

```bash
ascend-op-eval capabilities
ascend-op-eval methods upload --manifest examples/custom_methods/checker/method.json
```

Follow the [custom-method guide](docs/guides/custom-methods.md) for input uploads,
submission, private recovery handles, cancellation and raw output retrieval.
The [portable agent plugin](plugins/ascend-op-eval/README.md) runs with Python's
standard library and carries the same default-adapter client implementation.

## Deploy and develop

Install the service package independently of clients and external adapters:

```bash
python -m pip install ./packages/ascend-op-eval
ascend-op-eval-server --help
ascend-op-eval-server api
ascend-op-eval-server worker --cpu
```

The base service install does not install Torch or an Ascend toolchain. Device
workers require a qualified NPU runtime; use the declared service `npu` extra
and the [deployment guide](docs/operations/deployment.md). Compose and host
entrypoints live in `deploy/compose/` and `deploy/host/`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for editable installs and CPU validation.
CPU checks do not establish device correctness, timing or upstream task parity.
The [support matrix](docs/reference/support-matrix.md) distinguishes implemented
interfaces from hardware qualification and planned execution capabilities.

## Repository

```text
packages/ascend-op-eval/          HTTP, control, execution, methods and runtimes
packages/ascend-op-eval-client/   Lightweight custom-method client and CLI
packages/ascend-op-eval-compat/   Optional deprecated Python import bridge
adapters/default/                Definition/workload client adapter
adapters/cannbench/              Fixed-public-snapshot external method packages
plugins/                        Agent instructions and portable client artifacts
deploy/                         Compose, host and image build configuration
scripts/                        Release, validation and diagnostic tools
tests/                          Behavioral regressions and immutable fixtures
docs/                           Guides, reference, explanations and plans
```

The existing built-in operator implementation remains bundled during the
execution-core transition; its current dependencies and pending extraction are
recorded in the [package layout](docs/development/package-layout.md). Generic
execution design is tracked separately from this naming and layout migration.

## Documentation

[Documentation index](docs/README.md) · [Domain vocabulary](GLOSSARY.md) ·
[Naming rules](docs/reference/naming.md) · [Release identity](docs/reference/release-identity.md) ·
[Recovery](docs/operations/recovery.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)

The live service publishes `/openapi.json` and `/docs`. Existing operator routes
and `custom-method-v1` retain their wire and storage meanings. Proposed
`/executions` operations are not advertised as implemented.

## Third-party source

Bundled engine sources retain their Huawei copyright headers and CANN Open
Software License 2.0 references. The complete CANN license text is absent from
this checkout and remains a redistribution review item. Input generation retains
its included Apache-2.0 license and fixed NPUKernelBench attribution. CANNBench
method packages retain byte-identical upstream modules, provenance and license.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for their locations.
No repository-wide license has been selected for the remaining source.
