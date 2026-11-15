# backtest-bias-suite

Work in progress. A test suite that checks daily-bar backtest engines for common biases (lookahead, survivorship, missing costs, unadjusted corporate actions) on synthetic data with known answers.

See [SPEC.md](SPEC.md) for the problem definition, scope and acceptance criteria.

## Current state

All eight v1 traps run end to end: T1 (price lookahead), T2 (signal/execution misalignment), T3 (fundamentals not point-in-time), T4 (survivorship), T5 (zero transaction costs), T6 (corporate actions unadjusted), T7 (universe membership lookahead) and T8 (free and unlimited shorting).

```python
from btbias import ReferenceEngine, run_suite

report = run_suite(ReferenceEngine())
print(report.passed, report.failed_ids)  # True ()
```

- `btbias.ReferenceEngine`: a small event-loop engine that follows the reference semantics in SPEC.md.
- `btbias.mutants`: the reference engine with one bug each. `tests/test_mutation_matrix.py` checks that every mutant fails its own trap and passes the rest.
- `examples/`: a vectorized engine and the 25-line adapter that plugs it into the suite. It runs T1, T2 and T5; it does not model fundamentals, index membership or delistings yet.

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## License

MIT. See [LICENSE](LICENSE).
