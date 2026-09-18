import json
from unittest.mock import Mock, patch

import pytest

from jevdroid import Action, ActionKind, Element, Screen
from jevdroid.android.device import AndroidDevice, select_device
from jevdroid.cli import main
from jevdroid.errors import DeviceError
from jevdroid.trace import JsonlTrace

XML = '<hierarchy><node package="org.example.app" text="Feed"/></hierarchy>'


def phone():
    device = object.__new__(AndroidDevice)
    device.serial = "fixture-serial"
    device._device = Mock()
    return device


def test_ambiguous_device_requires_serial():
    with patch(
        "jevdroid.android.device.devices",
        return_value={"one": "device", "two": "device", "three": "unauthorized"},
    ):
        with pytest.raises(DeviceError):
            select_device()
        assert select_device("two") == "two"
        with pytest.raises(DeviceError):
            select_device("three")


def test_active_window_only_and_stable_snapshot():
    device = phone()
    device._device.jsonrpc.dumpWindowHierarchy.side_effect = [XML, XML]
    assert device.snapshot(stable=True).package == "org.example.app"
    assert device._device.jsonrpc.dumpWindowHierarchy.call_count == 2
    device._device.jsonrpc.dumpWindowHierarchy.assert_called_with(False, 50, True)


def test_transient_empty_screen():
    device = phone()
    device._device.jsonrpc.dumpWindowHierarchy.side_effect = ["<hierarchy/>", XML]
    assert device.snapshot().text == ("Feed",)


def test_tap_rejects_target_not_in_screen():
    device = phone()
    with pytest.raises(DeviceError):
        device.execute(
            Action("TAP_0", ActionKind.TAP, "Tap", element=Element(0, "X", (0, 0, 10, 10))),
            Screen("org.example.app"),
        )
    device._device.click.assert_not_called()


def test_launch_resolves_activity_and_checks_package():
    device = phone()
    device._device.shell.return_value = Mock(exit_code=0, output="Starting")
    with (
        patch("jevdroid.android.device.adb", return_value="foreign.app/.Activity"),
        pytest.raises(DeviceError),
    ):
        device.execute(
            Action("LAUNCH_0", ActionKind.LAUNCH, "Open", package="org.example.app"),
            Screen("home.app"),
        )
    device._device.shell.assert_not_called()


def test_trace_exclusive_creation_and_metadata(tmp_path):
    path = tmp_path / "run.jsonl"
    with JsonlTrace(path) as trace:
        trace({"event": "executed", "step": 1})
    assert json.loads(path.read_text())["step"] == 1
    with pytest.raises(FileExistsError):
        JsonlTrace(path)


def test_offline_demo_needs_no_device_or_credentials(capsys):
    with patch("jevdroid.cli.AndroidDevice", side_effect=AssertionError("No real device")):
        assert main(["demo"]) == 0
    assert "SIMULATION" in capsys.readouterr().out


def test_invalid_budget_rejected_before_device():
    with patch("jevdroid.cli.AndroidDevice") as device:
        assert main(["scroll", "--package", "org.example.app", "--budget", "NaN"]) == 1
        device.assert_not_called()
