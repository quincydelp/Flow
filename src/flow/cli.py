from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
from typing import Annotated

import typer

from flow.app import create_app
from flow.loader import load_workflow
from flow.runner import Runner

app = typer.Typer(no_args_is_help=True, help="Define, run, and visualize Flow workflows.")


def import_registrations(modules: list[str]) -> None:
    for module in modules:
        importlib.import_module(module)


@app.command()
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    workflow = load_workflow(path)
    typer.echo(f"✓ {workflow.name}: {len(workflow.steps)} steps, valid DAG")


@app.command()
def run(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    inputs: Annotated[str, typer.Option("--inputs", "-i")] = "{}",
    imports: Annotated[list[str] | None, typer.Option("--import")] = None,
) -> None:
    import_registrations(imports or [])
    workflow = load_workflow(path)
    result = asyncio.run(Runner().run(workflow, json.loads(inputs)))
    typer.echo(result.model_dump_json(indent=2))
    if result.status != "completed":
        raise typer.Exit(1)


@app.command()
def serve(
    workflows: Annotated[Path, typer.Option("--workflows", "-w")] = Path("workflows"),
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    imports: Annotated[list[str] | None, typer.Option("--import")] = None,
) -> None:
    import uvicorn

    import_registrations(imports or [])
    typer.echo(f"Flow visualizer: http://{host}:{port}")
    uvicorn.run(create_app(workflows), host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
