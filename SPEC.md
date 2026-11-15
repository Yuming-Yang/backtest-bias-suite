# SPEC: Backtest Bias Test Suite

Status: v1 complete on 2026-11-15. Scope and reference semantics fixed on 2026-11-14.

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
| T8 | Free and unlimited shorting | Short positions pay no borrow fee, and assets that cannot be borrowed are shorted anyway | Outcome: a short held on flat prices loses exactly the borrow fee; an order that would open a short in a non-shortable asset is not filled |

### Candidate traps for v2

Ranked by how common they are and how cleanly they can be tested deterministically. Universe membership lookahead, ranked first in the draft, was moved into v1 as T7.

1. **Stale prices and untradable fills.** Missing prices are forward-filled and treated as tradable, or fills happen while an asset is halted or has zero volume. Merged into one trap because the test scenario is the same.
2. **Back-adjusted price levels leaking future splits.** A filter like "price > $5" on back-adjusted prices uses information from future splits.
3. **Calendar misalignment.** Joining two data sources with different trading calendars or timezones, so one is shifted by a day. Real, but closer to data engineering, and harder to stage naturally.
4. **A combined scenario.** One market with every feature switched on at once (moving opens, costs, a split, a delisting, a membership change, a short). It only has to match ground truth; it is not part of the mutation matrix, because every mutant is expected to fail it. This covers bugs that need two features to interact, which the one-feature-per-scenario rule in v1 cannot reach.

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

- [x] The reference engine passes all v1 trap tests.
- [x] For each of T1–T8, the matching mutant fails that trap's test and passes all the others; the full mutation matrix is printed in the README.
- [x] Ground truth for every outcome check is computed by code independent of the reference engine (not by calling the engine itself).
- [x] An example adapter for a second engine style, written as a vectorized pandas engine, is 30 lines or fewer and runs in CI.
- [x] `uv run pytest` passes in CI (GitHub Actions) with ruff clean.
- [x] A fresh clone can follow the README to run the suite against the reference engine in under a minute.
- [x] README: one-sentence problem, quick-start demo, mutation-matrix results, design trade-offs, Limitations.

## Milestones

1. **Scaffold and data model.** uv project, CI, `Scenario` / `View` / `BacktestResult` types, adapter protocol. Done.
2. **Generator, reference engine and one trap end to end.** Seeded generator; minimal event-loop reference engine; T5 with its mutant; a first draft of the vectorized example adapter. T5 is the simplest trap, and the example adapter is the riskiest acceptance criterion, so both come early to test the contract before the other traps are built on it. Done.
3. **Timing traps.** T1 and T2, with probes, outcome checks and mutants. Done.
4. **Point-in-time data traps.** T3, T4 and T7. Done.
5. **Accounting traps.** T6 and T8. Done.
6. **Mutation matrix, CLI, final example adapter, README.** Done.

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

## Reference semantics

What "correct" means for outcome checks. The reference engine and every ground truth follow these rules.

1. **Sizing happens at the fill.** An order decided at the close of t is sized with prices on the fill day. With fill price `p_i` and `NAV_fill = cash + sum(shares_i * p_i)`, the target is `shares_i = w_i * NAV_fill / p_i`. Splits and dividends with that ex-date are applied first. Sizing at the decision close instead would spend money the portfolio does not have whenever prices gap up overnight.
2. **Costs come out of cash.** Each fill pays `rate * |traded notional|`. The engine does not solve for the share count that hits the target exactly after costs. Suite strategies keep gross exposure at or below 0.95, so cash never goes negative.
3. **Fractional shares.** No lot rounding. Outcome checks compare NAV with a relative tolerance of 1e-9.
4. **Orders that cannot fill are cancelled.** If an asset has no price on the fill day, its order is dropped, not carried forward. Orders decided on the last calendar day never fill.
5. **`View.universe`.** If the scenario has a membership table, the index members at `as_of`. Otherwise the assets with a price at `as_of`.
6. **Shorting.** A scenario declares a daily borrow rate and which assets can be borrowed. Each day a short pays `borrow_rate * |short market value at the close|` from cash. The part of an order that would take a position below zero in a non-shortable asset is not filled.
7. **Delisting.** A position in an asset that delists becomes cash at the close of its last trading day: `shares * close * (1 + delisting_return)`. NAV on that day already includes it.
8. **Corporate actions.** Splits and dividends take effect at the open of the ex-date, before that day's fills. A split multiplies shares by its ratio; a dividend pays `shares * amount` in cash. On a day with both, the dividend is paid on pre-split shares.

An engine that sizes at the decision close, or rounds to whole shares, is not wrong. Outside T2, scenarios are built so the two sizing rules agree (see the next section). Whole-share engines are a known limitation.

## Isolation between traps

A fill-timing bug changes NAV in any scenario that trades at a moving price. A missing-cost bug changes NAV wherever the cost rate is not zero. For each mutant to fail only its own trap, each scenario switches on one feature and keeps the rest neutral.

| Scenario for | Next open ≠ close on trade days | Cost rate > 0 | Splits, dividends | Delistings | Membership changes | Fundamentals | Shorts |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T1 price lookahead | no | no | no | no | no | no | no |
| T2 fill timing | **yes** | no | no | no | no | no | no |
| T3 point-in-time fundamentals | no | no | no | no | no | **yes** | no |
| T4 survivorship | no | no | no | **yes** | no | no | no |
| T5 costs | no | **yes** | no | no | no | no | no |
| T6 corporate actions | no | no | **yes** | no | no | no | no |
| T7 membership | no | no | no | no | **yes** | no | no |
| T8 shorting | no | no | no | no | no | no | **yes** |

Two more rules follow from the table:

- Where the first column says no, the open on every fill day equals the previous close. Filling at the decision close and filling at the next open then give the same shares and the same NAV, so the T2 mutant passes, and so does an engine that sizes at the decision close.
- Each scenario's strategy reads only the data its trap is about. The T2 strategy trades on a fixed schedule and ignores prices, so a view that leaks future prices cannot change its orders.

## Known limits (for the README Limitations section)

- **Probes test what the adapter hands over.** For an engine with its own data feed, that exercises the engine. For a vectorized engine, the adapter author writes the daily slicing, so a probe tests the adapter. Outcome checks do not have this gap.
- **Scenarios are clean on purpose.** One feature at a time makes failures attributable, and unlike a real market. Bugs that only appear when two features interact are out of reach in v1; a combined scenario is listed as a v2 candidate.
- **Whole-share engines** will miss the 1e-9 tolerance.
- **T8 covers feasibility, not attribution.** It checks that shorts cost money and that unborrowable assets are not shorted. Whether a long-short strategy earns most of its return on the short leg is a property of the strategy, and the suite does not report it.

## Decisions (2026-11-14)

1. **Names.** Repo `backtest-bias-suite`, import name `btbias`. Neither was taken on PyPI or under the author's GitHub account when checked.
2. **Trap list.** v1 is T1–T8. T7 (universe membership lookahead) was promoted from the v2 list because it shares T4's test machinery. T8 (free and unlimited shorting) comes from first-hand research experience: long-short results where most of the return sat in the short leg, in names that are not easy to borrow. v2 candidates are ranked above.
3. **Default execution convention.** Decide at close t, fill at open t+1. Each scenario can still declare another convention. Splits and dividends take effect at the open on the ex-date, so ground truth must apply the corporate action before the t+1 open fill.
4. **Delisting.** Scenarios carry an explicit delisting return (CRSP-style), defaulting to 0. Liquidating at the last traded price is the special case where the return is 0. T4 scenarios include both a positive case (cash merger) and a large negative case (performance-related delisting).
5. **Third-party engine adapter.** Not in v1. Any later result is to be reported as "results under default configuration" with the configuration stated, and with data-layer failures kept apart from engine failures.
