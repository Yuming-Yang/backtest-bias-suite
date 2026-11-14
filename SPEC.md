# SPEC: Backtest Bias Test Suite

Status: draft, awaiting author review.

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

### Candidate traps for v2 (author to decide)

These come from common practice and I am not sure which are worth the space. Please add, cut, or reorder based on what you have actually seen in research.

- **Universe membership lookahead.** Using today's index constituents for the whole history.
- **Back-adjusted price levels leaking future splits.** A filter like "price > $5" on back-adjusted prices uses information from future splits.
- **Untradable fills.** Fills while an asset is halted, or on a day with no volume.
- **Stale price forward-fill.** Missing prices forward-filled and treated as tradable.
- **Calendar misalignment.** Joining two data sources with different trading calendars or timezones, so one is shifted by a day.

## Package shape

- Python 3.12, managed by uv; numpy and pandas only at runtime.
- Import name: `btbias` (to be confirmed).
- Library API: `btbias.run_suite(adapter) -> SuiteReport`.
- pytest integration: a user writes a 3-line test file that parametrizes the suite over their adapter, and gets one test per trap.
- CLI: `btbias run path.to:MyAdapter` prints a pass/fail table.
- Execution convention is declared per scenario (default: decide at close t, fill at open t+1), so engines that use a different convention can still be tested honestly.

## Non-goals

- Not a backtest engine; the reference engine exists only to validate the tests.
- No real market data. Everything is synthetic and seeded.
- Daily bars only; no intraday or order-book simulation.
- No claims about specific third-party engines unless the author approves (see Open questions).
- Does not detect research-level overfitting (multiple testing, p-hacking). That is a different problem and a possible link to project 11.

## Acceptance criteria

- [ ] The reference engine passes all v1 trap tests.
- [ ] For each of T1–T6, the matching mutant fails that trap's test and passes all the others; the full mutation matrix is printed in the README.
- [ ] Ground truth for every outcome check is computed by code independent of the reference engine (not by calling the engine itself).
- [ ] An example adapter for a second engine style, written as a vectorized pandas engine, is 30 lines or fewer and runs in CI.
- [ ] `uv run pytest` passes in CI (GitHub Actions) with ruff clean.
- [ ] A fresh clone can follow the README to run the suite against the reference engine in under a minute.
- [ ] README: one-sentence problem, quick-start demo, mutation-matrix results, design trade-offs, Limitations.

## Milestones

1. **Scaffold and data model.** uv project, CI, `Scenario` / `View` / `BacktestResult` types, adapter protocol.
2. **Synthetic generator and reference engine.** Seeded generator; minimal event-loop reference engine; basic sanity tests.
3. **Timing traps.** T1 and T2, with probes, outcome checks and mutants.
4. **Point-in-time data traps.** T3 and T4.
5. **Accounting traps.** T5 and T6.
6. **Mutation matrix, CLI, example adapter, README.**

Each milestone is one branch and one PR, followed by a short Chinese walkthrough for the author.

## Cost and dependencies

No paid APIs, no cloud compute, no external data. Synthetic data only, so there is no licensing risk.

## Related work

Not verified. The web search was unavailable when this spec was drafted. Before publishing, check whether there are existing open-source tools that test backtest engines for these biases, and position this project relative to them in the README.

## Open questions for the author

1. **Repo and package name.** Proposed: repo `backtest-bias-suite`, import name `btbias`.
2. **Trap list.** Is the v1 list right? Which v2 candidates matter, and what is missing from your own experience?
3. **Execution convention.** Default is decide at close t, fill at open t+1. Is that the convention you want as the default, or should it be next close?
4. **Delisting return.** Use an explicit delisting return in the scenario (CRSP-style), or assume the position is liquidated at the last traded price?
5. **Real engine adapter (stretch).** Should we write an adapter for a well-known open-source engine and publish the results? This would be stronger evidence, but it means making a public statement about a third-party product.
