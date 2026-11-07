# External CANNBench method adapter

This independently installable package carries the existing fixed-source
comparator, measurement and full-harness method bridge. Prepare fixed-source
bundles with `ascend-op-eval-cannbench-prepare --help`. Register generated method
packages through `ascend-op-eval methods`.

See [bundle documentation](src/ascend_op_eval_adapter_cannbench/bundle/README.md)
for exact upstream provenance, CPU qualification and NPU qualification gaps.
The examples path links to this canonical bundle; the service never imports it.
