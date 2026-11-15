"""The trap registry. Traps are added here as each milestone lands."""

from btbias.traps.costs import T5

ALL_TRAPS = (T5,)

__all__ = ["ALL_TRAPS", "T5"]
