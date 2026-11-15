"""The whole adapter that plugs vectorized_engine into btbias."""

import pandas as pd

from btbias import BacktestResult, ExecutionConvention, Scenario, Strategy
from btbias.adapters import fills_from_money, view_at

from vectorized_engine import backtest


class VectorizedAdapter:
    name = "vectorized-example"

    def run(self, scenario: Scenario, strategy: Strategy) -> BacktestResult:
        if scenario.convention is not ExecutionConvention.NEXT_OPEN:
            raise NotImplementedError("the example engine only fills at the next open")
        # The engine wants every decision up front, so collect them day by day first.
        decisions = {t: strategy.target_weights(view_at(scenario, t)) for t in scenario.calendar}
        ca = scenario.corporate_actions.assign(ex_date=lambda d: pd.to_datetime(d["ex_date"]))
        actions = ca.pivot_table(index="ex_date", columns=["kind", "asset"], values="value")
        rate, borrow = scenario.cost_model.rate, scenario.borrow
        nav, traded, held = backtest(
            pd.DataFrame(decisions).T,
            scenario.open,
            scenario.close,
            rate,
            scenario.initial_cash,
            splits=actions.get("split"),
            dividends=actions.get("dividend"),
            delisting_returns=scenario.listings["delisting_return"],
            borrow_rate=borrow.daily_rate,
            no_short=borrow.hard_to_borrow,
        )
        trades = fills_from_money(traded, scenario.open, rate)
        return BacktestResult(nav=nav, trades=trades, weights=held)
