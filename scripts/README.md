# Supported commands

Run commands from the repository root in the configured Python environment.
Worker and preparation CLIs expose `--help`; preparation outputs belong outside
the checkout. The API entrypoint starts the configured listeners.

| Task | Commands | Guide |
| --- | --- | --- |
| Compose deployment | `compose.sh`, `deployment_preflight.py` | [Deployment](../docs/operations/deployment.md) |
| Release identity | `release_manifest.py` | [Release identity](../docs/reference/release-identity.md) |
| Automatic release PR and publication | `python -m scripts.release_pr` | [Release workflow](../docs/reference/release-identity.md#automated-release-prs) |
| Manual API/worker startup | `ascend-op-eval-server api`, `ascend-op-eval-server worker --cpu`, `ascend-op-eval-server worker --card 0` | [Deployment](../docs/operations/deployment.md) |
| Host workers and API | `start.sh`, `stop.sh`, `dl_wheels.sh` | [Deployment](../docs/operations/deployment.md) |
| Host smoke and limited NPU checks | `test_eval_service.py`, `npu_release_gate.py` | [Tests](../tests/README.md) |
| Separate versus combined timing and trace | `npu_feedback_comparison.py` | [Feedback measurements](../docs/research/feedback-performance.md) |
| Profiler and sandbox preparation | `prepare_profiler_runtime.py`, `prepare_engine_runtime_overlay.py` | [Profiler runtime](../docs/operations/profiler-runtime.md) |
| Profiler diagnostics | `probe_profiler_latency.py`, `replay_profiler_export.py` | [Profiler runtime](../docs/operations/profiler-runtime.md) |
| Reference-cache index | `reference_cache_index.py` | [Reference cache](../docs/operations/reference-cache.md) |

`npu_release_gate.py` currently reports readiness and add-correctness smoke
coverage, not complete production calibration. It fetches the target's live
OpenAPI schema for its report; schema files are not startup dependencies.

The reusable caller CLI is bundled in the
[Ascend Op Eval plugin](../plugins/ascend-op-eval/README.md); `scripts/` keeps service
startup, deployment and diagnostic tools.

Retired compilation experiments are recorded in [Git history](../docs/migration/history.md).

`npu_batchmatmul_gate.py` validates the pinned 51-case official BatchMatmul fixture
and runs its correctness/timing/profile checks through the HTTP API. Use
`--check-only` for file integrity without device execution. The
[NPU validation plan](../docs/development/npu-validation.md) describes its scope.
