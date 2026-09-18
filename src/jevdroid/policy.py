"""Action capabilities are selected by the host, never expanded by the model."""

from dataclasses import dataclass

from jevdroid.models import Action, ActionKind, Screen, validate_package


@dataclass(frozen=True)
class Policy:
    packages: tuple[str, ...]
    allow_taps: bool = False
    allow_back: bool = False
    allow_checkable: bool = False
    allow_scroll_up: bool = False

    def __post_init__(self) -> None:
        if not self.packages:
            raise ValueError("At least one allowed package is required.")
        for package in self.packages:
            validate_package(package)

    def actions(self, screen: Screen, *, scroll_only: bool = False) -> tuple[Action, ...]:
        actions = [
            Action("WAIT", ActionKind.WAIT, "Wait briefly for a loading screen"),
            Action("STOP", ActionKind.STOP, "Stop if blocked or no appropriate action exists"),
        ]
        if not scroll_only:
            actions.append(Action("DONE", ActionKind.DONE, "Goal already evidenced on this screen"))
        if screen.package in self.packages:
            actions.append(Action("SCROLL_DOWN", ActionKind.SCROLL_DOWN, "Swipe up to scroll down"))
            if self.allow_scroll_up and not scroll_only:
                actions.append(Action("SCROLL_UP", ActionKind.SCROLL_UP, "Swipe down to scroll up"))
            if self.allow_back and not scroll_only:
                actions.append(Action("BACK", ActionKind.BACK, "Press Android back"))
            if self.allow_taps and not scroll_only:
                actions.extend(
                    Action(f"TAP_{e.id}", ActionKind.TAP, f"Tap {e.label}", element=e)
                    for e in screen.elements
                    if self.allow_checkable or not e.checkable
                )
        for index, package in enumerate(self.packages):
            if package != screen.package:
                actions.append(
                    Action(f"LAUNCH_{index}", ActionKind.LAUNCH, f"Open {package}", package=package)
                )
        return tuple(actions)
