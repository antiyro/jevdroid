"""Command-line entry point; credentials never travel in command arguments."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import statistics
import sys
import time
from contextlib import ExitStack
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from jevdroid import Agent, Policy, RunConfig, RunStatus, __version__
from jevdroid.android.device import AndroidDevice, devices
from jevdroid.demo import DemoDevice, DemoProvider
from jevdroid.errors import JevDroidError
from jevdroid.models import validate_package
from jevdroid.providers.http import JevProvider, ProviderName
from jevdroid.trace import JsonlTrace


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="jevdroid", description="Text-first Android agents powered by Jev."
    )
    root.add_argument("--version", action="version", version=f"JevDroid {__version__}")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check ADB and device authorization; no API calls")
    commands.add_parser("demo", help="Run a scripted simulation; no device, API key or charges")
    inspect = commands.add_parser("inspect", help="Print accessible UI text locally; no API calls")
    inspect.add_argument("--serial")
    benchmark = commands.add_parser("benchmark", help="Measure XML read latency; no API calls")
    benchmark.add_argument("--serial")
    benchmark.add_argument("--samples", type=int, default=10)
    for name, help_text in (
        ("run", "Run a bounded navigation task"),
        ("scroll", "Open an app and scroll a fixed number of times"),
    ):
        cmd = commands.add_parser(name, help=help_text)
        if name == "run":
            cmd.add_argument("goal")
            cmd.add_argument(
                "--allow-taps", action="store_true", help="Enable taps on non-checkable UI targets"
            )
            cmd.add_argument("--allow-back", action="store_true")
            cmd.add_argument(
                "--allow-checkable",
                action="store_true",
                help="Also permit tapping toggles (requires --allow-taps)",
            )
        else:
            cmd.add_argument("--count", type=int, default=5)
            cmd.add_argument("--pause", type=float, default=0.5)
        cmd.add_argument(
            "--package", required=True, help="Only this package may receive gestures or taps"
        )
        cmd.add_argument("--serial")
        cmd.add_argument("--provider", choices=["vercel", "typesafe"], default="vercel")
        cmd.add_argument("--model", help="Override the provider's default Jev model")
        cmd.add_argument("--max-steps", type=int, default=20)
        cmd.add_argument("--budget", default="0.10", help="Estimated USD ceiling (default: 0.10)")
        cmd.add_argument(
            "--input-price",
            default="0.042",
            help="USD per million input tokens for the local estimate",
        )
        cmd.add_argument("--trace", type=Path, help="Create a NEW metadata-only JSONL trace")
        cmd.add_argument("--json", action="store_true", help="Emit events and result as JSON lines")
    return root


def print_event(event: dict[str, Any]) -> None:
    if event["event"] == "decision":
        print(
            f"[{event['step']:02}] {event['action']:<14} "
            f"UI {event['ui_seconds']:.2f}s  Jev {event['api_seconds']:.2f}s  "
            f"~${Decimal(event['estimated_usd']):.6f}",
            flush=True,
        )
    elif event["event"] == "skipped":
        print("     Screen changed; action skipped.", flush=True)


def _main(argv: list[str] | None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    if args.command == "doctor":
        print(
            json.dumps({"adb_available": AndroidDevice.available(), "devices": devices()}, indent=2)
        )
        return 0
    if args.command == "demo":
        print("SIMULATION — scripted choices, no Jev inference, no device, no charges.")
        result = Agent(
            DemoDevice(),
            DemoProvider(),
            policy=Policy(("com.android.settings",), allow_taps=True),
            on_event=print_event,
        ).run("Open Display settings without changing anything.")
        print(json.dumps(result.as_dict(), indent=2))
        return 0 if result.status == RunStatus.MODEL_DONE else 2
    if args.command == "benchmark" and not 1 <= args.samples <= 100:
        cli.error("--samples must be between 1 and 100")
    if args.command in {"inspect", "benchmark"}:
        device = AndroidDevice(args.serial)
        if args.command == "inspect":
            print(json.dumps(device.snapshot().as_state(), indent=2, ensure_ascii=False))
        else:
            samples = []
            for _ in range(args.samples):
                tick = time.perf_counter()
                device.snapshot()
                samples.append(round((time.perf_counter() - tick) * 1000, 2))
            print(
                json.dumps(
                    {"samples_ms": samples, "median_ms": statistics.median(samples)}, indent=2
                )
            )
        return 0
    package = validate_package(args.package)
    is_scroll = args.command == "scroll"
    config = RunConfig(
        max_steps=args.max_steps,
        budget_usd=Decimal(args.budget),
        input_price_per_million=Decimal(args.input_price),
        target_scrolls=args.count if is_scroll else None,
        scroll_pause=args.pause if is_scroll else 0.5,
    )
    if not is_scroll and args.allow_checkable and not args.allow_taps:
        cli.error("--allow-checkable requires --allow-taps")
    policy = Policy(
        (package,),
        allow_taps=not is_scroll and args.allow_taps,
        allow_back=not is_scroll and args.allow_back,
        allow_checkable=not is_scroll and args.allow_checkable,
        allow_scroll_up=not is_scroll,
    )
    goal = (
        f"Open {package} and scroll through {args.count} feed items. "
        "Do not like, comment, follow or purchase anything."
        if is_scroll
        else args.goal
    )
    if not goal.strip() or len(goal) > 2000:
        cli.error("goal must contain 1–2000 characters")
    with ExitStack() as stack:
        trace = stack.enter_context(JsonlTrace(args.trace)) if args.trace else None
        device = AndroidDevice(args.serial)
        variable = "AI_GATEWAY_API_KEY" if args.provider == "vercel" else "TYPESAFE_API_KEY"
        key = os.environ.get(variable, "").strip()
        if not key:
            if not sys.stdin.isatty():
                raise JevDroidError(f"Set {variable}, or use a terminal for a hidden key prompt.")
            key = getpass.getpass(f"{args.provider} API key (hidden, not saved): ").strip()
        provider = stack.enter_context(
            JevProvider(key, provider=cast(ProviderName, args.provider), model=args.model)
        )
        del key

        def events(event: dict[str, Any]) -> None:
            if trace:
                trace(event)
            if args.json:
                print(json.dumps(event), flush=True)
            else:
                print_event(event)

        result = Agent(device, provider, policy=policy, config=config, on_event=events).run(goal)
        if not args.json:
            print(
                f"{result.status}: {result.message}\n"
                f"{result.actions} actions · {result.calls} calls · "
                f"{result.elapsed_seconds:.2f}s · ~${result.estimated_usd:.6f}"
            )
            if result.reserved_tokens:
                print(
                    "Usage not received: estimate includes an unresolved reservation, "
                    "not confirmed billing."
                )
        return 0 if result.status in {RunStatus.COMPLETED, RunStatus.MODEL_DONE} else 2


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (JevDroidError, ValueError, InvalidOperation) as exc:
        print(f"jevdroid: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print(
            "jevdroid: Local file or device access failed; check paths and permissions.",
            file=sys.stderr,
        )
        return 1
    except (KeyboardInterrupt, EOFError):
        print("jevdroid: Cancelled.", file=sys.stderr)
        return 130
