"""Public Jev-to-Android SDK: observe, decide, execute, or run an agent."""

from __future__ import annotations

from typing import Literal, Self

from jevdroid.android.adb import AdbDevice
from jevdroid.android.device import AndroidDevice
from jevdroid.budget import Budget
from jevdroid.engine import INSTRUCTIONS, Agent
from jevdroid.errors import InvalidDecision, JevDroidError
from jevdroid.interfaces import Device, EventSink, Provider
from jevdroid.models import ActionKind, RunConfig, RunResult, Screen
from jevdroid.planning import PlannedAction, choose_action
from jevdroid.policy import Policy
from jevdroid.providers.http import JevProvider, ProviderName


class JevDroid:
    """Compose Jev with an Android device and explicitly enabled capabilities.

    `decide`/`act` share a lifetime budget and decision limit. Each `run` has its
    own budget. Only the latest pending decision can be executed, once. Instances
    are synchronous and not thread-safe. Only providers created by `connect`
    are closed by this object; injected dependencies belong to their caller.
    """

    def __init__(
        self,
        device: Device,
        provider: Provider,
        *,
        policy: Policy,
        config: RunConfig | None = None,
        on_event: EventSink | None = None,
    ) -> None:
        self.device = device
        self.provider = provider
        self.policy = policy
        self.config = config or RunConfig()
        self.on_event = on_event
        self.budget = Budget(self.config)
        self._pending: PlannedAction | None = None
        self._history: list[str] = []
        self._owned_provider: JevProvider | None = None
        self._closed = False

    @classmethod
    def connect(
        cls,
        *,
        api_key: str,
        packages: tuple[str, ...] = (),
        serial: str | None = None,
        backend: Literal["uiautomator", "adb"] = "uiautomator",
        provider: ProviderName = "vercel",
        policy: Policy | None = None,
        config: RunConfig | None = None,
        on_event: EventSink | None = None,
    ) -> Self:
        """Connect through ADB; use the persistent service by default for speed."""
        if backend not in {"uiautomator", "adb"}:
            raise ValueError("backend must be 'uiautomator' or 'adb'.")
        selected_policy = policy or Policy(packages)
        if packages and selected_policy.packages != packages:
            raise ValueError("Policy packages must match the requested packages.")
        device = AndroidDevice(serial) if backend == "uiautomator" else AdbDevice(serial)
        client = JevProvider(api_key, provider=provider)
        session = cls(device, client, policy=selected_policy, config=config, on_event=on_event)
        session._owned_provider = client
        return session

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._pending = None
        self._closed = True
        if self._owned_provider is not None:
            self._owned_provider.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise JevDroidError("JevDroid session is closed.")

    def observe(self) -> Screen:
        """Read Android's current accessibility state without calling Jev."""
        self._ensure_open()
        return self.device.snapshot(stable=self.policy.allow_taps)

    def decide(self, goal: str) -> PlannedAction:
        """Ask Jev to select an Android action; do not execute it yet."""
        self._ensure_open()
        self._pending = None
        if self.config.target_scrolls is not None:
            raise ValueError("Use run() for counted scrolling, or omit target_scrolls.")
        if self.budget.calls >= self.config.max_steps:
            raise JevDroidError("Session decision limit reached.")
        screen = self.observe()
        plan = choose_action(
            self.provider,
            screen=screen,
            actions=self.policy.actions(screen),
            goal=goal,
            instructions=INSTRUCTIONS,
            config=self.config,
            budget=self.budget,
            context={"recent_actions": self._history[-8:]},
        )
        self._pending = plan
        return plan

    def act(self, plan: PlannedAction) -> bool:
        """Execute the latest decision once. Return False if its screen is stale.

        DONE and STOP are terminal decisions and issue no device input. A failed
        or stale execution consumes the pending plan; decide again to continue.
        """
        self._ensure_open()
        if plan is not self._pending:
            raise InvalidDecision("Only this session's latest unconsumed decision may execute.")
        self._pending = None
        action, screen = plan.action, plan.screen
        if action not in self.policy.actions(screen):
            raise InvalidDecision("The action is no longer permitted by the current policy.")
        if action.kind in {ActionKind.DONE, ActionKind.STOP}:
            return False
        if action.kind in {
            ActionKind.TAP,
            ActionKind.SCROLL_DOWN,
            ActionKind.SCROLL_UP,
            ActionKind.BACK,
        }:
            fresh = self.device.snapshot(stable=action.kind == ActionKind.TAP)
            if fresh.package != screen.package or (
                action.kind == ActionKind.TAP and fresh != screen
            ):
                self._history.append(f"{action.id}: skipped because the screen changed")
                return False
            screen = fresh
        self.device.execute(action, screen)
        self._history.append(action.id)
        return True

    def run(self, goal: str) -> RunResult:
        """Let Jev operate Android in a bounded observe/decide/act loop."""
        self._ensure_open()
        self._pending = None
        return Agent(
            self.device,
            self.provider,
            policy=self.policy,
            config=self.config,
            on_event=self.on_event,
        ).run(goal)
