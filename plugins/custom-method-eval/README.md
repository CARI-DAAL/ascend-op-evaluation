# Custom method evaluation client

This portable plugin uses the explicit `custom-method-v1` contract. Its
[skill](skills/custom-method-eval/SKILL.md) and standalone standard-library
[CLI](skills/custom-method-eval/scripts/custom_method_eval.py) support packaging,
method/alias registration, artifact upload/download, submission, polling,
cancellation and recovery. It is independent of the Triton client.

Distribute this directory as one plugin, including the hidden compatibility
manifests. The script runs with Python 3.10+ and does not import the service,
Torch, candidate code or method code locally. Set `EVALUATION_URL` and
`EVALUATION_CAPABILITY_FILE`, or pass `--url` / `--capability-file`.

Use `custom_method_eval.py --help` and each subcommand's `--help` for exact options.
`submit` requires `--save-handle`: the handle is written privately before POST
and stores the original owner, idempotency key and submission, never credentials.
After an ambiguous submission, `recover --handle ...` replays that same request
on its original owner. Changing `--url` to another instance is rejected.

Exit codes: 0 for a successful client operation/completed method, 1 for a checker
false result, 2 for request/transport/method/protocol failures, 3 for a cancelled
execution. A harness completing is not proof its benchmark passed: inspect its
report and upstream exit/score fields. `--no-wait` returns accepted state without
cancelling work; client wait expiry also leaves execution alive.

Input/source artifacts are bounded at 1 MiB by the current service contract.
The client reads only explicitly listed source files and rejects symlink/path
escape. Artifact downloads verify digest and size before replacing the output.
Parameter/schema and runtime requirements are validated by the service; this
client does not convert unknown settings into another evaluation protocol.
