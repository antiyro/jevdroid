# JevDroid

**A Python framework for controlling Android over ADB with Jev.**

[![CI](https://github.com/antiyro/jevdroid/actions/workflows/ci.yml/badge.svg)](https://github.com/antiyro/jevdroid/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Give Jev a goal. It reads Android's accessibility tree, chooses an action, and
JevDroid executes it: open apps, tap, swipe, and navigate back.

Use `run()` for the full loop or compose `observe()`, `decide()`, and `act()`.
Includes standard ADB and persistent UIAutomator2 backends, TypeSafe and Vercel
providers, action permissions, and per-run budgets.

## Speed and cost

| Metric | Measured result |
| --- | --- |
| Jev decision latency | **390 ms median** across four scroll decisions |
| Estimated cost per decision | **$0.000058 average** for those decisions |
| Android action execution | **88 ms** to launch Settings · **170 ms** to tap |

Small POC samples on a Galaxy A05 over USB. Decision latency covers inference;
action timing covers device input only. Costs use $0.042 per million input tokens.
[Measurements and methodology →](docs/performance.md)

## Quick start

Requires Python 3.11+, [ADB](https://developer.android.com/tools/releases/platform-tools),
and an unlocked Android device with USB debugging authorized.

```bash
git clone https://github.com/antiyro/jevdroid.git
cd jevdroid
python -m venv .venv
source .venv/bin/activate
pip install -e ".[android]"

jevdroid run "Open Display settings without changing a setting" \
  --package com.android.settings --allow-taps --budget 0.05
```

The CLI prompts for a hidden Vercel API key. Use `--provider typesafe` for direct
TypeSafe access, or `jevdroid demo` to try an offline simulation without a key.
On Windows, activate with `.venv\Scripts\activate`.

## Python API

```python
import getpass
from jevdroid import JevDroid, Policy

with JevDroid.connect(
    api_key=getpass.getpass("Vercel API key: "),
    policy=Policy(("com.android.settings",), allow_taps=True),
) as droid:
    result = droid.run("Open Display settings without changing a setting.")
    print(result.status, result.estimated_usd)
```

Early alpha. Goals and visible UI text are sent to the selected provider.

[SDK](docs/sdk.md) · [CLI](docs/cli.md) · [Architecture](docs/architecture.md) ·
[Examples](examples) · [Contributing](CONTRIBUTING.md) · [MIT License](LICENSE)
