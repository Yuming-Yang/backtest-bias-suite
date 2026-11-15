"""The pattern from btbias.testing, used on the example adapter."""

import pytest

from btbias.mutants import FreeShortingEngine
from btbias.testing import ALL_TRAPS, assert_passes
from btbias.traps import T8

from vectorized_adapter import VectorizedAdapter


@pytest.mark.parametrize("trap", ALL_TRAPS, ids=lambda t: t.id)
def test_no_bias(trap) -> None:  # written exactly as a user would
    assert_passes(VectorizedAdapter(), trap)


def test_a_failing_trap_names_itself_and_the_finding() -> None:
    with pytest.raises(AssertionError, match=r"T8 \(Free and unlimited shorting\) fail: hard-to"):
        assert_passes(FreeShortingEngine(), T8)
