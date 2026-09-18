"""The scrolling profile cannot tap, like, comment, or follow."""

import argparse
import getpass
import os

from jevdroid import Agent, Policy, RunConfig
from jevdroid.android import AndroidDevice
from jevdroid.providers import JevProvider

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("package", help="Android package of the installed app to scroll")
package = parser.parse_args().package
key = os.environ.get("AI_GATEWAY_API_KEY") or getpass.getpass("Vercel key: ")
with JevProvider(key) as jev:
    result = Agent(
        AndroidDevice(),
        jev,
        policy=Policy((package,)),
        config=RunConfig(target_scrolls=5, max_steps=12),
    ).run(f"Open {package} and scroll through five videos. Stop if a dialog blocks the feed.")
    print(result.as_dict())
