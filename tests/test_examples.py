"""The example vectorized adapter: short, and it agrees with the reference engine."""

import inspect

import numpy as np
import pandas as pd
import pytest

from btbias import Adapter, CostModel, ExecutionConvention, ReferenceEngine, run_suite
from btbias.generator import random_walk, random_weights, simple_market, trading_days
from btbias.strategies import ScheduledWeights

import vectorized_adapter
from vectorized_adapter import VectorizedAdapter

MAX_ADAPTER_LINES = 30


def test_adapter_fits_in_30_lines() -> None:
    lines = inspect.getsource(vectorized_adapter).splitlines()
    code = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    assert len(code) <= MAX_ADAPTER_LINES, f"adapter is {len(code)} lines"


def test_adapter_satisfies_the_protocol_and_passes_the_suite() -> None:
    adapter = VectorizedAdapter()
    assert isinstance(adapter, Adapter)
    report = run_suite(adapter)
    assert report.passed, [r.detail for r in report.results]


def test_adapter_matches_the_reference_engine_on_a_moving_market() -> None:
    # Two engines written independently (shares and an event loop versus
    # money and a weight matrix) must agree on a market with overnight gaps,
    # daily rebalancing and costs.
    cal = trading_days(60)
    assets = ["X", "Y", "Z"]
    open_, close = random_walk(cal, assets, seed=11, gaps=True)
    scenario = simple_market("walk", open_, close, cost_model=CostModel(rate=0.002))
    strategy = ScheduledWeights(random_weights(cal, assets, seed=12))

    ours = VectorizedAdapter().run(scenario, strategy)
    ref = ReferenceEngine().run(scenario, strategy)

    ours.check_against(scenario)
    np.testing.assert_allclose(ours.nav, ref.nav, rtol=1e-9)
    np.testing.assert_allclose(ours.weights, ref.weights, rtol=1e-9, atol=1e-12)
    cols = ["quantity", "price", "cost"]
    np.testing.assert_allclose(ours.trades[cols], ref.trades[cols], rtol=1e-9)
    assert ours.trades["asset"].tolist() == ref.trades["asset"].tolist()


def test_adapter_handles_a_strategy_that_stays_in_cash() -> None:
    cal = trading_days(5)
    open_, close = random_walk(cal, ["X"], seed=0)
    scenario = simple_market("cash", open_, close)
    schedule = pd.DataFrame(index=cal, columns=["X"], dtype=float)
    result = VectorizedAdapter().run(scenario, ScheduledWeights(schedule))
    assert result.trades.empty
    assert (result.nav == scenario.initial_cash).all()


def test_adapter_refuses_conventions_the_engine_does_not_support() -> None:
    cal = trading_days(5)
    open_, close = random_walk(cal, ["X"], seed=0)
    scenario = simple_market("x", open_, close, convention=ExecutionConvention.NEXT_CLOSE)
    with pytest.raises(NotImplementedError, match="next open"):
        VectorizedAdapter().run(scenario, ScheduledWeights(pd.DataFrame(index=cal)))
