"""Persistent UIAutomator2 transport with bounded reads and validated input."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from typing import Any

from jevdroid.android.xml import parse_xml
from jevdroid.errors import DeviceError, EmptyScreen
from jevdroid.models import Action, ActionKind, Screen, validate_package


def adb(*args: str) -> str:
    try:
        return subprocess.run(
            ["adb", *args], capture_output=True, text=True, check=True, timeout=20
        ).stdout
    except FileNotFoundError:
        raise DeviceError("Install Android platform-tools and put adb on PATH.") from None
    except (subprocess.SubprocessError, OSError):
        raise DeviceError(
            "ADB failed. Check the USB connection and device authorization."
        ) from None


def devices() -> dict[str, str]:
    rows = (line.split() for line in adb("devices").splitlines()[1:])
    return {row[0]: row[1] for row in rows if len(row) >= 2}


def select_device(serial: str | None = None) -> str:
    connected = devices()
    if serial:
        if connected.get(serial) != "device":
            raise DeviceError("Selected device is absent, offline, or unauthorized.")
        return serial
    ready = [name for name, status in connected.items() if status == "device"]
    if len(ready) != 1:
        raise DeviceError("Connect one authorized Android device, or specify --serial.")
    return ready[0]


class AndroidDevice:
    """One connection per run. Installs/starts UIAutomator2's service when needed."""

    def __init__(self, serial: str | None = None) -> None:
        self.serial = select_device(serial)
        try:
            import uiautomator2 as u2
        except ImportError:
            raise DeviceError('Install Android support: pip install -e ".[android]"') from None
        try:
            self._device: Any = u2.connect(self.serial)
            self._device.jsonrpc.setConfigurator(
                {"waitForIdleTimeout": 0, "waitForSelectorTimeout": 0}
            )
            self._device.settings["operation_delay"] = (0, 0)
        except Exception:
            raise DeviceError("Cannot connect to the UIAutomator2 service.") from None

    @staticmethod
    def available() -> bool:
        return shutil.which("adb") is not None

    def snapshot(self, *, stable: bool = False) -> Screen:
        deadline = time.monotonic() + 2
        previous: Screen | None = None
        while time.monotonic() < deadline:
            try:
                xml = self._device.jsonrpc.dumpWindowHierarchy(False, 50, True)
            except Exception:
                raise DeviceError("Cannot read the active Android window.") from None
            try:
                screen = parse_xml(xml or "<hierarchy/>")
            except EmptyScreen:
                previous = None
                time.sleep(0.04)
                continue
            if not stable or screen == previous:
                return screen
            previous = screen
            time.sleep(0.04)
        raise DeviceError("Android window remained empty or unstable for two seconds.")

    def execute(self, action: Action, screen: Screen) -> None:
        try:
            self._execute(action, screen)
        except DeviceError:
            raise
        except Exception:
            raise DeviceError("Android action failed; it may have partially executed.") from None

    def _execute(self, action: Action, screen: Screen) -> None:
        if action.kind == ActionKind.TAP:
            if action.element is None or action.element not in screen.elements:
                raise DeviceError("Tap target does not belong to the supplied screen.")
            x1, y1, x2, y2 = action.element.bounds
            self._device.click((x1 + x2) // 2, (y1 + y2) // 2)
        elif action.kind in {ActionKind.SCROLL_DOWN, ActionKind.SCROLL_UP}:
            info = self._device.info
            width, height = info["displayWidth"], info["displayHeight"]
            start, end = int(height * 0.72), int(height * 0.30)
            if action.kind == ActionKind.SCROLL_UP:
                start, end = end, start
            self._device.swipe(width // 2, start, width // 2, end, duration=0.2)
        elif action.kind == ActionKind.LAUNCH:
            if not action.package:
                raise DeviceError("Launch requires an Android package.")
            validate_package(action.package)
            resolved = adb(
                "-s",
                self.serial,
                "shell",
                "cmd",
                "package",
                "resolve-activity",
                "--brief",
                action.package,
            )
            component = next(
                (
                    line.strip()
                    for line in reversed(resolved.splitlines())
                    if re.fullmatch(r"[\w.]+/[\w.$]+", line.strip())
                ),
                None,
            )
            if component is None or component.split("/")[0] != action.package:
                raise DeviceError("No launcher activity found for the allowed package.")
            response = self._device.shell(["am", "start", "-n", component])
            if response.exit_code or "Error" in response.output:
                raise DeviceError("Android could not launch the application.")
            time.sleep(0.5)
        elif action.kind == ActionKind.BACK:
            self._device.press("back")
            time.sleep(0.15)
        elif action.kind == ActionKind.WAIT:
            time.sleep(0.25)
        else:
            raise DeviceError("This action cannot be executed on Android.")
