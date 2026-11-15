"""The trap registry. Traps are added here as each milestone lands."""

from btbias.traps.costs import T5
from btbias.traps.lookahead import T1

ALL_TRAPS = (T1, T5)

__all__ = ["ALL_TRAPS", "T1", "T5"]
