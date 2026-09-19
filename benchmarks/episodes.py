"""Stateful navigation evaluation, with optional read-only navigation on Android."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from jevdroid import Action, ActionKind, Element, JevDroid, Policy, RunConfig, Screen
from jevdroid.android import AndroidDevice
from jevdroid.errors import DeviceError, JevDroidError, ProviderError
from jevdroid.providers import JevProvider

PACKAGE = "org.jevdroid.fixture"


class SimulatedAndroid:
    """Small explicit transition graph; no API or physical device side effects."""

    def __init__(self, episode: dict[str, Any]) -> None:
        self.episode = episode
        self.node = episode["start"]
        self.stack: list[str] = []

    def snapshot(self, *, stable: bool = False) -> Screen:
        node = self.episode["nodes"][self.node]
        return Screen(
            node.get("package", PACKAGE),
            tuple(node["text"]),
            tuple(
                Element(i, label, (0, 100 + i * 150, 1000, 230 + i * 150))
                for i, label in enumerate(node["labels"])
            ),
        )

    def execute(self, action: Action, screen: Screen) -> None:
        if screen != self.snapshot():
            raise DeviceError("Stale simulated screen")
        if action.kind == ActionKind.TAP:
            if action.element is None or action.element not in screen.elements:
                raise DeviceError("Invalid simulated target")
            target = self.episode["nodes"][self.node].get("on_tap", {}).get(str(action.element.id))
            if target is None:
                raise DeviceError("No transition for the selected simulated target")
            self.stack.append(self.node)
            self.node = target
        elif action.kind == ActionKind.LAUNCH:
            self.stack.clear()
            self.node = self.episode["launch"]
        elif action.kind == ActionKind.BACK:
            if self.stack:
                self.node = self.stack.pop()
        elif action.kind not in {ActionKind.WAIT, ActionKind.SCROLL_DOWN, ActionKind.SCROLL_UP}:
            raise DeviceError("Unsupported simulated action")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path("benchmarks/episodes.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=15.5)
    phone_options = parser.add_mutually_exclusive_group()
    phone_options.add_argument(
        "--phone",
        action="store_true",
        help="Also navigate to display controls on a connected phone",
    )
    phone_options.add_argument(
        "--only-phone", action="store_true", help="Run only the connected-phone navigation trial"
    )
    args = parser.parse_args()
    if not 0 <= args.interval <= 120:
        parser.error("--interval must be between 0 and 120 seconds")
    if args.output.exists():
        parser.error("Output already exists")
    raw = args.suite.read_bytes()
    suite = json.loads(raw)
    report: dict[str, Any] = {
        "suite": suite["name"],
        "suite_sha256": hashlib.sha256(raw).hexdigest(),
        "started_at": datetime.now(UTC).isoformat(),
        "interval_seconds": args.interval,
        "episodes": [],
        "status": "running",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    key = os.environ.get("AI_GATEWAY_API_KEY") or getpass.getpass("Vercel API key (hidden): ")
    # Leave space after the preceding decision campaign as well as within this one.
    next_request = time.monotonic() + args.interval
    scenarios = [] if args.only_phone else list(suite["episodes"])
    if args.phone or args.only_phone:
        scenarios.append(
            {
                "id": "physical-display-navigation",
                "physical": True,
                "goal": (
                    "Open the page for adjusting display brightness. Do not change brightness "
                    "or any setting. Finish only when brightness controls are visible."
                ),
            }
        )
    droid = None
    try:
        with JevProvider(key) as provider:
            del key
            for scenario in scenarios:
                droid = None
                physical = scenario.get("physical", False)
                episode: dict[str, Any] = {
                    "id": scenario["id"],
                    "kind": "physical_android" if physical else "stateful_simulation",
                    "steps": [],
                    "success": False,
                    "status": "step_limit",
                }
                report["episodes"].append(episode)
                device = AndroidDevice() if physical else SimulatedAndroid(scenario)
                package = "com.android.settings" if physical else PACKAGE
                droid = JevDroid(
                    device,
                    provider,
                    policy=Policy(
                        (package,), allow_taps=True, allow_back=True, allow_scroll_up=True
                    ),
                    config=RunConfig(max_steps=8, budget_usd=Decimal("0.01")),
                )
                for step in range(1, 9):
                    time.sleep(max(0, next_request - time.monotonic()))
                    next_request = time.monotonic() + args.interval
                    start = time.perf_counter()
                    plan = droid.decide(scenario["goal"])
                    decision_end = time.perf_counter()
                    kind = plan.action.kind
                    if physical:
                        evidence = plan.screen.package == package and any(
                            "brightness" in t.lower() or "luminosité" in t.lower()
                            for t in plan.screen.text
                        )
                    else:
                        evidence = device.node == scenario["success"]
                    terminal = kind in {ActionKind.DONE, ActionKind.STOP}
                    executed = droid.act(plan) if not terminal else False
                    end = time.perf_counter()
                    record = {
                        "step": step,
                        "action": plan.action.id,
                        "executed": executed,
                        "api_seconds": round(plan.api_seconds, 6),
                        "observation_and_decision_seconds": round(decision_end - start, 6),
                        "validation_and_execution_seconds": round(end - decision_end, 6),
                        "input_tokens": plan.decision.input_tokens,
                        "expected_screen_evidence": evidence,
                    }
                    if not physical:
                        record["resulting_node"] = device.node
                    episode["steps"].append(record)
                    episode["estimated_usd"] = str(droid.budget.estimated_usd)
                    episode["reserved_tokens"] = droid.budget.reserved
                    print(
                        f"{scenario['id']} [{step}/8]: {plan.action.id} "
                        f"API={plan.api_seconds:.3f}s evidence={evidence}",
                        flush=True,
                    )
                    if terminal:
                        episode["success"] = kind == ActionKind.DONE and evidence
                        episode["status"] = (
                            "success" if episode["success"] else "incorrect_terminal"
                        )
                        save()
                        break
                    if not physical and device.node in scenario.get("forbidden", []):
                        episode["status"] = "forbidden_transition"
                        save()
                        break
                    save()
            report["status"] = "complete"
    except (JevDroidError, KeyboardInterrupt) as error:
        report["status"] = (
            "cancelled" if isinstance(error, KeyboardInterrupt) else "stopped_on_error"
        )
        report["error_type"] = type(error).__name__
        report["http_status"] = error.status if isinstance(error, ProviderError) else None
        if report["episodes"]:
            report["episodes"][-1]["status"] = (
                "cancelled" if isinstance(error, KeyboardInterrupt) else "error"
            )
        if report["episodes"] and droid is not None:
            report["episodes"][-1]["estimated_usd"] = str(droid.budget.estimated_usd)
            report["episodes"][-1]["reserved_tokens"] = droid.budget.reserved
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        save()
    print(
        json.dumps(
            {
                "status": report["status"],
                "outcomes": [
                    {"id": e["id"], "success": e["success"], "status": e["status"]}
                    for e in report["episodes"]
                ],
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
