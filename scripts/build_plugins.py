"""Build or check portable clients from their independently installable sources."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def artifacts():
    operator = ROOT / "adapters/default/src/ascend_op_eval_adapter_default/client.py"
    methods = ROOT / "packages/ascend-op-eval-client/src/ascend_op_eval_client/methods.py"
    yield (
        ROOT / "plugins/ascend-op-eval/skills/ascend-op-eval/scripts/ascend_op_eval.py",
        operator.read_bytes(),
    )
    yield (
        ROOT / "plugins/triton-eval/skills/triton-eval/scripts/triton_eval.py",
        operator.read_bytes(),
    )
    yield (
        ROOT / "plugins/custom-method-eval/skills/custom-method-eval/scripts/custom_method_eval.py",
        methods.read_bytes(),
    )
    current = ROOT / "plugins/ascend-op-eval"
    legacy = ROOT / "plugins/triton-eval"
    for name in ("plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        metadata = json.loads((current / name).read_bytes())
        metadata["name"] = "triton-eval"
        yield legacy / name, (json.dumps(metadata, indent=2) + "\n").encode()
    skill = (current / "skills/ascend-op-eval/SKILL.md").read_text()
    skill = skill.replace("name: ascend-op-eval", "name: triton-eval", 1)
    skill = skill.replace("scripts/ascend_op_eval.py", "scripts/triton_eval.py")
    yield legacy / "skills/triton-eval/SKILL.md", skill.encode()
    yield (
        legacy / "README.md",
        (
            b"# Deprecated triton-eval plugin\n\n"
            b"Use [Ascend Op Eval](../ascend-op-eval/README.md) for new installations. "
            b"This compatibility artifact carries the same standalone operator client "
            b"and retains its old installation and script paths.\n"
        ),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    drift = []
    for target, content in artifacts():
        if target.exists() and target.read_bytes() == content:
            continue
        if args.check:
            drift.append(str(target.relative_to(ROOT)))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    if drift:
        parser.exit(1, "Regenerate portable clients: " + ", ".join(drift) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
