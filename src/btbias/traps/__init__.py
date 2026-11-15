"""The trap registry, in trap-id order."""

from btbias.traps.corporate_actions import T6
from btbias.traps.costs import T5
from btbias.traps.fill_timing import T2
from btbias.traps.lookahead import T1
from btbias.traps.membership import T7
from btbias.traps.point_in_time import T3
from btbias.traps.shorting import T8
from btbias.traps.survivorship import T4

ALL_TRAPS = (T1, T2, T3, T4, T5, T6, T7, T8)

__all__ = ["ALL_TRAPS", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
