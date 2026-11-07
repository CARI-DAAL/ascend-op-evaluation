---
status: current
applies_to: legacy-evaluation-and-custom-method-v1
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# NPU process labels

Service-owned workers and engine processes set their Linux `comm` name, including
the generated profiler runner and single-implementation benchmark. The short
name fits the kernel's 15-byte limit. `setproctitle` is optional for the short
name; when installed, it also supplies a longer title for `ps`.

| Example | Meaning |
| --- | --- |
| `Eval-Idle` | Worker with no assigned evaluation; it may retain its device allocation |
| `AscC-WBld-a1b2` | Worker supervising the native build for an evaluation ending in `a1b2` |
| `Trit-WVfy-a1b2` | Worker supervising correctness for that Triton evaluation |
| `AscC-Vfy-a1b2` | Native/AscendC verification engine before a case is selected |
| `Trit-Bench-a1b2` | Triton benchmark engine |
| `AscC-V003-a1b2` | Candidate verification, original workload number 3 |
| `AscC-R003-a1b2` | Reference execution/measurement for that same native evaluation |
| `AscC-C003-a1b2` | Output comparison for workload 3 |
| `Trit-B003-a1b2` | Candidate measurement for workload 3 |
| `AscC-P003-a1b2` | Profiler/trace execution for workload 3 |

`AscC` denotes the native-project path, `Trit` Triton, and `PyT` a Torch-only
request. These labels describe the submitted implementation, not proof of which
kernel language executed. A reference phase retains its evaluation's backend
prefix. `Input`/`I003` denotes input materialization and `Load` source/model loading.
Worker phase labels start with `W`; engine labels do not.

The workload number is **one-based**, so `003` corresponds to API `case_idx=2`.
The four hexadecimal characters are the evaluation ID suffix, not a unique
identifier: use PID plus the full evaluation/attempt IDs in worker logs or the
long title to disambiguate retries and suffix collisions.

```bash
npu-smi info
ps -ww -eo pid,comm,args
```

With `setproctitle`, the long title includes role, backend, phase, complete
evaluation ID, attempt ID and case number. Without it, `comm` still has the
short label and the original command line remains available. Workers restore
their idle identity when an evaluation finishes or raises.

Names follow **host execution stages**. They are not kernel timing events or
proof that asynchronous NPU queues are idle. Name changes occur outside measured
candidate invocations and do not introduce device synchronization.

## Scope and rollout

The worker passes sanitized task metadata through the engine environment and
the configured sandbox; no source code, credentials or caller-supplied operator
names are included. Naming failures never determine a correctness verdict.

This covers service-owned Python entrypoints. Compilers, shell commands and
programs independently spawned by a submission retain their tool names; `exec`
does not preserve a previously set kernel process name. A custom Python NPU
runner can opt into the inherited task context before loading the device runtime:

```python
from ascend_op_eval.execution.process_title import set_stage

set_stage("benchmark", initialize=True)
```

Deploy the updated service/engine package and restart workers. Regenerate pinned
runtime/source manifests using the existing release procedure where required.
Updating the client plugin alone does not change server process names.

CPU regression tests read real `/proc` names, including a real sandbox child,
generated profiler runners, task-context cleanup and the no-setproctitle path.
On the NPU server, run one Triton and one native verify/benchmark/profile request,
observe their names with the commands above, and confirm workers return to idle.
Actual `npu-smi` rendering still requires that server check.
