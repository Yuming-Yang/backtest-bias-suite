"""The command line, run in-process."""

from pathlib import Path

import pytest

from btbias.cli import load_adapter, main

EXAMPLE = Path(__file__).parents[1] / "examples" / "vectorized_adapter.py"


def test_run_passes_the_example_adapter_from_a_file_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["run", f"{EXAMPLE}:VectorizedAdapter"]) == 0
    out = capsys.readouterr().out
    assert "btbias: vectorized-example" in out
    assert "8 passed, 0 failed" in out


def test_run_fails_a_mutant_by_module_path_and_reports_why(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["run", "btbias.mutants:ZeroCostEngine", "--trap", "T5", "--trap", "T1"]) == 1
    out = capsys.readouterr().out
    assert "T1  PASS" in out and "T5  FAIL" in out
    assert "report the wrong cost" in out
    assert "1 passed, 1 failed" in out


def test_matrix_prints_both_tables_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["matrix"]) == 0
    out = capsys.readouterr().out
    assert "| reference | pass | pass |" in out
    assert "bug moves NAV by" in out
    assert "Diagonal: yes" in out


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("no_colon", "expected module:Name"),
        ("btbias.trap:NAV_RTOL", "is not an adapter"),
    ],
)
def test_bad_targets_exit_with_a_message(target: str, message: str) -> None:
    with pytest.raises(SystemExit, match=message):
        load_adapter(target)


def test_unknown_trap_ids_are_rejected() -> None:
    with pytest.raises(SystemExit, match="unknown trap"):
        main(["run", "btbias:ReferenceEngine", "--trap", "T9"])
