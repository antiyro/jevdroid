"""Immutable values shared by devices, policies, and providers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any


class ActionKind(StrEnum):
    TAP = "tap"
    SCROLL_DOWN = "scroll_down"
    SCROLL_UP = "scroll_up"
    LAUNCH = "launch"
    BACK = "back"
    WAIT = "wait"
    DONE = "done"
    STOP = "stop"


@dataclass(frozen=True)
class Element:
    id: int
    label: str
    bounds: tuple[int, int, int, int]
    resource_id: str = ""
    checkable: bool = False


@dataclass(frozen=True)
class Screen:
    package: str
    text: tuple[str, ...] = ()
    elements: tuple[Element, ...] = ()
    rotation: int = 0

    def as_state(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.as_state(), sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Action:
    id: str
    kind: ActionKind
    description: str
    element: Element | None = None
    package: str | None = None


@dataclass(frozen=True)
class Decision:
    action_id: str
    input_tokens: int
    model: str
    confidence: float | None = None


@dataclass(frozen=True)
class RunConfig:
    max_steps: int = 20
    budget_usd: Decimal = Decimal("0.10")
    input_price_per_million: Decimal = Decimal("0.042")
    max_request_tokens: int = 65_536
    max_payload_bytes: int = 28_000
    max_repeats: int = 3
    target_scrolls: int | None = None
    scroll_pause: float = 0.5

    def __post_init__(self) -> None:
        for name, value, lower, upper in (
            ("max_steps", self.max_steps, 1, 1000),
            ("max_request_tokens", self.max_request_tokens, 1, 65_536),
            ("max_payload_bytes", self.max_payload_bytes, 1, 100_000),
            ("max_repeats", self.max_repeats, 1, 100),
        ):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{name} must be an integer in [{lower}, {upper}].")
        for name in ("budget_usd", "input_price_per_million"):
            amount = Decimal(str(getattr(self, name)))
            if not amount.is_finite() or amount <= 0:
                raise ValueError(f"{name} must be finite and positive.")
            object.__setattr__(self, name, amount)
        if self.target_scrolls is not None and (
            type(self.target_scrolls) is not int or not 1 <= self.target_scrolls <= self.max_steps
        ):
            raise ValueError("target_scrolls must be between 1 and max_steps.")
        if not math.isfinite(self.scroll_pause) or not 0 <= self.scroll_pause <= 60:
            raise ValueError("scroll_pause must be between 0 and 60 seconds.")


class RunStatus(StrEnum):
    COMPLETED = "completed"
    MODEL_DONE = "model_done"
    STOPPED = "stopped"
    STEP_LIMIT = "step_limit"
    REPEATED = "repeated"
    BUDGET_LIMIT = "budget_limit"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    calls: int
    actions: int
    scrolls: int
    input_tokens: int
    estimated_usd: Decimal
    reserved_tokens: int
    elapsed_seconds: float
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "status": self.status.value,
            "estimated_usd": str(self.estimated_usd),
        }


def validate_package(package: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+", package):
        raise ValueError("Expected an Android package name, e.g. com.android.settings.")
    return package
