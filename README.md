# backtest-bias-suite

A test suite for backtest engines: it runs your engine on small synthetic markets with known answers and fails if the engine lets lookahead, survivorship, missing costs, unadjusted splits or free shorting into the results.

Most backtest bugs do not raise errors. They make the equity curve look better. One day of price lookahead turned a losing momentum strategy (−12.6%) into a +211% one in this suite's own test market. `btbias` checks the engine itself, whatever strategy runs on it, against answers worked out independently.

## Quick start

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Yuming-Yang/backtest-bias-suite
cd backtest-bias-suite
uv sync
uv run btbias run btbias:ReferenceEngine
uv run btbias run examples/vectorized_adapter.py:VectorizedAdapter
uv run btbias matrix
```

The first command runs the eight traps against the reference engine, the second against an independently written vectorized engine, and the third reproduces every number in the Results section. Each takes a few seconds.

## Testing your engine

Write an adapter: a class with a `name` and a `run(scenario, strategy)` method. `run` drives your engine through the scenario, calls `strategy.target_weights(view)` at each day's close, and returns a `BacktestResult` (daily NAV, fills, daily weights). [`examples/vectorized_adapter.py`](examples/vectorized_adapter.py) does this for a vectorized engine in 28 lines.

Then run it from the command line (exit status 1 if any trap fails):

```bash
uv run btbias run path/to/my_adapter.py:MyAdapter
```

or as one pytest test per trap:

```python
import pytest
from btbias.testing import ALL_TRAPS, assert_passes
from my_adapter import MyAdapter


@pytest.mark.parametrize("trap", ALL_TRAPS, ids=lambda t: t.id)
def test_no_bias(trap):
    assert_passes(MyAdapter(), trap)
```

If your engine takes a weight matrix rather than calling a strategy each day, `btbias.adapters.view_at` builds a correct point-in-time view, and `fills_from_money` turns a money-traded table into the fills the suite expects.

## The traps

| ID | Bias | What a buggy engine does | How the suite catches it |
| --- | --- | --- | --- |
| T1 | Price lookahead | Shows the strategy prices dated after the decision | No view may contain a later row; NAV must match the strategy run on point-in-time data |
| T2 | Signal/execution misalignment | Fills at the close the signal was computed on | Every fill at the declared price (next open by default); NAV matches |
| T3 | Fundamentals not point-in-time | Uses reports from period end, or restated values before the restatement | Every visible row published by then, exactly as published; NAV matches |
| T4 | Survivorship | Drops companies that later delisted, or their delisting return | NAV of "hold every listed stock" matches, including a takeover (+25%) and a failure (−30%) |
| T5 | Zero transaction costs | Ignores the declared cost model | On flat prices, NAV falls by exactly the costs; each fill reports its cost |
| T6 | Corporate actions unadjusted | Treats a 2:1 split as a 50% crash, or skips dividends | Companies whose value never changes must leave NAV unchanged |
| T7 | Universe membership lookahead | Uses today's index members for the whole history | Every asset offered was a member that day; NAV matches |
| T8 | Free and unlimited shorting | Charges no borrow fee, or shorts names that cannot be borrowed | On flat prices, NAV falls by exactly the fee; hard-to-borrow names never go short |

Each scenario switches on one market feature at a time (gapping opens, costs, delistings, and so on) and keeps the others neutral, so a failure points to one cause.

## Results

Reproduce with `uv run btbias matrix`.

**The tests are sharp and specific.** Each row below is an engine: the reference engine, then the reference engine with exactly one bug (the bug its trap targets). Every bug is caught by its own trap and by no other.

|  | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reference | pass | pass | pass | pass | pass | pass | pass | pass |
| T1 bug: view ends one day late | **fail** | pass | pass | pass | pass | pass | pass | pass |
| T2 bug: fill at the decision close | pass | **fail** | pass | pass | pass | pass | pass | pass |
| T3 bug: fundamentals known at period end | pass | pass | **fail** | pass | pass | pass | pass | pass |
| T4 bug: only today's surviving tickers | pass | pass | pass | **fail** | pass | pass | pass | pass |
| T5 bug: no transaction costs | pass | pass | pass | pass | **fail** | pass | pass | pass |
| T6 bug: no splits or dividends | pass | pass | pass | pass | pass | **fail** | pass | pass |
| T7 bug: today's index members | pass | pass | pass | pass | pass | pass | **fail** | pass |
| T8 bug: borrow terms ignored | pass | pass | pass | pass | pass | pass | pass | **fail** |

**How much each bug moves a backtest**, as final NAV on the trap's own scenario:

| | Bias | Correct engine | With the bug | Bug moves NAV by |
| --- | --- | --- | --- | --- |
| T1 | Price lookahead | −12.6% | +211.5% | +256.6% |
| T2 | Signal/execution misalignment | +4.7% | +0.8% | −3.7% |
| T3 | Fundamentals not point-in-time | −15.1% | −14.2% | +1.0% |
| T4 | Survivorship | −12.1% | −3.1% | +10.2% |
| T5 | Zero transaction costs | −2.1% | +0.0% | +2.1% |
| T6 | Corporate actions unadjusted | +0.0% | −39.4% | −39.4% |
| T7 | Universe membership lookahead | +0.3% | +41.9% | +41.4% |
| T8 | Free and unlimited shorting | −0.5% | +0.0% | +0.5% |

These are sizes on small synthetic markets (30–120 days), not estimates for real data. T3's +1.0% is noise: the synthetic fundamentals do not predict returns, so the leak changes which stock is held without making it a better one. It is caught on the first day either way.

**A second engine passes all eight traps.** The example vectorized engine works in money per asset with numpy and shares no code with the reference engine. It passes all eight traps, and on a 60-day market with gapping opens and costs it matches the reference engine to 1e-9.

## Design trade-offs

Full reasoning is in [DECISIONS.md](DECISIONS.md); the main choices:

- **Ground truth is computed independently.** Every expected NAV comes from a few lines of arithmetic in `btbias.truth` (in money or returns, never shares). A test fails if that module or any trap imports the reference engine.
- **Probes and outcome checks.** Probe checks record what the strategy was shown and name the first day of a leak. Outcome checks compare NAV with ground truth and catch leaks that probes cannot see, such as tomorrow's prices written under today's date.
- **One feature per scenario.** This is what keeps the matrix diagonal. Twice a mutant had to be narrowed when a new feature arrived (delistings, then ex-dates), because "the open equals the previous close" only holds in economic terms once those exist.
- **A strict tolerance (1e-9 relative).** It separates "follows the reference semantics" from "almost does". The price: an engine charging the textbook vectorized cost, `rate × |Δw| × NAV`, fails T5 by about 6e-6 although it charges costs. A per-trap tolerance was the alternative.
- **Raw prices, with corporate actions as data.** If scenarios shipped adjusted prices, an engine that ignores splits would still get them right, and T6 could not catch it.
- **Left out:** statistical checks such as "a random walk should not yield Sharpe 5", which are slow and can flake as pass/fail tests, and any claims about specific third-party engines.

The reference semantics (fills sized at the fill price, costs from cash, fractional shares, delisting and corporate-action timing, borrow fees) are listed in [SPEC.md](SPEC.md#reference-semantics).

## Limitations

- **Daily bars, next-open fills.** No intraday data, order books or partial fills. Every trap scenario declares fills at the next open; an engine that can only fill at the next close cannot run them as they stand.
- **Probes test what the adapter hands over.** For an engine with its own data feed, that is the engine. For a vectorized engine that uses `view_at`, T1, T3 and T7's probes test `view_at`; their outcome checks still test the engine.
- **One feature per scenario.** Bugs that need two features at once (a split on a short position, a delisting during a membership change) are not covered.
- **Strict reference semantics.** Engines that size orders at the decision close or round to whole shares are not wrong, but will miss the 1e-9 tolerance where those choices change the answer.
- **Simple borrow and delisting models.** One borrow rate, a fixed hard-to-borrow list, no recalls or margin; delisting proceeds are paid at the last close.
- **Synthetic markets only.** The suite says whether an engine handles each case correctly, not how large a bias would be on real data.

## Related work

Checked in November 2026 against each project's own documentation; none was installed or run. Tools such as `backtest-audit`, `backtest-auditor` and `replaybt`'s auditor scan strategy code for leak patterns. Freqtrade's `lookahead-analysis` re-runs Freqtrade strategies on truncated data. `peek` and `temporal-leaks` audit ML pipelines for leakage. They test the strategy or the pipeline. This suite tests the engine, against ground truth, and shows its tests are specific with a mutation matrix. More in [SPEC.md](SPEC.md#related-work).

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

CI also runs the tests on the oldest supported numpy (1.26) and pandas (2.2.1).

## License

MIT. See [LICENSE](LICENSE).
