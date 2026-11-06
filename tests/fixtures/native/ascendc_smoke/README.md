# Native AscendC service smoke project

Three intentionally small scalar AscendC kernels exercise add, reduction and
matrix multiplication with contiguous float32 inputs, including non-aligned
sizes. They are integration examples, not optimized kernels or timing baselines.
Their `.asc` kernels perform the arithmetic on the NPU; the PyTorch extension
only validates inputs, allocates output and launches the kernel.

The CMake ASC host-stub pattern and current-stream integration were checked
against the pinned [official direct-launch template](https://gitcode.com/cann/cannbot-skills/tree/2374941495c1549eb4a1a5a82987b567d61855f5/ops/ascendc-direct-invoke-template/references/add_custom).
This project contains independently written test kernels. The wrapper requests
`getCurrentNPUStream().stream(true)` before direct launch, flushing the framework
queue. Event timing is nevertheless disabled in the manifests until separately
qualified on the deployed stack.

Requirements: target NPU, CANN with the ASC CMake package and Bisheng, CMake
3.19+, matching torch/torch_npu headers and libraries, and a worker runtime that
exports ASCEND_HOME_PATH and can find ASC. The sample compiler target is
dav-2201; choose and verify the target matching the actual worker. These sources
have not been compiled or executed on NPU by the CPU test suite.

Each operation has its own `.native.json`, `.definition.json` and
`.workloads.jsonl`. The manifest contains an explicit file list relative to its
own directory. `build.sh` accepts compiler architecture as argument 1 and the
intentional add-error switch (`ON`/`OFF`) as argument 2. The negative fixture
changes arithmetic inside the NPU kernel; it does not substitute CPU results.

Use `scripts/npu_native_gate.py` from the repository root for the HTTP gate.
A failing build is a failed gate, not a skipped success. Keep the resulting
report and its actual worker provenance with the tested revision.
