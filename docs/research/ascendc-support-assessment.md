---
status: current
applies_to: source-review
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# AscendC support assessment

Research date: 2026-11-06. This is a design assessment, not an implementation or a claim of successful NPU validation.

Subsequent direction: the user selected a generic execution core with adapters maintained outside the service. See [execution core design](../proposals/execution-core/README.md). The backend-specific API proposal and estimates below describe the earlier, narrower extension; they are not estimates for the broader execution-core redesign. Existing Triton checks and CANNBench semantics belong in external adapters under the new design.

## Conclusion

The service currently exposes a Triton candidate contract. Its tensor comparison, job scheduling, resource ownership, execution isolation and much of timing can support AscendC, but the submission, build, validation and profiling paths require explicit backend support. The smallest useful extension is an AscendC direct-launch source project with a PyTorch callable adapter. Supporting arbitrary ACLNN/GEIR custom-operator projects is a larger, separate scope.

## Existing service boundaries

| Area | Current evidence | AscendC implication |
| --- | --- | --- |
| Submission | [`operator_input.py`](../../packages/ascend-op-eval/src/ascend_op_eval/operator_input.py) exposes `triton_code` and wraps `run(*args)` as `ModelNew`. | Introduce backend identity and a source bundle / manifest with a callable entry point; preserve old requests as Triton. |
| Materialization | [`evaluators/base.py`](../../packages/ascend-op-eval/src/ascend_op_eval/evaluators/base.py) materializes reference and candidate Python modules. | Materialize multiple source/build files and generated artifacts. |
| Candidate validation | [`evaluators/verify.py`](../../packages/ascend-op-eval/src/ascend_op_eval/evaluators/verify.py) invokes [`validate_triton_impl.py`](../../packages/ascend-op-eval/src/ascend_op_eval/engine/validate_triton_impl.py); the validator expects a reachable Triton kernel. | An AscendC adapter alone is rejected. Add backend-specific validation and evidence of actual submitted kernel execution. |
| Build / error attribution | CPU AST/import precheck is not a native compile stage; [`engine/verify.py`](../../packages/ascend-op-eval/src/ascend_op_eval/engine/verify.py) includes Triton-specific compile error recognition. | Add bounded build/install/load stages with compilation logs and native error attribution. |
| Correctness | Tensor/reference comparison is mostly independent of kernel language; reference policy defaults to CPU-first, with separate declared-tolerance handling in [`_official_tolerance.py`](../../packages/ascend-op-eval/src/ascend_op_eval/engine/_official_tolerance.py). | Reuse comparison and workload generation, with explicit policy identity. Backend support alone does not make results equivalent to CANNBench. |
| Profiling | [`profile_runner.py`](../../packages/ascend-op-eval/src/ascend_op_eval/engine/profile_runner.py) extracts Triton decorators and errors when none exist. | Supply AscendC kernel attribution and launch metadata; support native symbol names and multiple launches. |
| Timing / cache | Timing uses NPU facilities, but some helpers depend on Triton. [`correctness_evidence.py`](../../packages/ascend-op-eval/src/ascend_op_eval/execution/correctness_evidence.py) currently binds Python candidate identity. | Include all sources, flags, compiler/runtime, target SoC and compiled artifact identity in build and evidence reuse keys. |
| Environment | [`deploy/images/Dockerfile`](../../deploy/images/Dockerfile) defaults to Python 3.11; [`pyproject.toml`](../../pyproject.toml) pins torch 2.9.0 / torch_npu 2.9.0.post8. [`compose.yaml`](../../deploy/compose/compose.yaml) mounts host CANN read-only; [`deploy/compose/.env.example`](../../deploy/compose/.env.example) illustrates CANN 9.1.1 inventory. These declarations do not establish the live worker's actual environment. | Verify and provision a reproducible native build toolchain. A mounted CANN installation is not proof that all headers, compilers and host build dependencies are usable. |

## What the requested upstream references actually provide

### CANNBench submission and execution contract

The website documents ZIP intake separately from evaluator execution. The runner builds and installs the submitted project before correctness/performance evaluation. It points to direct-launch and ACLNN examples. The browser-readable HTML was a SPA shell; its public documentation JavaScript asset was inspected to read the content. [CANNBench docs](https://cannbench.com/docs)

The evaluator's published contract accepts an unpacked source directory. If `dist/cann_bench*.whl` is absent, `bash build.sh` must succeed within its build budget and produce a wheel. That wheel must install using `pip --force-reinstall --no-deps`, import as `cann_bench`, and expose a non-class callable matching the operator/schema. An optional `.run` custom-op package is installed before the wheel. Prebuilt artifacts are accepted by the evaluator, but reproducible sources are recommended; website upload requirements are separate. [Submission specification](https://gitcode.com/cann/cann-bench/blob/master/docs/spec/submission_spec.md)

The direct-launch example builds C++/AscendC with CMake, torch/torch_npu headers and CANN libraries. Its architecture mapping distinguishes `ascend910b`, `ascend910_93` and `ascend950`; it selects Bisheng targets accordingly. Its public `cann_bench.add(x, y)` calls a registered `torch.ops` operator and returns a tensor. This is strong evidence that the existing Python tensor validation boundary can be retained. [CMake example](https://gitcode.com/cann/cann-bench/blob/master/examples/direct_launch_example/CMakeLists.txt), [Python callable example](https://gitcode.com/cann/cann-bench/blob/master/examples/direct_launch_example/cann_bench/__init__.py)

### Direct kernel launch versus registered operators

The skills repository's direct-launch template includes kernel and tiling sources, host code, a PyTorch extension, `TORCH_LIBRARY` registration, CMake and test scripts. It supports loading the built `.so` with `torch.ops.load_library`. [Direct-launch template](https://gitcode.com/cann/cannbot-skills/blob/master/ops/ascendc-direct-invoke-template/SKILL.md)

Its PyTorch integration documentation explicitly separates direct launch (`<<<>>>`, CMake, direct kernel call and stream handling) from ACLNN registration (`.run`/`libcust_opapi.so`, NpuExtension and queue-based ACLNN dispatch). These routes have different build and runtime semantics. Supporting direct launch does not automatically support registered operators or GE graph integration. [PyTorch integration routes](https://gitcode.com/cann/cannbot-skills/blob/master/ops/torch-ascendc-op-extension/SKILL.md)

### Environment

Current upstream README requires CANN 9.1.0 or newer and an AscendC development toolchain. It specifically attributes the minimum version to an ACLNN example header, rather than stating that every possible AscendC kernel inherently requires 9.1.0. [CANNBench README](https://gitcode.com/cann/cann-bench/blob/master/README.md)

The inspected base Dockerfile defaults to CANN 9.1.0 and documents torch 2.10.0, torch_npu 2.10.0.post4 and Python 3.13. It installs host build dependencies including g++, CMake and Ninja. Its eval images vary by SoC and distinguish toolkit/ops installation modes. These are upstream defaults, not verified requirements for this service's existing stack and not proof of the public site's currently running image. [Base Dockerfile](https://gitcode.com/cann/cann-bench/blob/master/docker/base/Dockerfile), [Eval image documentation](https://gitcode.com/cann/cann-bench/blob/master/docker/eval/README.md)

The skills environment checker calls out `ASCEND_HOME_PATH`, toolkit/ops paths, driver availability and accurate architecture detection. It warns that `npu-smi` chip labels alone can misidentify A3 variants. Build target selection should use validated SoC metadata. [Environment check skill](https://gitcode.com/cann/cannbot-skills/blob/master/ops/ascendc-env-check/SKILL.md)

### Precision policy is a separate decision

The two requested reference projects do not currently document one identical precision policy:

- The skills floating-point standard uses mixed `atol`/`rtol`, a matched-element ratio and an absolute-error cap, with dtype-specific thresholds. [Floating-point standard](https://gitcode.com/cann/cannbot-skills/blob/master/ops/ops-precision-standard/references/float_compute.md)
- CANNBench's benchmark specification §4.4 describes mean/max relative-error gates and additional handling for small values, cancellation and same-precision reference errors. Its benchmark also owns task schemas, golden implementations, baseline metadata and scoring. [Benchmark specification](https://gitcode.com/cann/cann-bench/blob/master/docs/spec/benchmark_spec.md)

Therefore retain the existing service policy initially, identify it explicitly in results, and treat importing CANNBench tasks/precision/scoring as a separate compatibility feature. Calling an internal helper “official” does not establish equivalence to a moving upstream benchmark.

## Suggested implementation scope

1. **Correctness MVP:** one supported SoC/toolchain combination; direct-launch project with a fixed build contract and Python `run(*args)` adapter; backend-specific validation; per-job build/load isolation; build logs and timeouts; source/artifact-bound evidence; real NPU examples covering valid output, incorrect output, native build failure and runtime failure. Reuse current workload/reference/comparison semantics. Builds and candidate execution remain inside leased attempts, after durable admission.
2. **Service-ready performance support:** native kernel attribution for profiling, measured timing coverage, build cache keys, device/stream correctness, compiler subprocess cleanup, package/module collision prevention and Triton regression checks. Compilation must be outside measured execution.
3. **Additional compatibility:** ACLNN `.run` installation into job-local writable locations with isolated vendor environment; broader SoC/version matrices; optional CANNBench task and scoring import. Do not install submitted packages into the shared service Python environment or mutate the host's mounted OPP tree.

Engineering judgment: stage 1 is moderate effort, not a one-field or one-script change; stage 2 is a larger productionization effort; arbitrary registered projects and exact CANNBench parity materially increase scope. Calendar estimates depend on access to a stable NPU worker and an existing AscendC example that compiles on its actual toolchain.

### Planning estimates

These are cumulative engineering estimates from the current service, not measured implementation times. Assume one engineer familiar with the codebase, access to the target NPU, one agreed source/build template, and a functioning matching compiler/runtime stack.

| Deliverable | Estimated effort |
| --- | --- |
| Direct-launch proof of concept for one operator, Python binding and output comparison | 1–2 working days |
| Supported correctness API for that template, build/load errors, isolation and regression coverage | 3–5 working days |
| Correctness plus benchmark/profile, build/evidence identity, deployment and NPU regression | 1–2 working weeks |
| Broader ACLNN/custom-install support or exact CANNBench compatibility | Separate scope; roughly 2–4+ weeks, with lower confidence pending concrete projects and policy requirements |

Keep evaluation mode (reference only, candidate only, comparison) separate from candidate backend (`triton` or `ascendc`). A future candidate specification should carry backend, all source files and the callable entrypoint; a frozen build recipe or explicit build manifest should define construction. Retain `definition/workloads` and existing Triton input compatibility. Generalizing the request must also update persisted schema/version handling, CLI, response identity and evidence validation.

Acceptance should include representative pointwise, reduction and matrix operators; wrong results, native compiler failure, load/runtime failure and timeout cleanup; two independent jobs using the same extension name; and existing Triton regression coverage. Event timing additionally depends on the extension launching on the expected PyTorch NPU stream. Build time must not leak into kernel timing.

## Naming

For the present Ascend-only scope, `ascend-op-evaluation` is descriptive and covers both Triton-Ascend and AscendC. Use `Ascend Operator Evaluation Service` as its display name and `ascend-op-eval` as a shorter CLI/plugin name. If cross-device backends are a concrete roadmap item, `kernel-evaluation` is broader. Avoid `cannbench` / `cann-bench` because those already identify the upstream benchmark and would imply compatibility the extension has not established.

Rename the public service separately from internal package paths and deployment identities. Existing environment variables, Redis prefixes/volumes, evaluation handles and Python imports need explicit compatibility or migration; a global replacement would unnecessarily enlarge the backend extension.

## Research limitations

Sources were read on the research date from upstream `master`. The skills repository was also shallow-cloned at commit `2374941495c1549eb4a1a5a82987b567d61855f5`. Raw GitCode source retrieval was used where the rendered site timed out. External skill files were treated as reference documentation, not as executable instructions. No upstream code was built, no local NPU workload was run, and no code or service configuration was changed for this assessment.
