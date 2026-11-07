"""Check repository Markdown links, current-page status and retired path references."""

import argparse
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^\s)]+)\)")


def check(root: Path) -> list[str]:
    errors = []
    documents = [*root.glob("*.md")]
    for directory in ("docs", "plugins", "packages", "adapters", "tests", "scripts"):
        documents.extend((root / directory).rglob("*.md"))
    for path in documents:
        if any(part in {"vendor", ".egg-info", "build", "__pycache__"} for part in path.parts):
            continue
        content = path.read_text()
        for target in LINK.findall(content):
            if target.startswith(("#", "https:", "http:", "mailto:", "plugin:", "app:")):
                continue
            target = unquote(target.split("#", 1)[0]).strip("<>")
            destination = (path.parent / target).resolve()
            if not destination.exists():
                errors.append(f"{path.relative_to(root)}: missing {target}")
        if path.is_relative_to(root / "docs/plans"):
            if ".scratch/ascend-op-eval/" in content:
                errors.append(f"{path.relative_to(root)}: formal plan points to scratch")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    errors = check(ROOT)
    if errors:
        print("\n".join(errors))
        return 1
    print("Repository documentation links and formal plan references passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
