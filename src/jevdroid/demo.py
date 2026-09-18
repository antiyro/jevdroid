"""Deterministic simulation for trying the framework without hardware or API."""

from collections.abc import Mapping, Sequence
from typing import Any

from jevdroid.models import Action, ActionKind, Decision, Element, Screen


class DemoDevice:
    def __init__(self) -> None:
        self.opened = False
        self.display = False

    def snapshot(self, *, stable: bool = False) -> Screen:
        if not self.opened:
            return Screen("demo.launcher", ("Home",))
        if self.display:
            return Screen("com.android.settings", ("Display", "Brightness"))
        return Screen(
            "com.android.settings",
            ("Settings", "Display"),
            (Element(0, "Display", (0, 100, 400, 200)),),
        )

    def execute(self, action: Action, screen: Screen) -> None:
        if action.kind == ActionKind.LAUNCH:
            self.opened = True
        elif action.kind == ActionKind.TAP:
            self.display = True


class DemoProvider:
    """Scripted decisions, not a Jev inference or an intelligence benchmark."""

    def decide(
        self, state: Mapping[str, Any], actions: Sequence[Action], instructions: str
    ) -> Decision:
        ids = {a.id for a in actions}
        selected = "LAUNCH_0" if "LAUNCH_0" in ids else "TAP_0" if "TAP_0" in ids else "DONE"
        return Decision(selected, 0, "simulation")
