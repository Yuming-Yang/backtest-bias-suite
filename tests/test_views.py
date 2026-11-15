"""view_at agrees with the reference engine's views on every trap scenario."""

import pandas as pd
import pytest

from btbias import ReferenceEngine, Trap
from btbias.strategies import FundamentalTilt
from btbias.traps import ALL_TRAPS
from btbias.views import view_at


@pytest.mark.parametrize("trap", ALL_TRAPS, ids=[t.id for t in ALL_TRAPS])
def test_view_at_matches_the_reference_engine(trap: Trap) -> None:
    scenario, _ = trap.build()
    recorder = FundamentalTilt()  # any strategy that records views will do
    ReferenceEngine().run(scenario, recorder)
    for ref in recorder.seen:
        ours = view_at(scenario, ref.as_of)
        assert ours.universe == ref.universe
        pd.testing.assert_frame_equal(ours.close, ref.close)
        pd.testing.assert_frame_equal(ours.open, ref.open)
        pd.testing.assert_frame_equal(ours.fundamentals, ref.fundamentals)
