"""Native candidate methods through their data/measurement interfaces."""

import pytest
import torch

from triton_evaluation.engine import native_support


def test_native_outputs_reject_scalar_instead_of_tensor():
    with pytest.raises(AssertionError, match="Tensor"):
        native_support.compare_outputs(torch.tensor([2.0]), 2.0)


def test_native_outputs_preserve_tree_and_dtype_contract():
    expected = {"values": [torch.tensor([1.0], dtype=torch.float32)]}
    native_support.compare_outputs(expected, {"values": [torch.tensor([1.0])]})
    with pytest.raises(AssertionError, match="dtype"):
        native_support.compare_outputs(
            expected, {"values": [torch.tensor([1.0]).half()]}
        )
    with pytest.raises(AssertionError, match="structure"):
        native_support.compare_outputs(expected, [torch.tensor([1.0])])


def test_native_float64_zero_tolerance_does_not_lose_difference():
    with pytest.raises(AssertionError, match="tolerance"):
        native_support.compare_outputs(
            torch.tensor([1e8], dtype=torch.float64),
            torch.tensor([1e8 + 1], dtype=torch.float64),
            tolerance={
                "max_atol": 0.0,
                "max_rtol": 0.0,
                "required_matched_ratio": 1.0,
                "max_error_cap": 0.0,
            },
        )


def test_native_integer_outputs_are_exact_without_overflow():
    with pytest.raises(AssertionError, match="integer"):
        native_support.compare_outputs(torch.tensor([0]), torch.tensor([-(2**63)]))


def test_native_tolerance_ratio_cap_and_nonfinite_are_explicit():
    ref = torch.tensor([1.0, 1.0])
    out = torch.tensor([1.0, 1.25])
    native_support.compare_outputs(
        ref,
        out,
        tolerance={
            "max_atol": 0.0,
            "max_rtol": 0.0,
            "required_matched_ratio": 0.5,
            "max_error_cap": 0.3,
        },
    )
    with pytest.raises(AssertionError, match="tolerance"):
        native_support.compare_outputs(
            ref,
            out,
            tolerance={
                "max_atol": 0.0,
                "max_rtol": 0.0,
                "required_matched_ratio": 0.5,
                "max_error_cap": 0.2,
            },
        )
    neg = torch.tensor([-float("inf"), 1.0])
    with pytest.raises(AssertionError, match="non-finite"):
        native_support.compare_outputs(neg, neg)
    native_support.compare_outputs(neg, neg, tolerance={"allow_negative_inf": True})


def test_native_inputs_copy_nested_views_preserving_alias_without_polluting_source():
    source = torch.arange(8, dtype=torch.float32)
    inputs = [{"base": source, "view": source[1:7:2]}, source]
    candidate = native_support.copy_inputs(inputs, "cpu")
    reference = native_support.copy_inputs(inputs, "cpu")
    assert candidate[0]["base"] is candidate[1]
    assert candidate[0]["view"].stride() == (2,)
    candidate[0]["view"].fill_(99)
    assert candidate[0]["base"].tolist() == [0, 99, 2, 99, 4, 99, 6, 7]
    assert reference[0]["base"].tolist() == list(range(8))
    assert source.tolist() == list(range(8))


def test_native_profile_counts_every_launch_in_one_invocation(tmp_path):
    csv = tmp_path / "kernel_details.csv"
    csv.write_text("Name,Duration(us)\nreduce,10\nreduce,20\ncombine,5\n")
    assert native_support.parse_call_profile(tmp_path) == {
        "reduce": 30.0,
        "combine": 5.0,
    }


@pytest.mark.parametrize("rows", ["reduce,nan", "reduce,-1", "reduce,0", ",1"])
def test_native_profile_rejects_invalid_duration_or_identity(tmp_path, rows):
    (tmp_path / "kernel_details.csv").write_text("Name,Duration(us)\n" + rows + "\n")
    with pytest.raises(ValueError):
        native_support.parse_call_profile(tmp_path)


def test_native_profile_rejects_ambiguous_exports(tmp_path):
    for name in ["one", "two"]:
        path = tmp_path / name
        path.mkdir()
        (path / "kernel_details.csv").write_text("Name,Duration(us)\na,1\n")
    with pytest.raises(ValueError, match="exactly one"):
        native_support.parse_call_profile(tmp_path)


def test_native_verify_route_cannot_accept_mutated_nested_reference_inputs():
    from triton_evaluation.engine import verify

    class Reference(torch.nn.Module):
        def forward(self, values):
            return values[0] * 2

    class Candidate(torch.nn.Module):
        _native_candidate = True

        def forward(self, values):
            values[0].zero_()
            return values[0]

    source = torch.tensor([3.0])
    with pytest.raises(AssertionError, match="tolerance"):
        verify.run_single_case(
            verify.ModelPair(Reference(), Candidate()),
            [[source]],
            "cpu",
            verify.CaseContext(1, 1),
        )
    assert source.item() == 3.0


def test_native_verify_route_rejects_non_tensor_output():
    from triton_evaluation.engine import verify

    class Reference(torch.nn.Module):
        def forward(self, x):
            return x + 1

    class Candidate(torch.nn.Module):
        _native_candidate = True

        def forward(self, x):
            return 0

    with pytest.raises(AssertionError, match="Tensor"):
        verify.run_single_case(
            verify.ModelPair(Reference(), Candidate()),
            [torch.ones(2)],
            "cpu",
            verify.CaseContext(1, 1),
        )


def test_native_measurement_is_mean_of_full_invocations(tmp_path, monkeypatch):
    from types import SimpleNamespace

    calls = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        torch, "npu", SimpleNamespace(synchronize=lambda: None), raising=False
    )
    data = iter([(10, 20), (20, 40), (30, 60)])

    def capture(fn, directory):
        fn()
        first, second = next(data)
        (directory / "kernel_details.csv").write_text(
            f"Name,Duration(us)\nreduce,{first}\nreduce,{second}\n"
        )

    monkeypatch.setattr(native_support, "_capture_call", capture)
    samples = []
    operators, latency = native_support.measure_profile(
        lambda: calls.append("call"),
        2,
        3,
        "native",
        keep_res=True,
        samples_ms=samples,
    )
    assert calls == ["call"] * 5
    assert operators == {"reduce": 60.0}
    assert latency == 0.06
    assert samples == [0.03, 0.06, 0.09]
    assert len(list(tmp_path.rglob("kernel_details.csv"))) == 3


def test_native_profile_uses_explicit_kernel_names_without_triton(tmp_path):
    import sys

    from triton_evaluation.engine import profile_runner

    config = profile_runner.ProfileConfig(
        op_name="native",
        verify_dir=str(tmp_path),
        triton_impl_name="native_impl",
        profile_mode="op",
        case_idx=None,
        launch_count=1,
        timeout=30,
        output=str(tmp_path / "out.json"),
        engine_dir=str(tmp_path),
        python_bin=sys.executable,
        implementation="native",
        candidate_kind="native",
        kernel_names=["add_custom"],
    )
    seen = []

    def backend(**kwargs):
        seen.append(kwargs["kernel_names"])
        return {
            "status": "complete",
            "target_kernel": "add_custom",
            "kernels": [],
            "raw_metrics": {},
            "bound": None,
            "per_core": None,
            "recommendations": [],
            "missing_metrics": [],
            "warnings": [],
            "error": None,
        }

    result, code = profile_runner.run_profile(
        config,
        discover=lambda **kwargs: [{"case_idx": 0, "input_desc": []}],
        op_backend=backend,
    )
    assert code == 0
    assert seen == [["add_custom"]]
    assert result["per_case_results"][0]["status"] == "complete"


def test_native_mismatch_is_published_as_wrong_not_infrastructure_failure(monkeypatch):
    from types import SimpleNamespace

    from triton_evaluation.engine import verify
    from triton_evaluation.evaluators.shaping import shape_correctness

    monkeypatch.setattr(
        torch, "npu", SimpleNamespace(manual_seed=lambda seed: None), raising=False
    )

    class Reference(torch.nn.Module):
        def forward(self, x):
            return x + 1

    class Candidate(torch.nn.Module):
        _native_candidate = True

        def forward(self, x):
            return torch.zeros_like(x)

    success, failure = verify._try_run_case(
        {
            "framework_cls": Reference,
            "impl_cls": Candidate,
            "get_init_inputs": lambda: [],
        },
        verify.CaseContext(1, 1),
        [torch.ones(2)],
        "cpu",
    )
    assert success is False
    assert failure["kind"] == "value_mismatch"
    result = shape_correctness(
        {
            "op_name": "native",
            "comparison_method": "native_tensor_v1",
            "total_cases": 1,
            "passed_cases": 0,
            "failed_cases": 1,
            "failures": [failure],
        },
        decoy=False,
    )
    assert result.outcome == "wrong"
    assert result.passed is False


def test_native_contract_checks_remain_enabled_under_python_optimization():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "import torch; "
            "from triton_evaluation.engine.native_support import compare_outputs; "
            "compare_outputs(torch.ones(1), 1)",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "candidate output must be a Tensor" in result.stderr
