"""Public installation names retain protocol, recovery and module identity."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from ascend_op_eval.config import Settings, command_environment

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_settings_preserve_durable_namespace(monkeypatch):
    monkeypatch.setenv("ASCEND_OP_EVAL_API_PORT", "12001")
    monkeypatch.setenv("ASCEND_OP_EVAL_CARD_CANARY_ON_STARTUP", "false")
    settings = Settings()
    assert settings.api_port == 12001
    assert settings.card_canary_on_startup is False
    assert settings.redis_prefix == "triton-eval:v2.1"


def test_equal_legacy_and_canonical_settings_compare_parsed_values(monkeypatch):
    monkeypatch.setenv("ASCEND_OP_EVAL_CPU_WORKERS", "01")
    monkeypatch.setenv("TRITON_EVAL_CPU_WORKERS", "1")
    monkeypatch.setenv("ASCEND_OP_EVAL_CARD_CANARY_ON_STARTUP", "false")
    monkeypatch.setenv("TRITON_EVAL_CARD_CANARY_ON_STARTUP", "0")
    settings = Settings()
    assert settings.cpu_workers == 1
    assert settings.card_canary_on_startup is False


def test_conflicting_settings_redact_values(monkeypatch):
    monkeypatch.setenv("ASCEND_OP_EVAL_REDIS_URL", "redis://secret-current@localhost/1")
    monkeypatch.setenv("TRITON_EVAL_REDIS_URL", "redis://secret-previous@localhost/1")
    with pytest.raises(ValueError) as error:
        Settings()
    message = str(error.value)
    assert "ASCEND_OP_EVAL_REDIS_URL" in message
    assert "TRITON_EVAL_REDIS_URL" in message
    assert "secret-current" not in message
    assert "secret-previous" not in message


def test_worker_environment_removes_stale_aliases():
    settings = Settings(reference_cache_dir=None)
    environment = command_environment(
        settings,
        {
            "ASCEND_OP_EVAL_REFERENCE_CACHE_DIR": "/stale-current",
            "TRITON_EVAL_REFERENCE_CACHE_DIR": "/stale-previous",
        },
    )
    assert "ASCEND_OP_EVAL_REFERENCE_CACHE_DIR" not in environment
    assert "TRITON_EVAL_REFERENCE_CACHE_DIR" not in environment
    assert environment["ASCEND_OP_EVAL_ENGINE_DIR"] == settings.engine_dir
    assert environment["TRITON_EVAL_ENGINE_DIR"] == settings.engine_dir


def test_legacy_imports_share_canonical_class_identity(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                [
                    "from triton_evaluation.config import Settings as Old",
                    "from ascend_op_eval.config import Settings as New",
                    "from triton_evaluation.service.models import AttemptLease as OldLease",
                    "from ascend_op_eval.control.models import AttemptLease as NewLease",
                    "from triton_evaluation.runtime.sandbox import EngineSandbox as OldSandbox",
                    "from ascend_op_eval.runtimes.sandbox import EngineSandbox as NewSandbox",
                    "assert Old is New and OldLease is NewLease and OldSandbox is NewSandbox",
                ]
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module", ["ascend_op_eval.api", "ascend_op_eval_client.cli"])
def test_installed_control_and_client_import_without_device_dependencies(tmp_path, module):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                f"import {module}, sys; "
                "assert not ({'torch', 'torch_npu', 'triton'} & sys.modules.keys())"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("legacy", [False, True])
def test_portable_operator_client_uses_canonical_setting_and_rejects_conflicts(tmp_path, legacy):
    plugin, skill, script = (
        ("triton-eval", "triton-eval", "triton_eval.py")
        if legacy
        else ("ascend-op-eval", "ascend-op-eval", "ascend_op_eval.py")
    )
    source = ROOT / "plugins" / plugin / "skills" / skill / "scripts" / script
    copied = tmp_path / script
    copied.write_bytes(source.read_bytes())
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "EVALUATION_URL",
            "EVALUATION_CAPABILITY_FILE",
            "ASCEND_OP_EVAL_CLIENT_URL",
            "ASCEND_OP_EVAL_CLIENT_CAPABILITY_FILE",
        }
    }
    env |= {"ASCEND_OP_EVAL_CLIENT_URL": "http://127.0.0.1:1", "EVALUATION_URL": "http://other:2"}
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(copied), "get", "ev_" + "1" * 32],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    response = json.loads(result.stdout)
    assert response["error"]["code"] == "CONFIG_CONFLICT"


def test_shell_alias_conflict_fails_before_running_commands(tmp_path):
    result = subprocess.run(
        [
            "bash",
            "-e",
            "-c",
            'source "$1"; echo UNEXPECTED',
            "test",
            str(ROOT / "deploy/environment.sh"),
        ],
        cwd=tmp_path,
        env=os.environ | {"ASCEND_OP_EVAL_API_PORT": "11907", "TRITON_EVAL_API_PORT": "12000"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "Conflicting settings" in result.stderr
    assert result.returncode != 0
    assert "UNEXPECTED" not in result.stdout
    assert "ASCEND_OP_EVAL_API_PORT" in result.stderr
