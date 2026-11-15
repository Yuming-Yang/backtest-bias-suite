"""T7: the universe on each day is that day's index, not today's."""

from btbias import ReferenceEngine, Status
from btbias.mutants import TodaysConstituentsEngine
from btbias.trap import run_trap
from btbias.traps import T7
from btbias.traps.membership import members_at


def test_reference_engine_passes_t7() -> None:
    result = run_trap(ReferenceEngine(), T7)
    assert result.status is Status.PASS, result.detail


def test_t7_index_changes_twice_and_joiners_rise_before_joining() -> None:
    scenario, _ = T7.build()
    cal = scenario.calendar
    assert members_at(scenario, cal[0]) == ("AAA", "BBB", "CCC", "DDD")
    assert members_at(scenario, cal[21]) == ("AAA", "CCC", "DDD", "EEE")
    assert members_at(scenario, cal[-1]) == ("AAA", "DDD", "EEE", "FFF")
    close = scenario.close
    assert close["EEE"].iloc[21] > close["EEE"].iloc[0]
    assert close["BBB"].iloc[21] < close["BBB"].iloc[0]


def test_todays_constituents_are_caught_on_the_first_day_and_inflate_nav() -> None:
    result = run_trap(TodaysConstituentsEngine(), T7)
    assert result.status is Status.FAIL
    assert "first EEE, FFF on 2024-01-01" in result.detail
    scenario, strategy = T7.build()
    honest = ReferenceEngine().run(scenario, strategy).nav.iloc[-1]
    scenario, strategy = T7.build()
    biased = TodaysConstituentsEngine().run(scenario, strategy).nav.iloc[-1]
    assert biased > 1.2 * honest
