# backtest-bias-suite

Work in progress. A test suite that checks daily-bar backtest engines for common biases (lookahead, survivorship, missing costs, unadjusted corporate actions) on synthetic data with known answers.

See [SPEC.md](SPEC.md) for the problem definition, scope and acceptance criteria.

## Current state

T5 (zero transaction costs) runs end to end; the other traps are being added one milestone at a time.

```python
from btbias import ReferenceEngine, run_suite

report = run_suite(ReferenceEngine())
print(report.passed, report.failed_ids)  # True ()
```

- `btbias.ReferenceEngine`: a small event-loop engine that follows the reference semantics in SPEC.md.
- `btbias.mutants`: the reference engine with one bug each. `tests/test_mutation_matrix.py` checks that every mutant fails its own trap and passes the rest.
- `examples/`: a vectorized engine and the 25-line adapter that plugs it into the suite.

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## License

MIT. See [LICENSE](LICENSE).
