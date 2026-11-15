"""Ground-truth helpers, checked against numbers worked out by hand."""

import ast
from pathlib import Path

import numpy as np
import pandas as pd

import btbias
from btbias.generator import trading_days
from btbias.truth import flat_market_nav


def test_flat_market_nav_matches_a_hand_calculation() -> None:
    cal = trading_days(4)
    schedule = pd.DataFrame({"A": [0.5, 0.0, 0.0, 0.9], "B": [0.0, 0.5, 0.5, 0.0]}, index=cal)
    nav = flat_market_nav(schedule, initial_cash=100.0, cost_rate=0.01)
    # Day 1: buy A worth 50, cost 0.5. Day 2: sell A (50), buy B worth
    # 0.5 * 99.5, cost 1% of both legs. Day 3: B is topped up from 49.75 to
    # half of the new NAV. The day-3 decision never fills.
    nav2 = 99.5 - 0.01 * (50 + 49.75)
    nav3 = nav2 - 0.01 * abs(0.5 * nav2 - 49.75)
    np.testing.assert_allclose(nav, [100.0, 99.5, nav2, nav3], rtol=1e-15)


def test_flat_market_nav_without_costs_stays_at_initial_cash() -> None:
    cal = trading_days(5)
    schedule = pd.DataFrame({"A": [0.3, 0.9, 0.1, 0.5, 0.2]}, index=cal)
    assert (flat_market_nav(schedule, 1_000.0, 0.0) == 1_000.0).all()


def _btbias_imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return {n for n in names if n.startswith("btbias")}


def test_ground_truth_and_traps_do_not_import_the_reference_engine() -> None:
    package = Path(btbias.__file__).parent
    graded = [package / "truth.py", *sorted((package / "traps").glob("*.py"))]
    for path in graded:
        forbidden = _btbias_imports(path) & {"btbias.reference", "btbias.mutants", "btbias"}
        assert not forbidden, f"{path.name} imports {sorted(forbidden)}"
