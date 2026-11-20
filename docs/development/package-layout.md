---
status: current
applies_to: legacy-evaluation-and-custom-method-v1
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# Package layout and dependencies

The root pyproject configures tools. Each installable package has its own
pyproject and `src` tree. Install a package by its directory; a checkout root
installation no longer selects an implicit service distribution.

| Package | Owns | Dependencies |
| --- | --- | --- |
| `packages/ascend-op-eval` | HTTP, durable control, workers, execution, runtimes, device health and method registry | Lightweight server dependencies; Torch/NPU stack is an explicit runtime extra |
| `packages/ascend-op-eval-client` | Custom-method transport, immutable package submission, recovery and user command dispatch | Standard library |
| `adapters/default` | Definition/workload client packaging and operator command semantics | Client package |
| `adapters/cannbench` | Fixed upstream method packages and harness preparation | Client package; actual method runtime requirements remain in descriptors |
| `packages/ascend-op-eval-compat` | Deprecated Python namespace aliases sharing canonical module identities | Server package |

Within the server, `control/` owns existing durable resource state, `execution/`
owns worker lifecycle and execution helpers, `runtimes/` owns sandbox/environment
and profiler runtime policy, and `resources/` owns device health. `methods/`
owns the implemented immutable method contract and registry. Installed process
entrypoints live in `entrypoints/`; repository startup modules are wrappers.

## How an evaluation reaches a device

| Responsibility | Implementation | Contract with the next module |
| --- | --- | --- |
| Prepare a request | Client and evaluation adapter | Request, caller capability and instance-specific recovery handle |
| Admit or recover it | HTTP routes and `control/instance.py` | Durable identity and deadline in the instance's Redis store |
| Claim and complete an attempt | `execution/worker.py` and `control/broker.py` | Lease for the selected execution class, fenced publication |
| Collect evidence | `evaluators/`, built-in engine or packaged method | Check outcomes and artifacts for the admitted request |

The API and worker entrypoints share [Redis assembly](../../packages/ascend-op-eval/src/ascend_op_eval/entrypoints/storage.py).
Each process has a durable connection for state transitions and a separate
bounded connection for metrics and advisory caches. Deployment selects the
interpreter, toolkit, cards and Redis instance. The deployment-specific inputs
and launchers live together under [`deploy/`](../operations/deployment.md).

## Existing operator pipeline and planned extraction

The built-in operator input translator, `evaluators/` and vendored `engine/`
remain bundled to preserve current checks, state and evidence. Current operator
routes still depend on those models. The rename does not assert that generic
execution extraction has already been implemented.

The default adapter package currently owns the **caller-side** task-format
translation; it does not yet replace the worker's built-in evaluator. Moving
that evaluator and task-specific caches behind the future execution contract is
tracked by AOE-09/10/12/19. The CANNBench bridge already uses the external
custom-method path and is not imported by the service.

The [execution-core plan](../plans/ascend-op-eval/spec.md) contains those functional
changes and their acceptance requirements. Package moves do not satisfy their
hardware, isolation or parity gates. Avoid empty placeholder modules for future
capabilities; add them when implementing their actual interface.

## Portable artifacts

`python -m scripts.build_plugins` copies the canonical default-adapter client to
the new and compatibility operator plugins and the canonical method client to
the custom-method plugin. `--check` detects drift without writing. Archives run
without server sources or installed third-party dependencies.

Keep the CANNBench vendored modules byte-identical. The examples directory points readers to the external package's canonical
bundle. Upload manifests from that regular-file directory; the client's
symlink-rejection policy remains unchanged.
