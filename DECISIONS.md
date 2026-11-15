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
