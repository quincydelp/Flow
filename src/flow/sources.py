from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Delta:
    records: list[Any]
    cursor: str | None


class Source(Protocol):
    async def get(self, identifier: str) -> Any: ...

    async def search(self, query: dict[str, Any]) -> list[Any]: ...

    async def delta(self, cursor: str | None = None) -> Delta: ...

