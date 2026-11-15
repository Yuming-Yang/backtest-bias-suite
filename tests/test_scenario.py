import numpy as np
import pandas as pd
import pytest

from btbias.scenario import CostModel, ExecutionConvention, ScenarioError

from builders import CALENDAR, make_scenario

D = CALENDAR


def test_valid_scenario_builds_with_defaults() -> None:
    s = make_scenario()
    assert s.assets == ("AAA", "BBB")
    assert s.convention is ExecutionConvention.NEXT_OPEN
    assert s.cost_model.rate == 0.0
    assert s.corporate_actions.empty and s.fundamentals.empty and s.membership.empty


def test_full_scenario_with_all_metadata_builds() -> None:
    s = make_scenario(
        corporate_actions=pd.DataFrame(
            {
                "asset": ["AAA", "AAA"],
                "ex_date": [D[1], D[3]],
                "kind": ["split", "dividend"],
                "value": [2.0, 0.5],
            }
        ),
        fundamentals=pd.DataFrame(
            {
                "asset": ["AAA", "AAA"],
                "field": ["eps", "eps"],
                "period_end": [D[0], D[0]],
                "publish_date": [D[1], D[3]],  # second row is a restatement
                "value": [1.0, 0.8],
            }
        ),
        membership=pd.DataFrame(
            {
                "asset": ["AAA", "BBB", "AAA"],
                "start": [D[0], D[0], D[3]],
                "end": [D[2], D[2], pd.NaT],
            }
        ),
        cost_model=CostModel(rate=0.001),
        convention=ExecutionConvention.NEXT_CLOSE,
    )
    assert len(s.fundamentals) == 2


@pytest.mark.parametrize("rate", [-0.001, float("nan"), float("inf")])
def test_cost_model_rejects_bad_rates(rate: float) -> None:
    with pytest.raises(ScenarioError, match="cost rate"):
        CostModel(rate=rate)


def _close_with(**cols: list[float]) -> pd.DataFrame:
    base = make_scenario().close.copy()
    for k, v in cols.items():
        base[k] = v
    return base


def _action(**overrides: list[object]) -> pd.DataFrame:
    row = {"asset": ["AAA"], "ex_date": [D[1]], "kind": ["split"], "value": [2.0]}
    return pd.DataFrame(row | overrides)


def _fundamental(**overrides: list[object]) -> pd.DataFrame:
    row = {
        "asset": ["AAA"],
        "field": ["eps"],
        "period_end": [D[0]],
        "publish_date": [D[1]],
        "value": [1.0],
    }
    return pd.DataFrame(row | overrides)


BAD_CASES = {
    "unsorted calendar": (
        lambda: {"calendar": CALENDAR[::-1]},
        "sorted and unique",
    ),
    "intraday calendar": (
        lambda: {"calendar": CALENDAR + pd.Timedelta(hours=16)},
        "midnight",
    ),
    "non-positive price": (
        lambda: {"close": _close_with(AAA=[10.0, 0.0, 12.0, 11.0, 13.0])},
        "positive",
    ),
    "price index mismatch": (
        lambda: {"close": make_scenario().close.iloc[:-1]},
        "indexed by the calendar",
    ),
    "open and close gaps differ": (
        lambda: {"close": _close_with(AAA=[10.0, np.nan, 12.0, 11.0, 13.0])},
        "same days",
    ),
    "price after delisting": (
        lambda: {
            "close": _close_with(BBB=[20.0, 19.0, 18.0, 17.0, np.nan]),
            "open": _close_with(BBB=[20.0, 19.0, 18.0, 17.0, np.nan]) * 0.99,
        },
        "after its delist_date",
    ),
    "listing missing an asset": (
        lambda: {"listings": make_scenario().listings.loc[["AAA"]]},
        "one row per price column",
    ),
    "delisting return below -100%": (
        lambda: {"listings": make_scenario().listings.assign(delisting_return=[0.0, -1.5])},
        "delisting_return",
    ),
    "unknown corporate action": (
        lambda: {
            "corporate_actions": pd.DataFrame(
                {"asset": ["AAA"], "ex_date": [D[1]], "kind": ["spinoff"], "value": [1.0]}
            )
        },
        "unknown corporate action kinds",
    ),
    "corporate action off calendar": (
        lambda: {
            "corporate_actions": pd.DataFrame(
                {
                    "asset": ["AAA"],
                    "ex_date": [pd.Timestamp("2024-01-06")],
                    "kind": ["split"],
                    "value": [2.0],
                }
            )
        },
        "trading day",
    ),
    "published before period end": (
        lambda: {
            "fundamentals": pd.DataFrame(
                {
                    "asset": ["AAA"],
                    "field": ["eps"],
                    "period_end": [D[2]],
                    "publish_date": [D[1]],
                    "value": [1.0],
                }
            )
        },
        "published before its period ends",
    ),
    "fundamental for unknown asset": (
        lambda: {
            "fundamentals": pd.DataFrame(
                {
                    "asset": ["ZZZ"],
                    "field": ["eps"],
                    "period_end": [D[0]],
                    "publish_date": [D[1]],
                    "value": [1.0],
                }
            )
        },
        "unknown assets",
    ),
    "overlapping membership": (
        lambda: {
            "membership": pd.DataFrame(
                {"asset": ["AAA", "AAA"], "start": [D[0], D[1]], "end": [pd.NaT, D[3]]}
            )
        },
        "overlapping",
    ),
    "membership end before start": (
        lambda: {"membership": pd.DataFrame({"asset": ["AAA"], "start": [D[2]], "end": [D[1]]})},
        "after start",
    ),
    "non-positive initial cash": (lambda: {"initial_cash": 0.0}, "initial_cash"),
    "timezone-aware calendar": (
        lambda: {
            "calendar": CALENDAR.tz_localize("UTC"),
            "open": make_scenario().open.tz_localize("UTC"),
            "close": make_scenario().close.tz_localize("UTC"),
        },
        "timezone-naive",
    ),
    "delisting return without a delisting": (
        lambda: {"listings": make_scenario().listings.assign(delisting_return=[-0.5, -0.3])},
        "never delists",
    ),
    "delist date off calendar": (
        lambda: {
            "listings": make_scenario().listings.assign(
                delist_date=[pd.NaT, pd.Timestamp("2024-01-06")]
            )
        },
        "must trade on its delist_date",
    ),
    "no trade on the delist date": (
        lambda: {"listings": make_scenario().listings.assign(delist_date=[pd.NaT, D[4]])},
        "must trade on its delist_date",
    ),
    "corporate action value not finite": (
        lambda: {"corporate_actions": _action(value=[np.nan])},
        "finite",
    ),
    "duplicate corporate action": (
        lambda: {"corporate_actions": pd.concat([_action(), _action()])},
        "share asset, ex_date and kind",
    ),
    "corporate action after delisting": (
        lambda: {"corporate_actions": _action(asset=["BBB"], ex_date=[D[4]])},
        "does not trade",
    ),
    "fundamental without publish date": (
        lambda: {"fundamentals": _fundamental(publish_date=[pd.NaT])},
        "needs a period_end and a publish_date",
    ),
    "fundamental value not finite": (
        lambda: {"fundamentals": _fundamental(value=[np.nan])},
        "finite",
    ),
    "member after delisting": (
        lambda: {"membership": pd.DataFrame({"asset": ["BBB"], "start": [D[0]], "end": [pd.NaT]})},
        "not listed",
    ),
}


@pytest.mark.parametrize("case", list(BAD_CASES), ids=list(BAD_CASES))
def test_invalid_scenarios_are_rejected(case: str) -> None:
    overrides, message = BAD_CASES[case]
    with pytest.raises(ScenarioError, match=message):
        make_scenario(**overrides())
