"""Run from an installed checkout with an authorized Android device connected."""

import getpass
import os

from jevdroid import Agent, Policy, RunConfig
from jevdroid.android import AndroidDevice
from jevdroid.providers import JevProvider

key = os.environ.get("AI_GATEWAY_API_KEY") or getpass.getpass("Vercel key: ")
with JevProvider(key) as jev:
    result = Agent(
        AndroidDevice(),
        jev,
        policy=Policy(("com.android.settings",), allow_taps=True),
        config=RunConfig(max_steps=12),
    ).run("Open Display settings without changing any setting.")
    print(result.as_dict())
