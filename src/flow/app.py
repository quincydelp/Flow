from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from flow.loader import load_workflow, save_workflow
from flow.models import Workflow
from flow.runner import Runner, StepResult


class ExecuteRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


def create_app(workflow_dir: str | Path = "workflows", runner: Runner | None = None) -> FastAPI:
    directory = Path(workflow_dir)
    executor = runner or Runner()
    web = Path(__file__).parent / "web"
    app = FastAPI(title="Flow", version="0.1.0")
    runs: dict[str, dict[str, Any]] = {}

    def workflow_path(name: str) -> Path:
        if not name.replace("-", "").replace("_", "").isalnum():
            raise HTTPException(400, "invalid workflow name")
        candidates = [
            directory / f"{name}.json",
            directory / f"{name}.yaml",
            directory / f"{name}.yml",
        ]
        found = next((path for path in candidates if path.exists()), candidates[0])
        return found

    @app.get("/api/workflows")
    async def list_workflows() -> list[dict[str, Any]]:
        directory.mkdir(parents=True, exist_ok=True)
        entries = []
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
                continue
            try:
                workflow = load_workflow(path)
                entries.append(
                    {
                        "name": workflow.name,
                        "description": workflow.description,
                        "steps": len(workflow.steps),
                        "valid": True,
                    }
                )
            except Exception as exc:
                entries.append({"name": path.stem, "valid": False, "error": str(exc)})
        return entries

    @app.get("/api/workflows/{name}")
    async def get_workflow(name: str) -> dict[str, Any]:
        path = workflow_path(name)
        if not path.exists():
            raise HTTPException(404, "workflow not found")
        return load_workflow(path).model_dump(by_alias=True)

    @app.put("/api/workflows/{name}")
    async def put_workflow(name: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            workflow = Workflow.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(422, exc.errors()) from exc
        if workflow.name != name:
            raise HTTPException(400, "path and workflow name must match")
        save_workflow(workflow_path(name), workflow)
        return workflow.model_dump(by_alias=True)

    @app.post("/api/workflows/{name}/execute")
    async def execute_workflow(name: str, request: ExecuteRequest) -> dict[str, Any]:
        path = workflow_path(name)
        if not path.exists():
            raise HTTPException(404, "workflow not found")
        result = await executor.run(load_workflow(path), request.inputs)
        return result.model_dump(mode="json")

    @app.post("/api/workflows/{name}/runs", status_code=202)
    async def start_workflow(name: str, request: ExecuteRequest) -> dict[str, Any]:
        path = workflow_path(name)
        if not path.exists():
            raise HTTPException(404, "workflow not found")
        workflow = load_workflow(path)
        run_id = uuid.uuid4().hex[:12]
        started = time.time()
        runs[run_id] = {
            "run_id": run_id,
            "workflow": workflow.name,
            "status": "running",
            "started_at": started,
            "duration_ms": 0,
            "steps": [
                {"step_id": step.id, "status": "pending", "duration_ms": 0}
                for step in workflow.steps
            ],
            "outputs": {},
        }

        async def on_event(event: StepResult) -> None:
            snapshot = runs[run_id]
            for index, step in enumerate(snapshot["steps"]):
                if step["step_id"] == event.step_id:
                    snapshot["steps"][index] = event.model_dump(mode="json")
                    break
            snapshot["duration_ms"] = (time.time() - started) * 1000

        async def execute() -> None:
            try:
                result = await executor.run(
                    workflow,
                    request.inputs,
                    run_id=run_id,
                    on_event=on_event,
                )
                runs[run_id] = {
                    **result.model_dump(mode="json"),
                    "started_at": started,
                }
            except Exception as exc:
                runs[run_id].update(
                    status="failed",
                    error=str(exc),
                    duration_ms=(time.time() - started) * 1000,
                )

        asyncio.create_task(execute())
        return runs[run_id]

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        try:
            snapshot = runs[run_id]
        except KeyError as exc:
            raise HTTPException(404, "run not found") from exc
        if snapshot["status"] == "running":
            snapshot["duration_ms"] = (time.time() - snapshot["started_at"]) * 1000
        return snapshot

    @app.post("/api/validate")
    async def validate_workflow(body: dict[str, Any]) -> dict[str, Any]:
        try:
            workflow = Workflow.model_validate(body)
        except ValidationError as exc:
            return {"valid": False, "errors": exc.errors()}
        return {"valid": True, "workflow": workflow.model_dump(by_alias=True)}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(web / "index.html")

    @app.get("/app.js")
    async def javascript() -> FileResponse:
        return FileResponse(web / "app.js", media_type="text/javascript")

    @app.get("/styles.css")
    async def stylesheet() -> FileResponse:
        return FileResponse(web / "styles.css", media_type="text/css")

    return app
