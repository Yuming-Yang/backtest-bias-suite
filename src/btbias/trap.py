"""What a trap is, and how one is run against an adapter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd

from btbias.protocol import Adapter, BacktestResult, Strategy
from btbias.scenario import Scenario

NAV_RTOL = 1e-9
"""Relative tolerance for outcome checks (SPEC.md, reference semantics rule 3)."""


class Status(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    """The engine raised, or returned a result of the wrong shape."""


@dataclass(frozen=True)
class Trap:
    """One bias the suite checks for.

    Attributes:
        id: Short label such as ``"T5"``.
        title: What a buggy engine gets wrong, in a few words.
        build: Returns a fresh scenario and strategy. Called once per run,
            because probe strategies keep state.
        check: Given the scenario, the strategy after the run and the result,
            returns a list of problems. An empty list means the engine passed.
    """

    id: str
    title: str
    build: Callable[[], tuple[Scenario, Strategy]]
    check: Callable[[Scenario, Strategy, BacktestResult], list[str]]


@dataclass(frozen=True)
class TrapResult:
    trap_id: str
    title: str
    status: Status
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status is Status.PASS


def run_trap(adapter: Adapter, trap: Trap) -> TrapResult:
    """Run one trap. Never raises: engine errors become ``Status.ERROR``."""
    scenario, strategy = trap.build()
    try:
        result = adapter.run(scenario, strategy)
        result.check_against(scenario)
    except Exception as exc:  # the engine under test can fail in any way
        return TrapResult(trap.id, trap.title, Status.ERROR, f"{type(exc).__name__}: {exc}")
    problems = trap.check(scenario, strategy, result)
    if problems:
        return TrapResult(trap.id, trap.title, Status.FAIL, "; ".join(problems))
    return TrapResult(trap.id, trap.title, Status.PASS)


def nav_mismatch(actual: pd.Series, expected: pd.Series, rtol: float = NAV_RTOL) -> str | None:
    """Describe the first day where ``actual`` NAV is off, or ``None`` if none is."""
    a = actual.to_numpy(dtype=float)
    e = expected.to_numpy(dtype=float)
    bad = ~np.isclose(a, e, rtol=rtol, atol=0.0)
    if not bad.any():
        return None
    i = int(np.argmax(bad))
    day = expected.index[i]
    return (
        f"NAV on {day.date()} is {a[i]:,.6f}, expected {e[i]:,.6f} "
        f"(relative error {a[i] / e[i] - 1:+.2e})"
    )
