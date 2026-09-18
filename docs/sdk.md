# Jev-to-Android SDK

JevDroid is the bridge between Jev's typed decisions and an Android device
accessible through ADB. An application can use the complete agent loop or compose
individual decisions into a workflow it controls.

## Connect and run

```python
import getpass
from decimal import Decimal

from jevdroid import JevDroid, Policy, RunConfig

with JevDroid.connect(
    api_key=getpass.getpass("Vercel API key: "),
    backend="uiautomator",
    policy=Policy(
        packages=("com.android.settings",),
        allow_taps=True,
        allow_back=True,
        allow_scroll_up=True,
    ),
    config=RunConfig(max_steps=15, budget_usd=Decimal("0.05")),
) as droid:
    result = droid.run("Open Display settings without changing any setting.")
    print(result.as_dict())
```

`connect()` owns and closes its HTTP provider. It does not uninstall the Android
service or stop the shared ADB server when the session closes. Pass `serial` to
choose among multiple devices. `backend="adb"` uses standard platform-tools;
`backend="uiautomator"` uses the faster persistent service over ADB.

To use default capabilities, supply `packages=("org.example.app",)` instead of a
policy. Default capabilities include app launch, scrolling, waiting, and terminal
decisions. Taps and back navigation are opt-in. Supplying both `packages` and
`policy` requires the package tuples to match.

## Compose individual decisions

```python
from jevdroid import ActionKind

# Inside the connected context above:
plan = droid.decide("Open Display settings without changing any setting.")
if plan.action.kind not in {ActionKind.DONE, ActionKind.STOP}:
    executed = droid.act(plan)
    if not executed:
        print("Screen changed; observe and decide again.")
```

| Method | Inference | Device input | Result |
| --- | --- | --- | --- |
| `observe()` | None | None | Current `Screen` |
| `decide(goal)` | One Jev request | None | `PlannedAction` with action, screen, usage, API latency |
| `act(plan)` | None | At most one action | Whether device input completed |
| `run(goal)` | Bounded loop | Bounded actions | `RunResult` |

`decide()` observes a fresh screen itself. The model selects from actions generated
by the current policy; it does not generate shell commands or coordinates. A new
decision invalidates the previous pending plan. Execution consumes the plan even
if stale validation or a device error prevents it, avoiding accidental replays.

Manual calls share `droid.budget` and `config.max_steps` for the session lifetime.
The manual API does not automatically loop, pause, detect repeated decisions, or
count gestures; your application controls those concerns. Use `run()` for those
features, including `target_scrolls`. Each `run()` has a fresh independent budget
and invalidates any pending manual plan. It does not reset the manual budget.

`observe()` needs no API call. `decide()` and `act()` raise typed operational errors;
`run()` converts expected operational failures into a result status. Instances
are synchronous and must not share control of a device concurrently.

## Supply your own components

```python
from jevdroid import JevDroid, Policy
from jevdroid.android import AdbDevice
from jevdroid.providers import JevProvider

# The caller owns injected components and their lifecycle.
with JevProvider(api_key="provided-by-your-secret-manager") as jev:
    droid = JevDroid(
        device=AdbDevice(),
        provider=jev,
        policy=Policy(("org.example.app",)),
    )
```

Implement the `Device` or `Provider` protocols for another transport or decision
service. The lower-level `Agent` remains available for applications that only
need the automatic loop. `choose_action()` in `jevdroid.planning` is the shared
decision primitive used by both the SDK and the loop.

## Supported Android actions

The initial action set includes observed-element taps, vertical swipes, app
launch by package, Android back, wait, done, and stop. The two backends implement
the same set. Text entry, long press, arbitrary shell commands, and installation
are not model actions in this version.

Jev selects among supplied choices. Expanding the framework with a new primitive
requires a typed action definition, a policy rule, both transport implementations,
fresh-state validation where appropriate, and tests. App-specific workflows do
not belong in the core.
