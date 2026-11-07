# Fixed public CANNBench method examples

Upstream revision: **f0488d95b4d44a6a0da1b8cd99e91fbd06181962** (framework
1.0.0, task package 2.0.0). No code in the service imports CANNBench. These
external packages run only inside an admitted method process.

## CPU-qualified components

- `checker.method.json` invokes byte-identical upstream `compare_tensors`, with
  actual/reference/optional native-reference Tensor documents. It supports the
  comparator's per-dtype `custom_thresholds`; defaults use the pinned tables.
- `measurement.method.json` invokes the actual `KernelDetailsStrategy` against
  an input `kernel_details.csv`. It preserves **sum of per-kernel medians** and
  does not substitute Event timing or mean-of-call-totals. Its samples are the
  upstream per-kernel medians, explicitly labelled, with original CSV retained.

Use `custom_method_eval.py upload --manifest ...` and named artifact inputs as
in the service guide. The checker descriptor pins `torch==2.9.0+cpu`, the local
validation environment. A different runtime needs a deliberately updated
descriptor/version and requalification, not an invisible dependency fallback.

The Tensor document format is a nonempty `outputs` list of objects with dtype,
data and optional shape. Multiple tensor outputs and integer values are supported.
The strings `nan`, `+inf`, `-inf` encode special floating values without nonfinite
JSON literals. Arbitrary tensor layouts, aliases and opaque pickles are not this
example's data transport. Use the full harness for actual task hooks and layouts.

The upstream scalar `threshold` argument is not an effective per-output override
in this snapshot: per-output comparisons select their dtype's threshold instead.
The package deliberately exposes the effective `custom_thresholds` map and rejects
an unknown scalar threshold parameter. This is why source-level consumption tests
are required even when a field appears in upstream documentation.

`vendor/` retains exact upstream module bytes, copyright headers and LICENSE.
`vendor/provenance.json` records source paths and SHA-256 values. Namespace
initializers are local; no upstream algorithm was rewritten.

## Full NPU harness bridge — implemented, device-unverified

`prepare_harness.py` builds an explicit task-scoped archive directly from git
objects at the fixed revision, not potentially dirty working-tree files. Obtain
that revision in a local upstream checkout, then prepare an independent source
project with the upstream `build.sh` / `cann_bench` package contract.

```bash
python3 examples/custom_methods/cannbench/prepare_harness.py \
  --upstream /path/to/cann-bench --task-path tasks/level1/exp \
  --candidate /path/to/submission --candidate-files candidate-files.json \
  --torch-version 2.9.0 --torch-npu-version 2.9.0.post8 \
  --output /tmp/cannbench-method
```

`candidate-files.json` is an explicit JSON array of relative regular files;
include `build.sh` and every source/header/packaging file required by that project.
Packing never runs the build. Upload every generated `upstreamNN.bin` dependency
as an artifact first (its content SHA already appears in generated method.json),
then upload the generated method manifest and candidate.tar.gz. Submit with an
input map `{"candidate":"sha256:..."}`, the desired supported parameters, and an
explicit adequate parent deadline (for example `--deadline-seconds 3600`). The
parent deadline always bounds the longer per-build/per-operator settings.

The bridge runs the original staged or single upstream CLI, on logical device 0
of the service-assigned NPU. It creates a private venv for upstream wheel
installation, keeps declared worker packages accessible read-only, and sets the
upstream-supported `MC2_OPP_INSTALL_ROOT` to a private directory for `.run` packages.
It does not modify `ASCEND_OPP_PATH` or install into the shared interpreter.

The runtime must declare Python, NPU and **process-isolation** capabilities and
provide compatible CANN headers, compilers, libraries, Torch/NPU packages and
profiler tools. Use a validated sandbox/PID namespace; host process-group cleanup
alone does not contain arbitrary detached upstream workers. Compilation, NPU
execution, profiler rendering and actual task parity have **not** been qualified
in this CPU development environment.

Supported controls include execution_mode, operator/case selection, warmup,
repeat, profiler_level, eval_seed, input_dist, build/operator timeout,
perf_metric_strategy, batch_cases and no_perf. See harness.method.json for exact
defaults and constraints. Every option is passed as an argv token to the pinned
entrypoint. Other Config/BenchConfig hooks require another method package or
explicit extension; they are not accepted and then ignored.

Archives are bounded to eight 512 KiB dependency chunks, 64 MiB expanded upstream,
and a 1 MiB compressed candidate input. Output artifacts must fit the service
limits (at most 1 MiB each, total configured budget). A full suite or large PROF
capture can exceed them. Select a smaller **explicit** task scope or extend
storage capacity; never silently drop requested data.

The wrapper returning a valid report means the harness invocation completed.
Inspect `report.completed`, upstream `exit_code`, and the original reports for
build errors, case failures, baseline and HAP scores. No wrapper field certifies
online leaderboard equivalence.

## Verification scope

| Capability | Status and evidence |
| --- | --- |
| Per-dtype numeric threshold changes | CPU verified against actual pinned comparator, positive/negative and zero threshold |
| Composite outputs / large exact integer mismatch | CPU verified through pinned code and JSON transport |
| Repeated/multiple kernel aggregation | CPU verified against actual pinned strategy; known fixture gives 200 us rather than 101 us |
| Conditional launch example | CPU verified in the generic external method; full upstream capture topology remains device-unverified |
| Hashes, archive path rejection, private pip installation | CPU verified |
| Method upload/submit/report/artifact flow | Public integration gate supplied; records actual execution on the selected instance |
| Full source/task archive and upstream CLI bridge | Implemented; actual frozen checkout packaging/NPU execution still needs server validation |
| CANN native compilation, stream synchronization and profiler capture | Not locally verified |
| Full AccuracyEvaluator proto contracts, all generator/hooks, guards, HAP | Delegated unchanged to full harness; not covered by the numeric-only component |
| All upstream Config/BenchConfig/env parameters | Not claimed; supported subset is explicit in the package schema |
| Multi-NPU/multi-host tasks and large PROF exports | Not supported by this bounded single-device example |
| Exact website deployment or hidden cases | Unknown; no claim of coverage |

For server acceptance, freeze the same source/data/config/environment, run the
upstream entrypoint directly and through this method, retain both raw reports,
and compare correctness, coverage, errors and score. Set timing tolerances before
collecting paired samples. Include wrong outputs, boundary precision, build/run
failures and multi-kernel cases. CPU mocks, skipped checks or exit=0 cannot replace
that device and upstream-differential evidence.
