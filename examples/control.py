"""Compose Jev decisions and Android actions inside your own application loop."""

import argparse
import getpass
import os

from jevdroid import ActionKind, JevDroid, Policy, RunConfig

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("goal")
parser.add_argument("--package", action="append", required=True)
parser.add_argument("--backend", choices=["uiautomator", "adb"], default="uiautomator")
args = parser.parse_args()
key = os.environ.get("AI_GATEWAY_API_KEY") or getpass.getpass("Vercel API key: ")

with JevDroid.connect(
    api_key=key,
    backend=args.backend,
    policy=Policy(tuple(args.package), allow_taps=True, allow_back=True, allow_scroll_up=True),
    config=RunConfig(max_steps=5),
) as droid:
    for _ in range(5):
        plan = droid.decide(args.goal)
        print(plan.action.kind, plan.action.description)
        if plan.action.kind in {ActionKind.DONE, ActionKind.STOP}:
            break
        if not droid.act(plan):
            print("Screen changed; action skipped.")
