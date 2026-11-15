"""T8: shorts cost a borrow fee, and hard-to-borrow names cannot be shorted."""

from dataclasses import replace

from btbias import BorrowModel, ReferenceEngine, Scenario, Status
from btbias.trap import run_trap
from btbias.traps import T8


class FreeBorrow(ReferenceEngine):
    """Respects the hard-to-borrow list but charges no fee."""

    def borrow_model(self, scenario: Scenario) -> BorrowModel:
        return replace(scenario.borrow, daily_rate=0.0)


class UnlimitedBorrow(ReferenceEngine):
    """Charges the fee but shorts anything."""

    def borrow_model(self, scenario: Scenario) -> BorrowModel:
        return replace(scenario.borrow, hard_to_borrow=frozenset())


def test_reference_engine_passes_t8() -> None:
    result = run_trap(ReferenceEngine(), T8)
    assert result.status is Status.PASS, result.detail


def test_a_free_short_is_caught_on_nav_alone() -> None:
    result = run_trap(FreeBorrow(), T8)
    assert result.status is Status.FAIL
    assert "NAV on 2024-01-02" in result.detail and "held short" not in result.detail


def test_shorting_a_hard_to_borrow_name_is_caught_by_name() -> None:
    result = run_trap(UnlimitedBorrow(), T8)
    assert result.status is Status.FAIL
    assert "hard-to-borrow DDD held short, first at the 2024-01-02 close" in result.detail
