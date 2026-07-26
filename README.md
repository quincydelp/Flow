# Flow

Flow is an open-source declarative workflow framework that puts deterministic
software around probabilistic AI agents.

Define a typed DAG, connect Python functions and Pydantic AI agents, fan work
out over collections, persist artifacts, and inspect or run everything through
the bundled visualizer.

```python
from flow import Workflow, function

@function("inbox.search")
def search_inbox(hours: int = 18):
    return [{"subject": "Quarterly plan"}, {"subject": "Lunch"}]

workflow = Workflow.model_validate({
    "name": "morning-brief",
    "steps": [
        {
            "id": "emails",
            "type": "function",
            "uses": "inbox.search",
            "with": {"hours": 18},
        }
    ],
})
```

Or save the workflow as JSON/YAML and run:

```bash
flow validate examples/morning_brief.json
flow run examples/morning_brief.json
flow serve --workflows examples --import my_project.registrations
```

The visualizer is then available at `http://127.0.0.1:8000`.

## Principles

- Deterministic operations own searching, iteration, persistence, and retries.
- Agents are isolated to semantic tasks with typed inputs and outputs.
- Step outputs are immutable artifacts with lineage.
- Workflow definitions are validated before execution.
- Integrations are registered rather than embedded in workflow definitions.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,yaml,agents]"
pytest
```

Licensed under Apache 2.0.

## Finance intelligence demo

The Docker demo shows the central idea in two workflows:

1. Code collects a complete, bounded set of Reddit finance posts.
2. A typed agent turns each unstructured post into a new sentiment/topic row.
3. Code upserts those rows into a local SQLite dataset.
4. A second workflow retrieves matching rows deterministically.
5. Another agent writes a brief grounded only in those rows and cites post IDs.

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:8000`, run `reddit-finance-etl`, then run
`grounded-finance-brief`. The default uses realistic seed posts and a visible
deterministic agent fallback, so it works without credentials. Add
`OPENAI_API_KEY` to use the configured Pydantic AI model. Add Reddit OAuth
client credentials to collect live subreddit posts.

All generated data remains in the local `flow-data` Docker volume.
