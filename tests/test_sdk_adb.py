from unittest.mock import Mock, patch

import pytest

from jevdroid import Action, ActionKind, Decision, Element, JevDroid, Policy, RunConfig, Screen
from jevdroid.android import AdbDevice
from jevdroid.cli import parser
from jevdroid.errors import DeviceError, InvalidDecision, JevDroidError

APP = "org.example.app"
SCREEN = Screen(APP, ("Page",), (Element(0, "Next", (0, 0, 100, 100)),))
XML = '<hierarchy><node package="org.example.app" text="Page"/></hierarchy>'


def session(action="TAP_0", config=None):
    device, provider = Mock(), Mock()
    device.snapshot.return_value = SCREEN
    provider.decide.return_value = Decision(action, 100, "fixture")
    droid = JevDroid(device, provider, policy=Policy((APP,), allow_taps=True), config=config)
    return droid, device, provider


def test_decision_is_separate_from_execution_and_cannot_replay():
    droid, device, _ = session()
    plan = droid.decide("Open next page")
    device.execute.assert_not_called()
    assert droid.act(plan) is True
    with pytest.raises(InvalidDecision):
        droid.act(plan)
    assert device.execute.call_count == 1


def test_old_pending_decision_cannot_execute():
    droid, device, _ = session()
    first = droid.decide("Open next page")
    second = droid.decide("Open next page")
    with pytest.raises(InvalidDecision):
        droid.act(first)
    assert droid.act(second)
    assert droid.budget.calls == 2 and droid.budget.tokens == 200


def test_sdk_rejects_stale_taps():
    droid, device, _ = session()
    plan = droid.decide("Open")
    device.snapshot.return_value = Screen(APP, ("Changed",))
    assert droid.act(plan) is False
    device.execute.assert_not_called()


def test_observation_makes_no_inference_call():
    droid, _, provider = session()
    assert droid.observe() == SCREEN
    provider.decide.assert_not_called()


def test_session_step_limit_is_shared_across_decisions():
    droid, _, provider = session(config=RunConfig(max_steps=1))
    droid.decide("Open")
    with pytest.raises(JevDroidError, match="decision limit"):
        droid.decide("Open")
    assert provider.decide.call_count == 1


def test_closed_session_never_operates_and_does_not_close_injected_provider():
    droid, device, provider = session()
    droid.close()
    with pytest.raises(JevDroidError, match="closed"):
        droid.observe()
    provider.close.assert_not_called()
    device.snapshot.assert_not_called()


def test_terminal_decision_is_not_device_input():
    droid, device, _ = session("DONE")
    assert droid.act(droid.decide("Open")) is False
    device.execute.assert_not_called()


def test_policy_change_invalidates_pending_plan():
    droid, device, _ = session()
    plan = droid.decide("Open")
    droid.policy = Policy((APP,))
    with pytest.raises(InvalidDecision, match="no longer permitted"):
        droid.act(plan)
    device.execute.assert_not_called()


def test_connect_adb_owns_and_closes_provider():
    with patch("jevdroid.sdk.AdbDevice") as device, patch("jevdroid.sdk.JevProvider") as provider:
        with JevDroid.connect(api_key="fixture-key", packages=(APP,), backend="adb") as droid:
            assert droid.device is device.return_value
        provider.return_value.close.assert_called_once()


def test_connect_rejects_policy_mismatch_before_device_access():
    with patch("jevdroid.sdk.AdbDevice") as device:
        with pytest.raises(ValueError, match="match"):
            JevDroid.connect(
                api_key="fixture-key", packages=(APP,), backend="adb", policy=Policy(("other.app",))
            )
        device.assert_not_called()


def adb_phone():
    with patch("jevdroid.android.adb.select_device", return_value="fixture-serial"):
        return AdbDevice()


def test_adb_snapshot_removes_remote_dump():
    phone = adb_phone()
    with patch.object(phone, "_adb", side_effect=["UI hierarchy dumped", XML, ""]) as command:
        assert phone.snapshot().package == APP
        assert command.call_args.args[:3] == ("shell", "rm", "-f")
        assert command.call_args.args[3].startswith("/sdcard/jevdroid-")


def test_adb_dump_failure_still_cleans_up():
    phone = adb_phone()
    with patch.object(phone, "_adb", side_effect=[DeviceError("Disconnected"), ""]) as command:
        with pytest.raises(DeviceError):
            phone.snapshot()
        assert command.call_args.args[:3] == ("shell", "rm", "-f")


def test_adb_tap_coordinates_come_from_observed_element():
    phone = adb_phone()
    with patch.object(phone, "_adb") as command:
        phone.execute(Action("TAP_0", ActionKind.TAP, "Tap", element=SCREEN.elements[0]), SCREEN)
        command.assert_called_once_with("shell", "input", "tap", "50", "50")


def test_adb_swipe_respects_display_override_and_rotation():
    phone = adb_phone()
    with patch.object(
        phone, "_adb", side_effect=["Physical size: 1080x1920\nOverride size: 720x1600", ""]
    ) as command:
        phone.execute(
            Action("SCROLL_DOWN", ActionKind.SCROLL_DOWN, "Scroll"), Screen(APP, rotation=1)
        )
        command.assert_called_with("shell", "input", "swipe", "800", "518", "800", "216", "200")


def test_adb_launch_checks_resolved_activity_package():
    phone = adb_phone()
    with patch.object(phone, "_adb", return_value="other.app/.Main") as command:
        with pytest.raises(DeviceError):
            phone.execute(Action("LAUNCH", ActionKind.LAUNCH, "Open", package=APP), SCREEN)
        assert command.call_count == 1


def test_adb_stability_rejects_changing_screen():
    phone = adb_phone()
    with patch.object(phone, "_read", side_effect=[Screen(APP, (str(i),)) for i in range(3)]):
        with pytest.raises(DeviceError, match="stabilize"):
            phone.snapshot(stable=True)


def test_cli_accepts_multiple_packages_and_adb_backend():
    args = parser().parse_args(
        [
            "run",
            "Open settings",
            "--package",
            APP,
            "--package",
            "com.android.settings",
            "--backend",
            "adb",
        ]
    )
    assert args.package == [APP, "com.android.settings"]
    assert args.backend == "adb"


def test_run_invalidates_manual_plan():
    droid, _, provider = session()
    plan = droid.decide("Open")
    provider.decide.return_value = Decision("DONE", 100, "fixture")
    assert droid.run("Open").status == "model_done"
    with pytest.raises(InvalidDecision):
        droid.act(plan)


def test_counted_scrolling_requires_automatic_loop():
    droid, device, provider = session(config=RunConfig(target_scrolls=5))
    with pytest.raises(ValueError, match="Use run"):
        droid.decide("Scroll")
    device.snapshot.assert_not_called()
    provider.decide.assert_not_called()
