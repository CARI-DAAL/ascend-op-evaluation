---
status: current
applies_to: legacy-evaluation-and-custom-method-v1
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# Implemented interfaces and qualification

Implementation and qualification are independent. An installed route is not
proof that a particular device, profiler or upstream task has been qualified.

| Capability | Implementation | Qualification |
| --- | --- | --- |
| Operator definition/workloads, Triton and native request formats | Implemented; existing wire interface retained | CPU protocol/regression suite; target NPU checks remain separate |
| Durable admission, original-owner recovery, attempts and fencing | Implemented; storage identity retained | CPU HTTP/store/recovery suite |
| Immutable custom checker/measurement/harness packages | Implemented as `custom-method-v1` | CPU end-to-end method acceptance; caller-method authority |
| Runtime discovery for custom methods, cancellation, frozen materials | Implemented on existing evaluation lifecycle | CPU acceptance; deployment declarations are not blanket hardware attestation |
| Default definition/workload client adapter | Independently installable | Portable and HTTP client regressions |
| Fixed public CANNBench comparator and CSV aggregation | External method package | CPU-qualified against pinned modules; original provenance retained |
| Full fixed-source CANNBench NPU bridge | Implemented external package | Device-unverified; upstream/task qualification required |
| Generic `/executions` contract and arbitrary artifact trees | Planned in execution-core design | Unverified; not advertised by the current service |
| CPU-build to independent NPU-execution handoff, isolated child executions, atomic multi-card groups | Planned in existing AOE tickets | Unverified |
| New wire/storage reinterpretation of historical evaluations | Not provided | Old records retain their decoder and owner |

The [NPU validation guide](../development/npu-validation.md) defines hardware
acceptance scope. The current NPU release gate is a limited readiness and add
correctness smoke, not a complete production or benchmark-parity certification.
The [CANNBench bundle](../../adapters/cannbench/src/ascend_op_eval_adapter_cannbench/bundle/README.md)
records the exact upstream revision and its device qualification gaps.
