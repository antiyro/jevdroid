"""Evaluate fixed synthetic Android decisions with reordered UI variants."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import random
import statistics
import time
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from jevdroid import Element, Policy, RunConfig, Screen
from jevdroid.budget import Budget
from jevdroid.engine import INSTRUCTIONS
from jevdroid.errors import JevDroidError, ProviderError
from jevdroid.interfaces import Provider
from jevdroid.planning import choose_action
from jevdroid.providers import JevProvider

PACKAGE = "org.jevdroid.fixture"


def presentation(case: dict[str, Any], variant: int, seed: int) -> tuple[Screen, str, list[int]]:
    order = list(range(len(case["labels"])))
    if variant:
        # Rotate a shuffled permutation if it accidentally equals the original.
        random.Random(f"{seed}:{case['id']}:{variant}").shuffle(order)
        if len(order) > 1 and order == list(range(len(order))):
            order = order[1:] + order[:1]
    elements = tuple(
        Element(i, case["labels"][old], (0, 100 + i * 150, 1000, 230 + i * 150))
        for i, old in enumerate(order)
    )
    expected = case["expected"]
    if expected.startswith("TAP_"):
        expected = f"TAP_{order.index(int(expected.removeprefix('TAP_')))}"
    screen = Screen(PACKAGE, tuple(case["text"]), elements)
    return screen, expected, order


def summarize(records: list[dict[str, Any]], planned: int) -> dict[str, Any]:
    answered = [r for r in records if "correct" in r]
    categories: dict[str, list[bool]] = defaultdict(list)
    pairs: dict[str, list[bool]] = defaultdict(list)
    for record in answered:
        categories[record["category"]].append(record["correct"])
        pairs[record["case_id"]].append(record["correct"])
    latencies = [r["api_seconds"] for r in answered]
    costs = [Decimal(r["estimated_usd"]) for r in answered]
    return {
        "planned_decisions": planned,
        "attempted": len(records),
        "answered": len(answered),
        "correct": sum(r["correct"] for r in answered),
        "accuracy": sum(r["correct"] for r in answered) / len(answered) if answered else None,
        "coverage": len(answered) / planned,
        "errors": len(records) - len(answered),
        "median_api_seconds": statistics.median(latencies) if latencies else None,
        "p95_api_seconds": statistics.quantiles(latencies, n=100, method="inclusive")[94]
        if len(latencies) >= 2
        else None,
        "mean_cost_per_answer_usd": str(sum(costs) / len(costs)) if costs else None,
        "categories": {
            k: {"correct": sum(v), "answered": len(v)} for k, v in sorted(categories.items())
        },
        "both_presentations_correct": sum(len(v) == 2 and all(v) for v in pairs.values()),
        "fully_evaluated_pairs": sum(len(v) == 2 for v in pairs.values()),
    }


def evaluate_one(
    provider: Provider,
    case: dict[str, Any],
    variant: int,
    seed: int,
    config: RunConfig,
    budget: Budget,
) -> dict[str, Any]:
    screen, expected, order = presentation(case, variant, seed)
    actions = list(Policy((PACKAGE,), allow_taps=True, allow_back=True).actions(screen))
    if variant:
        random.Random(f"{seed}:{case['id']}:actions").shuffle(actions)
    # Expected answers, IDs and categories never enter the provider's state.
    plan = choose_action(
        provider,
        screen=screen,
        actions=actions,
        goal=case["goal"],
        instructions=INSTRUCTIONS,
        config=config,
        budget=budget,
        context={"recent_actions": case.get("history", [])},
    )
    return {
        "case_id": case["id"],
        "category": case["category"],
        "variant": variant,
        "display_order": order,
        "expected": expected,
        "actual": plan.action.id,
        "correct": plan.action.id == expected,
        "api_seconds": round(plan.api_seconds, 6),
        "input_tokens": plan.decision.input_tokens,
        "model": plan.decision.model,
        "estimated_usd": str(
            Decimal(plan.decision.input_tokens) * config.input_price_per_million / 1_000_000
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path("benchmarks/decisions.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--interval", type=float, default=15.5, help="Minimum seconds between request starts"
    )
    parser.add_argument("--budget", default="0.05")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--resume-from", type=Path, help="Preserve previous results and run unanswered trials only"
    )
    parser.add_argument(
        "--check", action="store_true", help="Validate cases without calling the API"
    )
    args = parser.parse_args()
    if not 0 <= args.interval <= 120:
        parser.error("--interval must be between 0 and 120 seconds")
    raw = args.suite.read_bytes()
    suite = json.loads(raw)
    ids = [c["id"] for c in suite["cases"]]
    if len(ids) != len(set(ids)):
        parser.error("Case IDs must be unique")
    for case in suite["cases"]:
        for variant in (0, 1):
            screen, expected, _ = presentation(case, variant, args.seed)
            assert expected in {
                a.id for a in Policy((PACKAGE,), allow_taps=True, allow_back=True).actions(screen)
            }
    if args.check:
        print(f"Validated {len(ids)} cases, two presentations each. No API calls.")
        return 0
    if args.output.exists():
        parser.error("Output already exists; choose a new report path")
    previous = json.loads(args.resume_from.read_text()) if args.resume_from else None
    suite_hash = hashlib.sha256(raw).hexdigest()
    instructions_hash = hashlib.sha256(INSTRUCTIONS.encode()).hexdigest()
    if previous and (
        previous["suite_sha256"] != suite_hash
        or previous["instructions_sha256"] != instructions_hash
        or previous["seed"] != args.seed
        or previous["status"] == "running"
    ):
        parser.error("Resume requires the same suite, instructions and seed, and a stopped report")
    carried_cost = (
        Decimal(previous["estimated_usd_including_reservation"]) if previous else Decimal(0)
    )
    remaining = Decimal(args.budget) - carried_cost
    if remaining <= 0:
        parser.error("No estimated budget remains after the previous run")
    config = RunConfig(max_steps=1000, budget_usd=remaining)
    budget = Budget(config)
    trials = [(case, variant) for case in suite["cases"] for variant in (0, 1)]
    random.Random(args.seed).shuffle(trials)
    planned = len(trials)
    completed = (
        {(r["case_id"], r["variant"]) for r in previous["records"] if "correct" in r}
        if previous
        else set()
    )
    trials = [(case, variant) for case, variant in trials if (case["id"], variant) not in completed]
    report: dict[str, Any] = {
        "suite": suite["name"],
        "suite_sha256": suite_hash,
        "instructions_sha256": instructions_hash,
        "kind": "synthetic_single_decision_evaluation",
        "seed": args.seed,
        "started_at": datetime.now(UTC).isoformat(),
        "interval_seconds": args.interval,
        "input_price_per_million": str(config.input_price_per_million),
        "records": previous["records"] if previous else [],
        "status": "running",
    }
    if previous:
        report["resumed_from"] = args.resume_from.name
        report["carried_estimated_usd_including_reservation"] = str(carried_cost)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        report["summary"] = summarize(report["records"], planned)
        report["estimated_usd_including_reservation"] = str(carried_cost + budget.estimated_usd)
        report["reserved_tokens"] = budget.reserved + (
            previous["reserved_tokens"] if previous else 0
        )
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    key = os.environ.get("AI_GATEWAY_API_KEY") or getpass.getpass("Vercel API key (hidden): ")
    next_request = time.monotonic()
    try:
        with JevProvider(key) as provider:
            del key
            for index, (case, variant) in enumerate(trials, len(completed) + 1):
                time.sleep(max(0, next_request - time.monotonic()))
                next_request = time.monotonic() + args.interval
                try:
                    record = evaluate_one(provider, case, variant, args.seed, config, budget)
                except JevDroidError as error:
                    report["records"].append(
                        {
                            "case_id": case["id"],
                            "variant": variant,
                            "error_type": type(error).__name__,
                            "http_status": error.status
                            if isinstance(error, ProviderError)
                            else None,
                        }
                    )
                    report["status"] = "stopped_on_error"
                    print(f"Stopped: {type(error).__name__}; no automatic retry.", flush=True)
                    break
                report["records"].append(record)
                save()
                print(
                    f"[{index:02}/{planned}] {case['id']} v{variant}: "
                    f"{'PASS' if record['correct'] else 'FAIL'} "
                    f"expected={record['expected']} actual={record['actual']} "
                    f"API={record['api_seconds']:.3f}s total=${budget.estimated_usd:.6f}",
                    flush=True,
                )
            else:
                report["status"] = "complete"
    except KeyboardInterrupt:
        report["status"] = "cancelled"
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        save()
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
