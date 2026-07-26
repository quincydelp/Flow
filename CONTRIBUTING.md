# Contributing

Flow is early and its execution semantics are still being shaped. Issues and
small, focused pull requests are welcome.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,yaml,agents]"
ruff check .
pytest
```

Please add tests for behavior changes and keep integrations behind the registry
interfaces so the core remains provider-independent.

