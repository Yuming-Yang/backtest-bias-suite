"""The whole adapter that plugs vectorized_engine into btbias."""

import numpy as np
import pandas as pd

from btbias import BacktestResult, ExecutionConvention, Scenario, Strategy, View

from vectorized_engine import backtest


class VectorizedAdapter:
    name = "vectorized-example"

    def run(self, scenario: Scenario, strategy: Strategy) -> BacktestResult:
        if scenario.convention is not ExecutionConvention.NEXT_OPEN:
            raise NotImplementedError("the example engine only fills at the next open")
        # The engine wants every decision up front, so collect them day by day first.
        decisions = {}
        for t in scenario.calendar:
            universe = tuple(scenario.close.loc[t].dropna().index)
            view = View(t, scenario.open.loc[:t], scenario.close.loc[:t], universe)
            decisions[t] = strategy.target_weights(view)
        rate, cash = scenario.cost_model.rate, scenario.initial_cash
        weights = pd.DataFrame(decisions).T
        nav, traded, held = backtest(weights, scenario.open, scenario.close, rate, cash)
        # The engine reports money traded; the suite wants one row per fill.
        day, asset = np.nonzero(traded.to_numpy())
        money, price = traded.to_numpy()[day, asset], scenario.open.to_numpy()[day, asset]
        trades = pd.DataFrame(
            {"date": scenario.calendar[day], "asset": traded.columns[asset],
             "quantity": money / price, "price": price, "cost": rate * np.abs(money)}
        )  # fmt: skip
        return BacktestResult(nav=nav, trades=trades, weights=held)
