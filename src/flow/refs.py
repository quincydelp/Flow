from __future__ import annotations

import re
from typing import Any

FULL_REF = re.compile(r"^\$\{(inputs|steps)\.([^}]+)\}$")
INLINE_REF = re.compile(r"\$\{(inputs|steps)\.([^}]+)\}")


def resolve(value: Any, inputs: dict[str, Any], outputs: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: resolve(child, inputs, outputs) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve(child, inputs, outputs) for child in value]
    if not isinstance(value, str):
        return value

    full = FULL_REF.match(value)
    if full:
        return lookup(full.group(1), full.group(2), inputs, outputs)

    return INLINE_REF.sub(
        lambda match: str(lookup(match.group(1), match.group(2), inputs, outputs)),
        value,
    )


def lookup(root: str, path: str, inputs: dict[str, Any], outputs: dict[str, Any]) -> Any:
    parts = path.split(".")
    if root == "steps":
        if len(parts) < 2 or parts[1] != "output":
            raise ValueError(f"step reference must include .output: {path}")
        value: Any = outputs[parts[0]]
        parts = parts[2:]
    else:
        value = inputs

    for part in parts:
        if isinstance(value, dict):
            value = value[part]
        elif isinstance(value, list) and part.isdigit():
            value = value[int(part)]
        else:
            value = getattr(value, part)
    return value

