# Contributing to Ascend Op Eval

Use Python 3.10+ and run repository checks from the checkout root. Package
metadata belongs to each package; the root pyproject configures repository tools.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e 'packages/ascend-op-eval[test,dev]' \
  -e packages/ascend-op-eval-client -e packages/ascend-op-eval-compat \
  -e adapters/default -e adapters/cannbench
python -m pip install torch==2.9.0 --index-url https://download.pytorch.org/whl/cpu
python -m ruff check .
python -m pytest -m 'not npu' -q
python -m scripts.release_manifest consistency
python -m scripts.build_plugins --check
python -m scripts.check_docs
python -m compileall -q packages adapters scripts plugins
git diff --check
```

Use the [test guide](tests/README.md) for focused and device checks. Preserve
fixtures with fixed provenance. Candidate failures, missing evidence and
infrastructure failures must retain their separate meanings. Admission persists
identity before any submitted code executes, and attempts publish through the
existing fencing rules.

Use [GLOSSARY.md](GLOSSARY.md) and the [naming reference](docs/reference/naming.md)
when adding public fields, packages or modules. Document current behavior in
guides/reference/explanation; keep new designs in proposals and experiments in
research. Formal task state belongs in [docs/plans](docs/plans/README.md).

Portable plugin clients are generated from installable sources with
`python -m scripts.build_plugins`. Edit their source modules and regenerate;
verify portable execution without the repository or site packages. When moving
runtime helpers, rebuild source pins and release manifests before deployment.
Keep third-party headers and licenses with their original materials.
