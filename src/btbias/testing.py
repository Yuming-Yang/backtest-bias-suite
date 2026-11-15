"""pytest integration: one test per trap, from a six-line test file.

    import pytest
    from btbias.testing import ALL_TRAPS, assert_passes
    from my_engine import MyAdapter

    @pytest.mark.parametrize("trap", ALL_TRAPS, ids=lambda t: t.id)
    def test_no_bias(trap):
        assert_passes(MyAdapter(), trap)

pytest is not a dependency of btbias; this module only raises
``AssertionError``, which any test runner reports.
"""

from __future__ import annotations

from btbias.protocol import Adapter
from btbias.trap import Trap, run_trap
from btbias.traps import ALL_TRAPS

__all__ = ["ALL_TRAPS", "assert_passes"]


def assert_passes(adapter: Adapter, trap: Trap) -> None:
    """Raise ``AssertionError`` with the trap's findings unless the adapter passes."""
    result = run_trap(adapter, trap)
    if not result.passed:
        raise AssertionError(f"{trap.id} ({trap.title}) {result.status.value}: {result.detail}")
