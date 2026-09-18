"""Standard ADB backend: no persistent service or Android Python extra required."""

import re
import time
import uuid

from jevdroid.android.device import adb, select_device
from jevdroid.android.xml import parse_xml
from jevdroid.errors import DeviceError
from jevdroid.models import Action, ActionKind, Screen, validate_package


class AdbDevice:
    """Android observation and input through platform-tools only.

    This fallback launches uiautomator for every XML read. Prefer AndroidDevice
    for low-latency loops. Snapshot stability is bounded by three dumps.
    """

    def __init__(self, serial: str | None = None) -> None:
        self.serial = select_device(serial)

    def _adb(self, *args: str) -> str:
        return adb("-s", self.serial, *args)

    def _read(self) -> Screen:
        path = f"/sdcard/jevdroid-{uuid.uuid4().hex}.xml"
        try:
            result = self._adb("shell", "uiautomator", "dump", path)
            if "ERROR" in result.upper():
                raise DeviceError("ADB could not dump the active accessibility hierarchy.")
            return parse_xml(self._adb("exec-out", "cat", path))
        finally:
            try:
                self._adb("shell", "rm", "-f", path)
            except DeviceError:
                pass

    def snapshot(self, *, stable: bool = False) -> Screen:
        previous = self._read()
        if not stable:
            return previous
        for _ in range(2):
            current = self._read()
            if current == previous:
                return current
            previous = current
        raise DeviceError("Android window did not stabilize across three ADB observations.")

    def execute(self, action: Action, screen: Screen) -> None:
        if action.kind == ActionKind.TAP:
            if action.element is None or action.element not in screen.elements:
                raise DeviceError("Tap target does not belong to the supplied screen.")
            x1, y1, x2, y2 = action.element.bounds
            self._adb("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))
        elif action.kind in {ActionKind.SCROLL_DOWN, ActionKind.SCROLL_UP}:
            sizes = re.findall(r"(\d+)x(\d+)", self._adb("shell", "wm", "size"))
            if not sizes:
                raise DeviceError("Cannot determine Android display dimensions.")
            width, height = map(int, sizes[-1])
            if screen.rotation in {1, 3}:
                width, height = height, width
            start, end = int(height * 0.72), int(height * 0.30)
            if action.kind == ActionKind.SCROLL_UP:
                start, end = end, start
            self._adb(
                "shell",
                "input",
                "swipe",
                str(width // 2),
                str(start),
                str(width // 2),
                str(end),
                "200",
            )
        elif action.kind == ActionKind.LAUNCH:
            if not action.package:
                raise DeviceError("Launch requires an Android package.")
            validate_package(action.package)
            resolved = self._adb(
                "shell", "cmd", "package", "resolve-activity", "--brief", action.package
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
            response = self._adb("shell", "am", "start", "-n", component)
            if "Error" in response:
                raise DeviceError("Android could not launch the application.")
        elif action.kind == ActionKind.BACK:
            self._adb("shell", "input", "keyevent", "4")
        elif action.kind == ActionKind.WAIT:
            time.sleep(0.25)
        else:
            raise DeviceError("This action cannot be executed on Android.")
