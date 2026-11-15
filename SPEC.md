# SPEC: Backtest Bias Test Suite

Status: v1 scope fixed on 2026-11-14. The questions under "Open design questions" are to be settled before milestone 2.

## Problem

A backtest engine can produce a good-looking equity curve from a strategy with no real edge. The usual causes are well known: the strategy sees prices it could not have seen yet, fundamentals are used before they were published, delisted stocks have quietly disappeared from history, fills happen at the same price the signal was computed from, trading is free, and splits look like crashes. These bugs rarely raise an error. They just make the numbers better.

This project is a test suite that wraps around any daily-bar backtest engine and checks, on synthetic data with a known ground truth, that the engine does not fall for each of these traps. Think of it as pytest for a backtest engine.

## Approach

1. **Synthetic market generator.** Seeded, deterministic scenarios: price paths, universe entries and exits, delistings with a delisting return, fundamentals with both a period-end date and a publish date (including restatements), splits and cash dividends. Every scenario is small (a handful of assets, tens to hundreds of days), so the expected result can be computed by hand or by a few lines of independent code.
2. **Adapter contract.** The suite does not assume any particular engine. A user writes an adapter that:
   - takes a `Scenario` (market data, cost model, execution convention) and a `Strategy`;
   - runs the engine, calling `strategy.target_weights(view)` at each decision time, where `view` is whatever data the engine exposes at that moment;
   - returns a `BacktestResult` (held weights, executed trades with prices, daily NAV).

   Target: a third-party engine can be wired up in 30 lines or fewer.
3. **Two kinds of checks per trap.**
   - *Probe checks* (deterministic): suite-provided strategies inspect the `view` they receive and record what they saw, for example the latest price timestamp or which fundamental vintages were visible. A leak is caught at the exact bar where it happens.
   - *Outcome checks* (deterministic): the engine's NAV, trades and fill prices are compared against an independently computed ground truth, within a stated numerical tolerance.

   Statistical checks (for example, "a random-walk market should not yield Sharpe 5") are kept as a secondary diagnostic only, because they are slower and can flake.
4. **Reference engine and mutants.** A deliberately small, readable reference engine passes every test. Each trap has a mutant: the reference engine with exactly one bug switched on. A meta-test checks the mutation matrix: every mutant fails its own trap and only its own trap. This shows that the tests are sharp (they catch the bug) and specific (they do not fire on unrelated bugs).

## Trap list (v1)

| ID | Trap | What a buggy engine does | How the suite detects it |
| --- | --- | --- | --- |
| T1 | Price lookahead | `view` at decision time t includes bars after t | Probe: max timestamp seen ≤ t. Outcome: momentum strategy on a scenario where peeking yields a known, very different NAV |
| T2 | Signal/execution misalignment | Order is filled at the same close the signal was computed on | Outcome: fill prices and NAV must match the declared convention (decide at close t, fill at open t+1) |
| T3 | Fundamentals not point-in-time | Fundamentals visible from period end instead of publish date; restated values leak backward | Probe: every visible value has publish date ≤ t, and the as-originally-reported value is shown until the restatement date |
| T4 | Survivorship bias | Assets that delist are missing from the whole history, or their delisting return is dropped | Outcome: equal-weight "hold all listed assets" NAV matches the ground truth including delisted names and delisting returns |
| T5 | Zero transaction costs | Declared cost model is ignored | Outcome: on flat prices, a pure-turnover strategy loses exactly turnover × cost rate |
| T6 | Corporate actions unadjusted | A 2:1 split shows up as a −50% return; dividends are not credited | Outcome: holding through a split leaves NAV unchanged; holding through a dividend increases NAV by the dividend amount |
| T7 | Universe membership lookahead | Today's index constituents are used for the whole history | Probe: every asset offered at t was a member at t. Outcome: equal-weight "hold the index members" NAV matches the ground truth built from point-in-time membership |

### Candidate traps for v2

Ranked by how common they are and how cleanly they can be tested deterministically. Universe membership lookahead, ranked first in the draft, was moved into v1 as T7.

1. **Stale prices and untradable fills.** Missing prices are forward-filled and treated as tradable, or fills happen while an asset is halted or has zero volume. Merged into one trap because the test scenario is the same.
2. **Back-adjusted price levels leaking future splits.** A filter like "price > $5" on back-adjusted prices uses information from future splits.
3. **Calendar misalignment.** Joining two data sources with different trading calendars or timezones, so one is shifted by a day. Real, but closer to data engineering, and harder to stage naturally.

## Package shape

- Python 3.12, managed by uv; numpy and pandas only at runtime.
- Import name: `btbias`.
- Library API: `btbias.run_suite(adapter) -> SuiteReport`.
- pytest integration: a user writes a 3-line test file that parametrizes the suite over their adapter, and gets one test per trap.
- CLI: `btbias run path.to:MyAdapter` prints a pass/fail table.
- Execution convention is declared per scenario (default: decide at close t, fill at open t+1), so engines that use a different convention can still be tested honestly.

## Non-goals

- Not a backtest engine; the reference engine exists only to validate the tests.
- No real market data. Everything is synthetic and seeded.
- Daily bars only; no intraday or order-book simulation.
- No claims about specific third-party engines in v1 (see Decisions, item 5).
- Does not detect research-level overfitting (multiple testing, p-hacking). That is a different problem.

## Acceptance criteria

- [ ] The reference engine passes all v1 trap tests.
- [ ] For each of T1–T7, the matching mutant fails that trap's test and passes all the others; the full mutation matrix is printed in the README.
- [ ] Ground truth for every outcome check is computed by code independent of the reference engine (not by calling the engine itself).
- [ ] An example adapter for a second engine style, written as a vectorized pandas engine, is 30 lines or fewer and runs in CI.
- [ ] `uv run pytest` passes in CI (GitHub Actions) with ruff clean.
- [ ] A fresh clone can follow the README to run the suite against the reference engine in under a minute.
- [ ] README: one-sentence problem, quick-start demo, mutation-matrix results, design trade-offs, Limitations.

## Milestones

1. **Scaffold and data model.** uv project, CI, `Scenario` / `View` / `BacktestResult` types, adapter protocol.
2. **Synthetic generator and reference engine.** Seeded generator; minimal event-loop reference engine; basic sanity tests.
3. **Timing traps.** T1 and T2, with probes, outcome checks and mutants.
4. **Point-in-time data traps.** T3, T4 and T7.
5. **Accounting traps.** T5 and T6.
6. **Mutation matrix, CLI, example adapter, README.**

Each milestone is one branch and one PR.

## Cost and dependencies

No paid APIs, no cloud compute, no external data. Synthetic data only, so there is no licensing risk.

## Related work

Checked on 2026-11-14 against each project's PyPI metadata, README or official docs. None of them was installed or run, so the descriptions below are what the projects say about themselves.

Existing tools fall into two groups, and both test the **strategy**, not the **engine**:

- **Static linters for strategy code.** They scan Python source for leak patterns and do not run a backtest. `backtest-audit` and `backtest-auditor` (both on PyPI) describe themselves this way. `replaybt` is a backtest engine that ships a static bias auditor among its validation tools.
- **Re-run checks.** Freqtrade's `lookahead-analysis` chains backtests and compares indicator values and entries/exits against the full run; it does not read the strategy code, and it only works for Freqtrade strategies. `peek` and `temporal-leaks` audit time-series ML pipelines for leakage.

This project differs in three ways:

1. It tests the **engine**: whether the engine leaks data, misaligns fills, drops delisted names, skips costs or mishandles corporate actions, whatever strategy it runs.
2. It checks against a **ground truth** on synthetic data with known answers, not against patterns or heuristics.
3. It shows the tests are sharp and specific with a **mutation matrix** (one bug per mutant).

The search found no open-source tool that tests an engine for survivorship bias or point-in-time fundamentals (T3, T4). That is an absence of search results, not proof that none exists.

## Open design questions

To settle before milestone 2, because the reference engine and every ground truth depend on them.

1. **Reference accounting.** How target weights become share counts under each convention: which NAV the weights apply to, where costs are taken from, whether fractional shares are allowed, and what happens to an order for an asset that does not trade on the fill day.
2. **Isolation between traps.** A fill-timing bug changes NAV in any scenario that trades, and a missing-cost bug changes NAV in any scenario with a non-zero cost rate. For each mutant to fail only its own trap, every outcome scenario has to be insensitive to the other bugs. This needs an explicit table: scenario by trap, sensitive or not.
3. **Meaning of `View.universe`.** Listed assets, or index members when the scenario has a membership table. T7's probe depends on the answer.
4. **What probes can reach.** Probes inspect the `View` the adapter builds. For an engine with its own data feed this exercises the engine. For a vectorized engine the adapter author writes the slicing, so the probe tests the adapter. Outcome checks do not have this gap. This belongs in Limitations.

## Decisions (2026-11-14)

1. **Names.** Repo `backtest-bias-suite`, import name `btbias`. Neither was taken on PyPI or under the author's GitHub account when checked.
2. **Trap list.** v1 is T1–T7: the original six plus universe membership lookahead, which shares T4's test machinery. v2 candidates are ranked above. The list stays open for traps from first-hand research experience.
3. **Default execution convention.** Decide at close t, fill at open t+1. Each scenario can still declare another convention. Splits and dividends take effect at the open on the ex-date, so ground truth must apply the corporate action before the t+1 open fill.
4. **Delisting.** Scenarios carry an explicit delisting return (CRSP-style), defaulting to 0. Liquidating at the last traded price is the special case where the return is 0. T4 scenarios include both a positive case (cash merger) and a large negative case (performance-related delisting).
5. **Third-party engine adapter.** Not in v1. Any later result is to be reported as "results under default configuration" with the configuration stated, and with data-layer failures kept apart from engine failures.
