from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from dataclasses import asdict, is_dataclass
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from flow.artifacts import Artifact, ArtifactStore, FileArtifactStore, artifact_id
from flow.models import (
    AgentStep,
    FanoutStep,
    FunctionStep,
    SourceStep,
    Step,
    Workflow,
    referenced_steps,
)
from flow.refs import resolve
from flow.registry import Registry, registry


class StepResult(BaseModel):
    step_id: str
    status: str
    output: Any = None
    artifact_id: str | None = None
    duration_ms: float
    error: str | None = None


class RunResult(BaseModel):
    run_id: str
    workflow: str
    status: str
    outputs: dict[str, Any]
    steps: list[StepResult]
    duration_ms: float


class Runner:
    def __init__(
        self,
        *,
        registry_: Registry = registry,
        store: ArtifactStore | None = None,
    ) -> None:
        self.registry = registry_
        self.store = store or FileArtifactStore()

    async def run(
        self,
        workflow: Workflow,
        inputs: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
        on_event: Callable[[StepResult], Awaitable[None] | None] | None = None,
    ) -> RunResult:
        started = time.perf_counter()
        run_id = run_id or uuid.uuid4().hex[:12]
        workflow_inputs = {**workflow.inputs, **(inputs or {})}
        outputs: dict[str, Any] = {}
        results: list[StepResult] = []
        pending = {step.id: step for step in workflow.steps}

        while pending:
            ready = [
                step
                for step in pending.values()
                if self._dependencies(step) <= outputs.keys()
            ]
            if not ready:
                raise RuntimeError(f"unable to schedule steps: {sorted(pending)}")

            for step in ready:
                await self._emit(
                    on_event,
                    StepResult(step_id=step.id, status="running", duration_ms=0),
                )
            batch = await asyncio.gather(
                *(self._run_step(run_id, step, workflow_inputs, outputs) for step in ready),
                return_exceptions=True,
            )
            for step, result in zip(ready, batch, strict=True):
                pending.pop(step.id)
                if isinstance(result, BaseException):
                    failed = StepResult(
                        step_id=step.id,
                        status="failed",
                        duration_ms=0,
                        error=str(result),
                    )
                    results.append(failed)
                    await self._emit(on_event, failed)
                    return self._result(run_id, workflow, outputs, results, started, "failed")
                outputs[step.id] = result.output
                results.append(result)
                await self._emit(on_event, result)

        final = resolve(workflow.outputs, workflow_inputs, outputs) if workflow.outputs else outputs
        return self._result(run_id, workflow, final, results, started, "completed")

    @staticmethod
    async def _emit(
        callback: Callable[[StepResult], Awaitable[None] | None] | None,
        event: StepResult,
    ) -> None:
        if callback is None:
            return
        result = callback(event)
        if inspect.isawaitable(result):
            await result

    @staticmethod
    def _dependencies(step: Step) -> set[str]:
        return set(step.needs) | referenced_steps(step.model_dump(by_alias=True))

    async def _run_step(
        self,
        run_id: str,
        step: Step,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
    ) -> StepResult:
        started = time.perf_counter()
        if isinstance(step, FunctionStep):
            output = await self._function(step, inputs, outputs)
        elif isinstance(step, AgentStep):
            output = await self._agent(step, inputs, outputs)
        elif isinstance(step, SourceStep):
            output = await self._source(step, inputs, outputs)
        else:
            output = await self._fanout(step, inputs, outputs)

        artifact = Artifact(
            id=artifact_id(run_id, step.id, output),
            run_id=run_id,
            step_id=step.id,
            value=output,
        )
        await self.store.put(artifact)
        return StepResult(
            step_id=step.id,
            status="completed",
            output=output,
            artifact_id=artifact.id,
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    async def _function(
        self, step: FunctionStep, inputs: dict[str, Any], outputs: dict[str, Any]
    ) -> Any:
        try:
            function = self.registry.functions[step.uses]
        except KeyError as exc:
            raise ValueError(f"function {step.uses!r} is not registered") from exc
        arguments = resolve(step.inputs, inputs, outputs)
        result = function(**arguments)
        return await result if inspect.isawaitable(result) else result

    async def _agent(
        self, step: AgentStep, inputs: dict[str, Any], outputs: dict[str, Any]
    ) -> Any:
        try:
            agent = self.registry.agents[step.uses]
        except KeyError as exc:
            raise ValueError(f"agent {step.uses!r} is not registered") from exc
        prompt = resolve(step.prompt, inputs, outputs)
        kwargs = resolve(step.inputs, inputs, outputs)
        result = await agent.run(prompt, **kwargs)
        output = getattr(result, "output", getattr(result, "data", result))
        return output.model_dump(mode="json") if isinstance(output, BaseModel) else output

    async def _source(
        self, step: SourceStep, inputs: dict[str, Any], outputs: dict[str, Any]
    ) -> Any:
        try:
            source = self.registry.sources[step.uses]
        except KeyError as exc:
            raise ValueError(f"source {step.uses!r} is not registered") from exc
        arguments = resolve(step.inputs, inputs, outputs)
        method = getattr(source, step.action)
        result = method(**arguments)
        value = await result if inspect.isawaitable(result) else result
        return asdict(value) if is_dataclass(value) else value

    async def _fanout(
        self, step: FanoutStep, inputs: dict[str, Any], outputs: dict[str, Any]
    ) -> list[Any]:
        items = resolve(step.over, inputs, outputs)
        if not isinstance(items, list):
            raise TypeError(f"fanout {step.id} expected a list, got {type(items).__name__}")
        semaphore = asyncio.Semaphore(step.concurrency)

        async def run_one(item: Any, index: int) -> Any:
            scoped_inputs = {**inputs, "item": item, "index": index}
            async with semaphore:
                if isinstance(step.step, FunctionStep):
                    return await self._function(step.step, scoped_inputs, outputs)
                return await self._agent(step.step, scoped_inputs, outputs)

        return await asyncio.gather(*(run_one(item, index) for index, item in enumerate(items)))

    @staticmethod
    def _result(
        run_id: str,
        workflow: Workflow,
        outputs: dict[str, Any],
        steps: list[StepResult],
        started: float,
        status: str,
    ) -> RunResult:
        return RunResult(
            run_id=run_id,
            workflow=workflow.name,
            status=status,
            outputs=outputs,
            steps=steps,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
