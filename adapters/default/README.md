# Default operator client adapter

This independent package owns definition/workload source packaging and the
existing operator CLI semantics. Install it alongside ascend-op-eval-client.
Its implementation is also distributed as a reproducible standard-library
agent-plugin client. It does not import server sources.

The server's current built-in evaluator remains bundled until the separately
planned generic-execution interface supports its worker-side extraction.
