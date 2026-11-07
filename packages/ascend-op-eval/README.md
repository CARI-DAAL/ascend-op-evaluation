# Ascend Op Eval service

Install this package with `pip install ./packages/ascend-op-eval`. Start installed
processes with `ascend-op-eval-server api` or `ascend-op-eval-server worker --cpu`.
Server settings use `ASCEND_OP_EVAL_*`; legacy names remain accepted with conflict
detection. Existing durable record and HTTP contracts are preserved.

The base installation is CPU-control-only; a device worker needs the declared
`npu` extra and separately prepared host CANN/driver/runtime. Read the repository
operations and migration guides before upgrading an existing deployment.
