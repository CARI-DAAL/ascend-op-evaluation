# Ascend Op Eval client

A standard-library client for custom-method-v1 package submission and recovery.
Install the default adapter separately for `verify`, `benchmark`, `profile` and
existing operator evaluation commands. `ascend-op-eval methods --help` exposes
the immutable method workflow; `ascend-op-eval capabilities` reads the current
method runtime capabilities.

Use `ASCEND_OP_EVAL_CLIENT_URL` and `ASCEND_OP_EVAL_CLIENT_CAPABILITY_FILE`, or
explicit command flags. Old EVALUATION settings remain supported; differing
old/new values fail without exposing credentials.
