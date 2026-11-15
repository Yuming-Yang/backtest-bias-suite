# Decisions

Key design decisions, with the alternatives that were considered and dropped. Newest last.

## 2026-11-14 — Spec decisions

See the Decisions section of [SPEC.md](SPEC.md): names, the default fill convention (close t → open t+1), explicit delisting returns, the v1 trap list T1–T7, and no third-party engine adapter in v1.

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

