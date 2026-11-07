"""The custom method plugin stays portable and its examples have real schemas."""

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/custom-method-eval"


def test_custom_method_plugin_runs_from_an_isolated_archive(tmp_path):
    archive = tmp_path / "plugin.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in PLUGIN.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                zipped.write(path, path.relative_to(PLUGIN))
    isolated = tmp_path / "isolated"
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(isolated)
    manifest = json.loads((isolated / "plugin.json").read_text())
    for folder in (".codex-plugin", ".claude-plugin"):
        overlay = json.loads((isolated / folder / "plugin.json").read_text())
        for name in ("name", "version", "description", "repository"):
            assert overlay[name] == manifest[name]
        assert (isolated / overlay["skills"] / "custom-method-eval/SKILL.md").is_file()
    for path in isolated.rglob("*.md"):
        for href in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if "://" not in href and not href.startswith("#"):
                target = (path.parent / href).resolve()
                assert target.is_relative_to(isolated) and target.is_file()
    script = isolated / "skills/custom-method-eval/scripts/custom_method_eval.py"
    for action in [[], ["pack"], ["upload"], ["submit"], ["cancel"], ["recover"], ["output"]]:
        result = subprocess.run(
            [sys.executable, "-I", "-S", str(script), *action, "--help"],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0 and "usage:" in result.stdout
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(script), "--version"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0 and result.stdout.strip() == manifest["version"]
