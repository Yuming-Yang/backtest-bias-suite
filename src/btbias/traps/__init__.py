"""The trap registry. Traps are added here as each milestone lands."""

from btbias.traps.costs import T5
from btbias.traps.fill_timing import T2
from btbias.traps.lookahead import T1
from btbias.traps.point_in_time import T3
from btbias.traps.survivorship import T4

ALL_TRAPS = (T1, T2, T3, T4, T5)

__all__ = ["ALL_TRAPS", "T1", "T2", "T3", "T4", "T5"]
