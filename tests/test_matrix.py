"""The matrix report: the diagonal holds, and effects come out with the right sign."""

import pandas as pd

from btbias.matrix import bug_effects, is_diagonal, mutation_matrix, to_markdown
from btbias.traps import T5, T6


def test_the_full_matrix_is_diagonal() -> None:
    matrix = mutation_matrix()
    assert list(matrix.index)[0] == "reference"
    assert is_diagonal(matrix), matrix


def test_is_diagonal_spots_a_mutant_that_trips_another_trap() -> None:
    matrix = pd.DataFrame(
        {"T1": ["pass", "fail", "pass"], "T2": ["pass", "fail", "fail"]},
        index=["reference", "T1", "T2"],
    )
    assert not is_diagonal(matrix)


def test_bug_effects_have_the_expected_direction() -> None:
    effects = bug_effects(traps=[T5, T6])
    # Free trading flatters NAV; an ignored split looks like a crash.
    assert effects.loc["T5", "bug moves NAV by"] > 0
    assert effects.loc["T6", "bug moves NAV by"] < -0.3
    assert effects.loc["T6", "correct"] == 0.0


def test_to_markdown_renders_a_table() -> None:
    frame = pd.DataFrame({"T1": ["fail"], "x": [0.123]}, index=["T1"])
    assert to_markdown(frame, percent=["x"]) == (
        "|  | T1 | x |\n| --- | --- | --- |\n| T1 | **fail** | +12.3% |"
    )
