"""Deliberately broken engines, one bug each.

Every mutant is the reference engine with exactly one method overridden.
The mutation matrix (tests/test_mutation_matrix.py) checks that each one
fails its own trap and passes every other trap: the first shows the trap
catches the bug, the second shows it does not fire on unrelated ones.
"""

from __future__ import annotations

from btbias.reference import ReferenceEngine
from btbias.scenario import Scenario


class ZeroCostEngine(ReferenceEngine):
    """T5: ignores the scenario's cost model and trades for free."""

    name = "mutant-T5-zero-cost"

    def transaction_cost(self, scenario: Scenario, notional: float) -> float:
        return 0.0


MUTANTS: dict[str, type[ReferenceEngine]] = {
    "T5": ZeroCostEngine,
}
"""Trap id -> the mutant that trap must catch."""
