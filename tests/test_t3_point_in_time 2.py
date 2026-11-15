"""T3: fundamentals visible only once published, as originally published."""

from dataclasses import replace

import pandas as pd

from btbias import ReferenceEngine, Scenario, Status, View
from btbias.strategies import best_reported
from btbias.trap import run_trap
from btbias.traps import T3
from btbias.traps.point_in_time import expected_schedule


class BackfilledRestatements(ReferenceEngine):
    """Respects publish dates but writes each final value over earlier rows.

    The common way restated data leaks: a database keeps only the latest
    value of each report, under the first publish date.
    """

    name = "backfilled-restatements"

    def view(self, scenario: Scenario, t: pd.Timestamp, weights: pd.Series) -> View:
        v = super().view(scenario, t, weights)
        if v.fundamentals.empty:
            return v
        key = ["asset", "field", "period_end"]
        final = scenario.fundamentals.sort_values("publish_date").groupby(key)["value"].last()
        fu = v.fundamentals.drop(columns="value").join(final, on=key)
        return replace(v, fundamentals=fu)


def test_reference_engine_passes_t3() -> None:
    result = run_trap(ReferenceEngine(), T3)
    assert result.status is Status.PASS, result.detail


def test_t3_scenario_has_restatements_and_a_strategy_that_reacts_to_them() -> None:
    scenario, _ = T3.build()
    fu = scenario.fundamentals
    assert fu.duplicated(subset=["asset", "period_end"]).sum() >= 10
    # Visible from period end, the strategy would pick differently on many days.
    pit = expected_schedule(scenario).idxmax(axis=1)
    leaked = pd.Series(
        [best_reported(fu[fu["period_end"] <= t]).idxmax() for t in scenario.calendar],
        index=scenario.calendar,
    )
    assert (pit != leaked).sum() >= 20


def test_restated_values_written_over_the_original_are_caught_by_the_probe() -> None:
    result = run_trap(BackfilledRestatements(), T3)
    assert result.status is Status.FAIL
    assert "never published as shown" in result.detail
    assert "before their publish date" not in result.detail
