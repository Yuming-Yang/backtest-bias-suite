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
