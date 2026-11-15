# Decisions

Key design decisions, with the alternatives that were considered and dropped. Newest last.

## 2026-11-14 — Spec decisions

See the Decisions section of [SPEC.md](SPEC.md): names, the default fill convention (close t → open t+1), explicit delisting returns, the v1 trap list (now T1–T8), and no third-party engine adapter in v1.

## 2026-11-14 — Raw prices; corporate actions in a separate table

**Decision.** Scenario prices are raw, as traded. Splits and dividends are rows in `corporate_actions`.

**Why.** If the scenario shipped adjusted prices, an engine that ignores corporate actions would still get the right NAV, and T6 could not catch it. Raw prices also make the v2 trap "back-adjusted price filter" possible later.

**Dropped.** Shipping both raw and adjusted prices. It is convenient for engines, but it doubles the surface where the two can disagree, and the suite would then have to test that adjustment too.

## 2026-11-14 — Wide price frames, long metadata tables

**Decision.** `open` and `close` are wide (date × asset). Fundamentals, corporate actions and membership are long tables.

**Why.** Prices are dense and every engine style (event loop or vectorized) reads them by date. The metadata is sparse and event-like, and fundamentals need several rows per period to represent restatements.

## 2026-11-14 — No same-close convention

**Decision.** `ExecutionConvention` offers only `NEXT_OPEN` and `NEXT_CLOSE`.

**Why.** With daily bars, filling at the close the signal was computed on is the T2 bug. Real market-on-close execution needs the signal before the close, which daily bars cannot represent. If an engine really does that, it should be modeled with intraday data, which is out of scope.

## 2026-11-14 — `View` does not validate itself

**Decision.** `View` is a plain frozen dataclass with no checks.

**Why.** The suite exists to find views that leak the future. If `View` raised on rows after `as_of`, a leaking engine would crash, and the probe strategies could not report the exact date of the leak. Checks live in the probes, not the container.

## 2026-11-14 — Scenarios validate on construction

**Decision.** `Scenario.__post_init__` rejects inconsistent data, for example prices after the delist date, fundamentals published before the period ends, or overlapping membership intervals.

**Why.** A broken scenario would make a correct engine look buggy. That would damage the core claim of the mutation matrix: each test fails only on its own bug.

**Trade-off.** The dataclass is frozen but its frames are not deep-frozen. Treating a scenario as read-only is a convention, not something the code enforces. Deep copies on every access would make the suite slower for little gain at this size.

## 2026-11-14 — Delisting return timing matches CRSP

**Decision.** `delisting_return` is measured from the close on `delist_date` (the last trading day) to the cash received after delisting, and is compounded onto the position after that close.

**Why.** This matches CRSP's definition of `DLRET`: a value after delisting compared with the price on the last trading date, combined with the regular return. Worthless shares give −100%, which is why validation allows `>= -1`.

**Context for scenarios.** CRSP leaves many performance-related delisting returns missing. The common fix from the literature (Shumway 1997, and Shumway & Warther 1999 for Nasdaq) imputes about −30% for NYSE/AMEX and −55% for Nasdaq. T4 scenarios use a large negative delisting return in this range, so dropping it visibly changes NAV.

## 2026-11-14 — Target weights are unconstrained

**Decision.** `Strategy.target_weights` may return any finite weights, including shorts and gross exposure above 1. The suite does not enforce long-only or a leverage cap.

**Why.** Constraints belong to a strategy, not to the engine contract. The suite's own probe and outcome strategies will stay long-only and fully funded, so their ground truth does not depend on borrow costs or margin, which are out of scope for v1.

## 2026-11-14 — The delist date must be a day the asset trades

**Decision.** A scenario is rejected if an asset has no price on its `delist_date`, or carries a non-zero `delisting_return` without a `delist_date`.

**Why.** The delisting return is defined from the close on the last trading day. Without a close on that day there is nothing to compound it onto, and each engine would be free to guess. Found by probing the validator with edge cases after milestone 1; nine other inconsistent inputs were closed in the same change.

## 2026-11-14 — Dependency floors are tested, not inherited

**Decision.** `numpy>=1.26`, `pandas>=2.2.1`, and a CI job that installs the lowest allowed versions.

**Why.** The first floors were simply the versions installed on day one (numpy 2.5, pandas 3.1). A suite that wraps other engines has to run in their environment, and many still pin pandas 2.x.

**Dropped.** `pandas>=2.2.0`: importing 2.2.0 emits a pyarrow DeprecationWarning, and this project runs pytest with warnings as errors. Relaxing that filter for one patch release was not worth it.

## 2026-11-14 — Reference semantics: size at the fill, costs from cash

**Decision.** Orders are sized with fill-day prices, costs are deducted from cash, shares are fractional, and unfillable orders are cancelled. Full rules are in SPEC.md under "Reference semantics".

**Why.** Sizing at the fill never overspends and matches the `weights * returns` arithmetic of vectorized research code, so ground truth can be computed by hand.

**Dropped.** Sizing at the decision close. Many event-driven engines do this, and it is not a bug, but it needs a rule for what happens when the fill costs more than the cash available. Scenarios outside T2 set the next open equal to the close, so engines of either kind get the same answer.

## 2026-11-14 — One feature per scenario

**Decision.** Each trap's scenario switches on exactly one feature (moving opens, costs, corporate actions, delistings, membership changes, fundamentals, shorts). The table is in SPEC.md.

**Why.** Otherwise a fill-timing mutant fails every test that trades, and the mutation matrix cannot show that each test is specific.

**Trade-off.** Bugs that need two features at once, such as a split on the day after a delisting, are not covered.

## 2026-11-14 — T8: shorting is in scope, for one trap only

**Decision.** Add T8, free and unlimited shorting. Scenarios gain a daily borrow rate and a per-asset shortable flag. This revises the earlier "target weights are unconstrained" entry: suite strategies stay long-only everywhere except T8.

**Why.** A long-short backtest can look good because of its short leg while those shorts could not have been borrowed, or not at zero cost. An engine that lets this through inflates exactly the strategies that are hardest to trade.

**Dropped.** Time-varying borrow availability, recalls and margin. They are real, but each needs its own ground truth, and a static flag is enough to catch an engine that ignores borrowing altogether.

## 2026-11-14 — Mutants override one method of the reference engine

**Decision.** Each rule of the reference semantics is its own method on `ReferenceEngine`. A mutant is a subclass that overrides exactly one of them. The T5 mutant overrides `transaction_cost` to return 0.

**Why.** The diff between the reference and a mutant is then a few lines anyone can read, and "exactly one bug" is visible in the code rather than promised in a comment.

**Dropped.** A `bugs=` flag set on the engine, with `if` branches inside it. It keeps everything in one file, but it makes the reference engine harder to read and lets two flags interact in ways the mutation matrix never tests.

## 2026-11-14 — The reference engine refuses what it does not model yet

**Decision.** Until their traps land, the reference engine raises `NotImplementedError` for corporate actions, delistings and short positions.

**Why.** An engine that silently ignores a split returns a plausible NAV. If a scenario with one slipped into a test before T6 exists, the test would pass for the wrong reason.

## 2026-11-14 — Engine errors are results, not exceptions

**Decision.** `run_trap` catches any exception from the adapter and reports it as `ERROR`. In the mutation matrix, a mutant that makes its own trap crash counts as not caught.

**Why.** A suite run should report every trap, not stop at the first engine that crashes. And a trap that only "catches" a bug by crashing would give a user no message about what went wrong.

## 2026-11-14 — Ground truth works in money, and its independence is tested

**Decision.** T5's expected NAV comes from `truth.flat_market_nav`, a ten-line loop over money per asset. A test parses the imports of `truth.py` and every trap module and fails if any imports the reference engine or the mutants.

**Why.** On a market where no price moves, shares and prices drop out of the problem, so the ground truth can be written without any of the engine's machinery. The import test turns the acceptance criterion "ground truth is independent of the reference engine" into something CI checks.

## 2026-11-14 — Keep the 1e-9 tolerance; the example engine tracks drift

**Decision.** Outcome checks keep a relative tolerance of 1e-9. The example vectorized engine keeps one loop over days so that each fill trades the gap between the target and the holdings as they drifted since the last fill.

**Why.** Drafting the example adapter showed that the textbook vectorized cost, `rate * |w_t - w_{t-1}| * NAV`, ignores that drift. On the T5 scenario it ends about 6e-6 (relative) away from the exact NAV, against a cost effect of about 2%. It fails T5 at 1e-9 even though it charges costs. With 1e-9 the suite can tell "follows the reference semantics" from "almost does", and the example shows an exact vectorized engine is possible in about 60 lines.

**Trade-off.** Engines that use the textbook formula will fail T5 without a cost bug. The alternative is a per-trap tolerance set well below the size of the effect each trap tests (on T5, 1e-4 would still sit two orders of magnitude below the 2% effect). That would accept approximate engines at the price of missing bugs smaller than the tolerance.

## 2026-11-14 — `View.weights` is optional

**Decision.** Suite strategies never read `View.weights`.

**Why.** A vectorized engine takes all decisions up front and only knows its holdings after the run, so its adapter cannot fill this field. Requiring it would rule out the most common engine style in research code.

## 2026-11-15 — T1 uses one strategy as both probe and outcome check

**Decision.** T1's momentum strategy records every view (the probe) and trades on the last row it is shown (the outcome). The check flags any view with rows dated after `as_of`, and separately compares NAV with the strategy run on point-in-time data.

**Why.** Each check misses a case the other catches. The probe names the exact day of a leak but trusts the dates; an engine that writes tomorrow's prices under today's date passes it. The outcome check catches that, but on its own it would only say "NAV is off". The strategy reads `iloc[-1]` rather than `loc[as_of]` on purpose: it trusts the engine, as most strategy code does, so a leak changes its orders.

**Guard.** A test checks that the expected momentum picks switch often (more than 20 times across all four assets). If the strategy held one asset throughout, a leak could leave its orders unchanged and the outcome check would see nothing.

## 2026-11-15 — The T2 mutant fills on the next day at the decision close

**Decision.** `SameCloseEngine` overrides only `fill_prices`: the fill is still dated the day after the decision, but at the decision day's close.

**Why.** Dating the trade on the decision day as well would mean changing the engine loop, not one method. The price is what makes this bug inflate results, and both T2 checks (fill price, NAV) catch it. Where opens equal the previous close, as in every scenario except T2's, the mutant gives bit-for-bit the same answer as the reference engine, which is what keeps the mutation matrix diagonal.

**Dropped.** A probe for T2 (for example, checking the date of each fill). Fill dates belong to the result, not the view, so the price check already covers them.

## 2026-11-15 — Ground truth for moving markets comes from returns, not shares

**Decision.** `truth.no_cost_nav` computes NAV from weights and returns between fill prices, as a cumulative product. It requires a price for every asset on every day and no costs.

**Why.** Without costs, rebalancing to target weights at a fill makes growth until the next fill exactly `1 + w . r`. That shares no code path with the share-and-cash bookkeeping of the reference engine, so the two agreeing is evidence, not a tautology.

## 2026-11-15 — Delisting proceeds are booked at the last close

**Decision.** A position in an asset that delists becomes cash at the close of its last trading day, at `shares * close * (1 + delisting_return)`. This is reference semantics rule 7 in SPEC.md.

**Why.** Booking the cash the next day would lose the delisting return whenever the last trading day is the last day of the scenario. It would also leave a position in the books that can no longer be priced. Booked at the close, NAV on the last trading day already shows what holders received, and the strategy deciding that evening sees it as cash.

**Dropped.** Paying out on the next trading day. It is closer to how cash from a merger actually settles, but the extra day of delay changes no test and adds an edge case.

## 2026-11-15 — The T2 mutant cannot fill an asset that does not trade

**Decision.** `SameCloseEngine` uses the decision-day close only for assets that trade on the fill day.

**Why.** Without this, an order decided on an asset's last trading day filled the next day at that close, buying a stock that no longer exists. That is a second bug, and it made the T2 mutant fail T4 too. The isolation table assumed opens equal previous closes wherever there is a price, and delistings are where "wherever there is a price" starts to matter.

## 2026-11-15 — T3 checks that rows are shown exactly as published

**Decision.** Besides "no row published after the decision day", the T3 probe requires every visible row to match a scenario row on all five columns.

**Why.** A common leak keeps only the latest value of each report but under its first publish date. Publish dates then look fine and only the values are wrong. Matching whole rows catches this, while still allowing an engine to show fewer rows (hiding data is not lookahead).

**Limit.** The synthetic fundamentals do not predict returns, so a leak changes NAV by noise rather than by a systematic gain. The test only needs the NAV to differ, and a guard checks that the leak changes the strategy's pick on at least 20 days.

## 2026-11-15 — Survivorship is staged through the universe

**Decision.** The T4 mutant drops every asset that ever delists from the universe, as a data set built from today's tickers would. Dropping the delisting return is covered by a separate test engine, not a second mutant.

**Why.** One mutant per trap keeps the matrix square. Both bugs make NAV wrong in the same scenario, so the outcome check covers both.

## 2026-11-15 — T7 stages realistic index changes

**Decision.** In T7, the assets that join the index drift up beforehand and those that leave drift down, by 0.8% a day.

**Why.** Index additions tend to follow strong performance and deletions weak performance. With that in place the mutant (today's constituents throughout) ends 41% above the correct NAV, which shows why the bias matters and not only that the test can detect it. Detection does not depend on the drift: the probe fires on the first day.

## 2026-11-15 — The example adapter runs only the traps its engine models

**Decision.** The example vectorized adapter runs T1, T2 and T5.

**Why.** It builds views from prices alone and its engine needs a price for every asset on every day. Running T3, T4 and T7 against it would only show what the example leaves out. Whether to extend it depends on how much fits in the 30-line adapter limit.

## 2026-11-15 — T6 runs on companies whose value never changes

**Decision.** T6's prices are flat in total-return terms: raw prices drop on each ex-date by the dividend and then the split ratio, and are otherwise constant. The expected NAV is the initial cash on every day.

**Why.** It is the one ground truth nobody has to take on trust: if nothing about the companies changed, a correct backtest cannot make or lose money. An engine that ignores a split books it as a crash (the mutant ends 39% down); one that ignores dividends loses the payout. The strategy changes its allocation every day, so the engine also has to size orders correctly right after each action.

**Dropped.** A random walk with corporate actions on top. Its ground truth would need adjusted prices, which is the very calculation T6 is testing.

## 2026-11-15 — The T2 mutant restates the decision close across ex-dates

**Decision.** On a fill day that is also an ex-date, `SameCloseEngine` converts the decision-day close into post-action shares before using it.

**Why.** Otherwise it paid a pre-split price for post-split shares, a second bug that also failed T6. The conversion uses the same rule as the generator (dividend off, then divide by the ratio), so on T6's market the mutant matches the reference engine bit for bit. A test fails without it.

## 2026-11-15 — Borrow terms are a model, like costs

**Decision.** `Scenario.borrow` is a `BorrowModel`: one daily rate on the market value of shorts at each close, and a set of hard-to-borrow assets that cannot be shorted. The engine reads it through one method, and the T8 mutant overrides that method to return the free and unlimited default.

**Why.** It mirrors how T5 treats the cost model, so "ignores the declared borrow terms" is one bug in one place. Splitting T8 into a fee mutant and an availability mutant would break the one-mutant-per-trap rule; instead, two test engines show that each half is caught on its own (no fee on NAV; shorting a hard-to-borrow name by name).

**Dropped.** Per-asset borrow rates, time-varying availability and recalls. They are real, and listed under Known limits in SPEC.md, but a flat rate and a static list are enough to catch an engine that ignores borrowing.

## 2026-11-15 — The example engine covers every trap

**Decision.** The example vectorized engine models missing prices, delisting returns, splits and dividends, borrow fees and a no-short list, and passes all eight traps. This replaces the earlier decision to run it on T1, T2 and T5 only.

**Why.** Until then only the reference engine had passed every trap, and the traps were written alongside it. An engine written separately, in another style (money per asset, a weight matrix up front), passing all eight is the best available evidence that the traps test the reference semantics and not one implementation's habits.

## 2026-11-15 — Adapter helpers live in the library

**Decision.** `btbias.adapters` provides `view_at` (a point-in-time view) and `fills_from_money` (a money-traded table to one row per fill). The example adapter uses both and is 28 code lines.

**Why.** Formatted normally, the full adapter was 39 lines. Both pieces are needed by every adapter around a weight-matrix engine, and writing the point-in-time rules again in each adapter would invite exactly the bugs the suite looks for. The line-count test also rejects `fmt: skip`, so the 30-line limit is not met by squeezing lines past the formatter.

**Trade-off.** For an adapter that uses `view_at`, the probes of T1, T3 and T7 test `view_at` rather than the engine. This is listed under Limitations in the README.

## 2026-11-15 — The pytest pattern is six lines, not three

**Decision.** `btbias.testing` exports `ALL_TRAPS` and `assert_passes`; a user parametrizes one test over the traps.

**Why.** The spec guessed three lines. Getting one named test per trap needs the import, a parametrize decorator with ids and a test function, which is six lines. A pytest plugin could hide them, but would make pytest a dependency for a gain of three lines.
