---
status: current
applies_to: legacy-evaluation-and-custom-method-v1
verified_revision: e1dbe98977ebf1634c233fb1bfc127c8d62287f9
owner: maintainers
---

# Release workflow

Service metadata is in `packages/ascend-op-eval/pyproject.toml`; the root
pyproject only configures tools. Client, compatibility and adapter packages have
independent metadata. Plugin client versions agree with their distributed
implementation, independently of the service release number.

Use `python -m scripts.release_manifest consistency` before generating and
binding a release manifest. The [release identity reference](../reference/release-identity.md)
describes the existing format, build identity and verified startup.

The current automatic release PR changes only the service pyproject and
CHANGELOG. It continues to publish the existing service `v*` tag stream so
historical release recovery is preserved. Independent client/adapter publishing
and package-qualified tags require a separate publishing workflow; they are not
implicitly enabled by creating installable packages.

After source moves, regenerate deployment-specific runtime source pins and the
release manifest. Preserve the existing Redis/volume/owner identities described
in [the cutover guide](../migration/rename-and-cutover.md). Publication and
production rollout are separate from local branch validation.
