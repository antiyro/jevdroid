"""A reusable Jev decision primitive, independent of the agent loop."""

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jevdroid.budget import Budget
from jevdroid.errors import InvalidDecision, JevDroidError
from jevdroid.interfaces import Provider
from jevdroid.models import Action, Decision, RunConfig, Screen


@dataclass(frozen=True)
class PlannedAction:
    """A model-selected host action tied to the observation it was based on."""

    action: Action
    screen: Screen
    decision: Decision
    api_seconds: float = 0


def choose_action(
    provider: Provider,
    *,
    screen: Screen,
    actions: Sequence[Action],
    goal: str,
    instructions: str,
    config: RunConfig,
    budget: Budget,
    context: Mapping[str, Any] | None = None,
) -> PlannedAction:
    """Reserve cost, request a typed choice, and reject unsupported action IDs."""
    if not goal.strip() or len(goal) > 2000:
        raise ValueError("Goal must contain 1–2000 characters.")
    if not actions or len({a.id for a in actions}) != len(actions):
        raise ValueError("Actions must be nonempty and have unique IDs.")
    state = {**(context or {}), "screen": screen.as_state(), "user_goal": goal}
    payload_size = len(
        json.dumps(
            {
                "state": state,
                "instructions": instructions,
                "choices": {a.id: a.description for a in actions},
            }
        ).encode()
    )
    if payload_size > config.max_payload_bytes:
        raise JevDroidError("Screen exceeds the configured inference payload limit.")
    budget.reserve()
    started = time.perf_counter()
    decision = provider.decide(state, actions, instructions)
    api_seconds = time.perf_counter() - started
    budget.settle(decision.input_tokens)
    action = next((a for a in actions if a.id == decision.action_id), None)
    if action is None:
        raise InvalidDecision("Provider chose an action outside the available choices.")
    return PlannedAction(action, screen, decision, api_seconds)
