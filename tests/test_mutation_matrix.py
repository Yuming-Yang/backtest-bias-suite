"""The mutation matrix: every mutant fails its own trap and only its own trap."""

import pytest

from btbias import ReferenceEngine, Status, Trap
from btbias.mutants import MUTANTS
from btbias.trap import run_trap
from btbias.traps import ALL_TRAPS

TRAP_IDS = [t.id for t in ALL_TRAPS]


def test_every_trap_has_exactly_one_mutant() -> None:
    assert sorted(MUTANTS) == sorted(TRAP_IDS)


@pytest.mark.parametrize("trap", ALL_TRAPS, ids=TRAP_IDS)
def test_reference_engine_passes(trap: Trap) -> None:
    result = run_trap(ReferenceEngine(), trap)
    assert result.status is Status.PASS, result.detail


@pytest.mark.parametrize("trap", ALL_TRAPS, ids=TRAP_IDS)
@pytest.mark.parametrize("bug", sorted(MUTANTS))
def test_mutant_fails_only_its_own_trap(bug: str, trap: Trap) -> None:
    result = run_trap(MUTANTS[bug](), trap)
    if bug == trap.id:
        # FAIL, not ERROR: the trap must catch the bug, not crash on it.
        assert result.status is Status.FAIL, f"{bug} mutant was not caught: {result.detail}"
    else:
        assert result.status is Status.PASS, f"{bug} mutant tripped {trap.id}: {result.detail}"
