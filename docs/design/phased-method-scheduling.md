# Phase-split method scheduling: build on CPU workers, run on NPU workers

> Issue draft — target: `ascend-op-eval` service. Author: campaign agent
> (A3 host), 2026-11-09. Status: proposal, ready for development.

## Problem

A method evaluation is an atomic lease on one NPU worker card, but the
method's own work is two very different workloads:

1. **build phase** — extract candidate, create private venv, `bash
   build.sh` (AscendC/bisheng cross-compile). Pure host-CPU work: observed
   ~50 cores busy for 20-40 minutes on L4 kernels while the card sits idle.
2. **run phase** — install wheel, execute 20 cases + profiler. Actual NPU
   work: 3-8 minutes.

Evidence from the A3 campaign (2026-11-08, 5-card pool): two concurrent
AscendC builds each burned ~26 hours of CPU (≈48 cores) inside 32 wall
minutes while holding a card each; the whole queue behind them waited on
idle silicon. Throughput ≈ cards ÷ (build+run), so build time is the
dominant throughput term. Two L4 operators (`fused_causal_conv1d`,
`selective_scan`) repeatedly died on the 3600s deadline purely from build
time.

## Design constraint that makes this easy

The upstream cann-bench evaluator (frozen `f0488d95`) already has a
no-source path intended for pre-installed packages:

```python
# src/kernel_eval/staged_eval.py::_install_or_scan
if not args.source_dir:
    return pm.prepare_skip_build()
```

So "evaluate an installed wheel" is an upstream-supported, byte-identical
evaluation path. We only need the service to produce that installed wheel
somewhere cheaper.

## Proposed architecture

```
caller ──submit──▶ service admission (unchanged contract: submit → result)
                     │
                     ├─ Phase A on a CPU worker:
                     │    sandbox (no device nodes)
                     │    extract candidate.tar.gz
                     │    private venv (pip from read-only runtime)
                     │    bash build.sh   (NPU_ARCH=ascend910_93, CANN toolkit RO-mounted)
                     │    → dist/cann_bench*.whl uploaded as a stage artifact
                     │    compile failure → terminal result (compile_failed report, as today)
                     │
                     └─ Phase B queued for an NPU worker:
                          sandbox (device nodes, as today)
                          private venv ← pip install <stage-A wheel>
                          kernel_eval.staged_eval WITHOUT --source-dir
                          (prepare_skip_build path) → same official
                          correctness/perf pipeline → raw reports → result
```

- **No upstream changes.** Both phases run our method bundle code; phase B
  uses the upstream CLI's existing no-source mode.
- **Wire contract unchanged.** Callers still see one evaluation; the phase
  split is internal orchestration.
- **Anti-cheat unaffected.** The website still builds fresh from source at
  submission time; this only changes our internal loop economics.
- **Alignment preserved.** Phase B evaluates the exact bytes phase A
  produced through the same upstream checker/profiler; differential
  validation vs the current single-phase path is the acceptance gate.

## Suggested implementation notes

- `MethodExecution` gains optional `stages` in the method descriptor
  (default: single stage = current behavior). A staged method declares
  `[{device: cpu, entry: build}, {device: npu, entry: run}]`.
- Stage handoff storage — NOT the method artifact registry (its 1MB
  per-artifact cap and 64MB/caller quota are for method *code*; built
  wheels are data, AscendC `_C.so` wheels run tens of MB):
  - Primary (single-container deployments, like ours): a content-addressed
    spool on the shared engine filesystem,
    `$ENGINE_DIR/stage-spool/<sha256>/cann_bench.whl`. Phase A writes it
    and records the digest in the execution record; phase B's sandbox adds
    the spool path as a read-only mount and verifies the digest before
    install. Spool limits: ≤256MB per wheel, retention = evaluation life
    + 24h, deleted when phase B completes.
  - Fallback (multi-host): chunked upload into the existing registry,
    mirroring the method bundle's `upstreamNN.bin` 512KB-chunk pattern
    (sha-verified reassembly); costs caller quota, documented as the
    cross-host path only.
- Lease/scheduling: phase A admits to CPU workers (already exist via
  `--cpu`); phase B enters the NPU queue only when the artifact is ready.
  One evaluation = one lease per stage, not one card lease for the whole
  life.
- Failure semantics: phase A failure = terminal `compile_failed` result
  (same report shape the harness emits today); phase B failures unchanged.
- Card-hold accounting: metrics should now report build_ms (CPU stage) and
  run_ms (NPU stage) separately for queue telemetry.

## Expected impact

- NPU card hold per evaluation: 10-40 min → 3-8 min (**throughput ×3-5**).
- L4 AscendC operators stop timing out on the 3600s deadline (deadline
  applies per stage).
- Agent feedback latency drops proportionally; the evolution loop's inner
  cycle gets faster for free.

## Acceptance

1. Differential: for N ≥ 5 operators (mix of triton/AscendC), single-phase
   and phased executions produce identical correctness outcomes and perf
   scores within run-to-run noise (same wheel bytes ⇒ same scores).
2. Compile-failure candidates return the same `compile_failed` report
   shape from phase A without ever entering the NPU queue.
3. No regression on the existing single-stage path (default descriptor).
