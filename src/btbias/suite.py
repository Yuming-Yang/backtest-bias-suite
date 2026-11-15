"""Run every trap against one adapter."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from btbias.protocol import Adapter
from btbias.trap import Trap, TrapResult, run_trap
from btbias.traps import ALL_TRAPS


@dataclass(frozen=True)
class SuiteReport:
    adapter: str
    results: tuple[TrapResult, ...]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failed_ids(self) -> tuple[str, ...]:
        return tuple(r.trap_id for r in self.results if not r.passed)


def run_suite(adapter: Adapter, traps: Sequence[Trap] = ALL_TRAPS) -> SuiteReport:
    return SuiteReport(adapter.name, tuple(run_trap(adapter, trap) for trap in traps))
