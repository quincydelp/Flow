from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

STEP_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class StepBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    description: str | None = None
    needs: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict, alias="with")
    persist: list[str] = Field(default_factory=list)


class FunctionStep(StepBase):
    type: Literal["function"]
    uses: str


class AgentStep(StepBase):
    type: Literal["agent"]
    uses: str
    prompt: Any


class SourceStep(StepBase):
    type: Literal["source"]
    uses: str
    action: Literal["get", "search", "delta"]


class FanoutStep(StepBase):
    type: Literal["fanout"]
    over: Any
    step: FunctionStep | AgentStep
    concurrency: int = Field(default=10, ge=1, le=1000)


Step = Annotated[FunctionStep | AgentStep | SourceStep | FanoutStep, Field(discriminator="type")]


class Workflow(BaseModel):
    name: str
    description: str | None = None
    version: str = "1"
    inputs: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step]
    outputs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph(self) -> Workflow:
        ids: set[str] = set()
        for step in self.steps:
            if not STEP_ID.match(step.id):
                raise ValueError(f"invalid step id: {step.id!r}")
            if step.id in ids:
                raise ValueError(f"duplicate step id: {step.id}")
            ids.add(step.id)

        known: set[str] = set()
        for step in self.steps:
            missing = set(step.needs) - ids
            if missing:
                raise ValueError(f"step {step.id} needs unknown steps: {sorted(missing)}")
            inferred = referenced_steps(step.model_dump(by_alias=True))
            unknown = inferred - ids
            if unknown:
                raise ValueError(f"step {step.id} references unknown steps: {sorted(unknown)}")
            known.add(step.id)

        graph = {
            step.id: set(step.needs) | referenced_steps(step.model_dump(by_alias=True))
            for step in self.steps
        }
        visit_graph(graph)
        return self


def referenced_steps(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, str):
        pattern = r"\$\{steps\.([A-Za-z][A-Za-z0-9_-]*)\.output(?:\.[^}]*)?\}"
        for match in re.finditer(pattern, value):
            refs.add(match.group(1))
    elif isinstance(value, dict):
        for child in value.values():
            refs |= referenced_steps(child)
    elif isinstance(value, list):
        for child in value:
            refs |= referenced_steps(child)
    return refs


def visit_graph(graph: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f"workflow contains a cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
