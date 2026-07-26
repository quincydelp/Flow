from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T", bound=Callable[..., Any])


@dataclass
class Registry:
    functions: dict[str, Callable[..., Any]] = field(default_factory=dict)
    agents: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, Any] = field(default_factory=dict)

    def register_function(self, name: str, value: Callable[..., Any]) -> None:
        self._add(self.functions, name, value)

    def register_agent(self, name: str, value: Any) -> None:
        self._add(self.agents, name, value)

    def register_source(self, name: str, value: Any) -> None:
        self._add(self.sources, name, value)

    @staticmethod
    def _add(target: dict[str, Any], name: str, value: Any) -> None:
        if name in target:
            raise ValueError(f"{name!r} is already registered")
        target[name] = value


registry = Registry()


def function(name: str) -> Callable[[T], T]:
    def decorate(value: T) -> T:
        registry.register_function(name, value)
        return value

    return decorate


def agent(name: str) -> Callable[[T], T]:
    def decorate(value: T) -> T:
        registry.register_agent(name, value)
        return value

    return decorate


def source(name: str) -> Callable[[T], T]:
    def decorate(value: T) -> T:
        registry.register_source(name, value)
        return value

    return decorate

