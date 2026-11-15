"""Test suite for daily-bar backtest engines.

The suite runs an engine on synthetic scenarios with known answers and
checks that it does not fall for common backtest biases. See SPEC.md.
"""

from btbias.protocol import Adapter, BacktestResult, ResultError, Strategy, View
from btbias.reference import ReferenceEngine
from btbias.scenario import CostModel, ExecutionConvention, Scenario, ScenarioError
from btbias.suite import SuiteReport, run_suite
from btbias.trap import Status, Trap, TrapResult

__version__ = "0.1.0"

__all__ = [
    "Adapter",
    "BacktestResult",
    "CostModel",
    "ExecutionConvention",
    "ReferenceEngine",
    "ResultError",
    "Scenario",
    "ScenarioError",
    "Status",
    "Strategy",
    "SuiteReport",
    "Trap",
    "TrapResult",
    "View",
    "run_suite",
]
