"""T4: delisted assets must stay in history and pay their delisting return."""

from btbias import ReferenceEngine, Scenario, Status
from btbias.trap import run_trap
from btbias.traps import T4
from btbias.traps.survivorship import FAILURE, TAKEOVER


class IgnoresDelistingReturn(ReferenceEngine):
    """Keeps delisted assets but liquidates them at the last close."""

    def delisting_proceeds(
        self, scenario: Scenario, asset: str, shares: float, last_close: float
    ) -> float:
        return shares * last_close


def test_reference_engine_passes_t4() -> None:
    result = run_trap(ReferenceEngine(), T4)
    assert result.status is Status.PASS, result.detail


def test_t4_scenario_has_a_takeover_and_a_failure() -> None:
    scenario, _ = T4.build()
    for asset, day, dlret in (TAKEOVER, FAILURE):
        assert scenario.listings.loc[asset, "delist_date"] == scenario.calendar[day]
        assert scenario.listings.loc[asset, "delisting_return"] == dlret
        assert scenario.close[asset].iloc[day + 1 :].isna().all()
    # The failing company falls before it is delisted.
    eee = scenario.close["EEE"]
    assert eee.iloc[FAILURE[1]] < 0.8 * eee.iloc[0]


def test_dropping_the_delisting_return_is_caught() -> None:
    result = run_trap(IgnoresDelistingReturn(), T4)
    assert result.status is Status.FAIL
    assert f"NAV on {T4.build()[0].calendar[TAKEOVER[1]]:%Y-%m-%d}" in result.detail
