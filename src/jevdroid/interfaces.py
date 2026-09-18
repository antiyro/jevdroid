"""Implement these protocols to bring another device or decision provider."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from jevdroid.models import Action, Decision, Screen


class Device(Protocol):
    def snapshot(self, *, stable: bool = False) -> Screen: ...

    def execute(self, action: Action, screen: Screen) -> None: ...


class Provider(Protocol):
    def decide(
        self, state: Mapping[str, Any], actions: Sequence[Action], instructions: str
    ) -> Decision: ...


class EventSink(Protocol):
    def __call__(self, event: dict[str, Any]) -> None: ...
