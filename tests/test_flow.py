from __future__ import annotations

from fastapi.testclient import TestClient

from flow.app import create_app
from flow.loader import load_workflow
from flow.models import Workflow
from flow.registry import Registry
from flow.runner import Runner
from flow.sources import Delta


async def test_function_dag_and_refs(tmp_path):
    registry = Registry()
    registry.register_function("numbers", lambda count: list(range(count)))
    registry.register_function("total", lambda values: sum(values))
    workflow = Workflow.model_validate(
        {
            "name": "sum",
            "inputs": {"count": 4},
            "steps": [
                {
                    "id": "numbers",
                    "type": "function",
                    "uses": "numbers",
                    "with": {"count": "${inputs.count}"},
                },
                {
                    "id": "total",
                    "type": "function",
                    "uses": "total",
                    "with": {"values": "${steps.numbers.output}"},
                },
            ],
            "outputs": {"total": "${steps.total.output}"},
        }
    )
    result = await Runner(registry_=registry).run(workflow)
    assert result.status == "completed"
    assert result.outputs == {"total": 6}


async def test_fanout(tmp_path):
    registry = Registry()
    registry.register_function("double", lambda value: value * 2)
    workflow = Workflow.model_validate(
        {
            "name": "fan",
            "inputs": {"items": [1, 2, 3]},
            "steps": [
                {
                    "id": "double",
                    "type": "fanout",
                    "over": "${inputs.items}",
                    "step": {
                        "id": "one",
                        "type": "function",
                        "uses": "double",
                        "with": {"value": "${inputs.item}"},
                    },
                }
            ],
        }
    )
    result = await Runner(registry_=registry).run(workflow)
    assert result.outputs["double"] == [2, 4, 6]


async def test_source_delta():
    class Feed:
        async def delta(self, cursor=None):
            return Delta(records=[{"id": "new"}], cursor="next")

    registry = Registry()
    registry.register_source("feed", Feed())
    workflow = Workflow.model_validate(
        {
            "name": "sync",
            "steps": [
                {
                    "id": "changes",
                    "type": "source",
                    "uses": "feed",
                    "action": "delta",
                    "with": {"cursor": None},
                }
            ],
        }
    )
    result = await Runner(registry_=registry).run(workflow)
    assert result.outputs["changes"]["cursor"] == "next"


def test_cycle_is_rejected():
    try:
        Workflow.model_validate(
            {
                "name": "cycle",
                "steps": [
                    {"id": "a", "type": "function", "uses": "x", "needs": ["b"]},
                    {"id": "b", "type": "function", "uses": "x", "needs": ["a"]},
                ],
            }
        )
    except ValueError as exc:
        assert "cycle" in str(exc)
    else:
        raise AssertionError("cycle should fail validation")


def test_visualizer_and_workflow_api(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/").status_code == 200
    assert "Flow Studio" in client.get("/").text

    workflow = {
        "name": "hello",
        "description": "A test workflow",
        "steps": [{"id": "say", "type": "function", "uses": "say"}],
    }
    saved = client.put("/api/workflows/hello", json=workflow)
    assert saved.status_code == 200
    assert client.get("/api/workflows").json()[0]["name"] == "hello"
    assert client.post("/api/validate", json=workflow).json()["valid"] is True


async def test_finance_demo_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FLOW_SOCIAL_MODE", "seed")
    import finance_demo.registrations  # noqa: F401

    etl = await Runner().run(load_workflow("workflows/social-finance-etl.json"))
    assert etl.status == "completed"
    assert etl.outputs["load"]["rows_written"] > 0

    brief = await Runner().run(load_workflow("workflows/grounded-finance-brief.json"))
    assert brief.status == "completed"
    assert brief.outputs["brief"]["cited_post_ids"]
