from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field


class Artifact(BaseModel):
    id: str
    run_id: str
    step_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    value: Any


class ArtifactStore(Protocol):
    async def put(self, artifact: Artifact) -> str: ...

    async def get(self, artifact_id: str) -> Artifact: ...


class FileArtifactStore:
    def __init__(self, root: str | Path = ".flow/artifacts") -> None:
        self.root = Path(root)

    async def put(self, artifact: Artifact) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{artifact.id}.json"
        path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        return artifact.id

    async def get(self, artifact_id: str) -> Artifact:
        path = self.root / f"{artifact_id}.json"
        return Artifact.model_validate_json(path.read_text(encoding="utf-8"))


def artifact_id(run_id: str, step_id: str, value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str).encode()
    digest = hashlib.sha256(payload).hexdigest()[:12]
    return f"{run_id}-{step_id}-{digest}"

