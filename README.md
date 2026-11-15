# backtest-bias-suite

Work in progress. A test suite that checks daily-bar backtest engines for common biases (lookahead, survivorship, missing costs, unadjusted corporate actions) on synthetic data with known answers.

See [SPEC.md](SPEC.md) for the problem definition, scope and acceptance criteria.

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## License

MIT. See [LICENSE](LICENSE).
