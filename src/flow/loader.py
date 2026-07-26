from __future__ import annotations

import json
from pathlib import Path

from flow.models import Workflow


def load_workflow(path: str | Path) -> Workflow:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("YAML support requires: pip install declarative-flow[yaml]") from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return Workflow.model_validate(data)


def save_workflow(path: str | Path, workflow: Workflow) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(workflow.model_dump_json(indent=2, by_alias=True), encoding="utf-8")

