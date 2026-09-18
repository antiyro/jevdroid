# Contributing

Use Python 3.11+ and an isolated virtual environment.

```bash
python -m pip install -e ".[android,dev]"
ruff check .
ruff format --check .
mypy
pytest --cov=jevdroid --cov-report=term-missing
python -m build
```

Tests are offline and must never require a real device, API key, or paid call.
Use HTTPX mock transports for provider contracts and fake `Device`/`Provider`
implementations for the loop. Add regression tests for execution boundaries and
budget changes. Keep public types explicit and provider-specific wire formats
inside `providers/`.

For manual device testing, use your own unlocked, authorized device. Include the
OS, Python version, device model, and measurement boundary in bug reports. Remove
API keys, device identifiers, UI text, and account data before sharing artifacts.

Keep pull requests focused. Describe observable behavior, validation, and any
protocol compatibility limits. Do not claim performance gains without measured
before/after evidence under the same conditions.
