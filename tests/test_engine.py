from decimal import Decimal
from unittest.mock import Mock

import pytest

from jevdroid import Agent, Decision, Element, Policy, RunConfig, RunStatus, Screen
from jevdroid.errors import DeviceError, ProviderError

APP = "org.example.app"
SCREEN = Screen(APP, ("Feed",), (Element(0, "Open", (0, 0, 100, 100)),))


def setup_run(actions, *, config=None, policy=None, snapshots=None, provider_error=None):
    device = Mock()
    device.snapshot.return_value = SCREEN
    if snapshots:
        device.snapshot.side_effect = snapshots
    provider = Mock()
    provider.decide.side_effect = provider_error or [Decision(a, 100, "test") for a in actions]
    events = []
    agent = Agent(
        device,
        provider,
        policy=policy or Policy((APP,), allow_taps=True),
        config=config or RunConfig(scroll_pause=0),
        on_event=events.append,
    )
    return agent, device, provider, events


def test_navigation_and_distinct_model_completion():
    agent, device, provider, events = setup_run(["TAP_0", "DONE"])
    result = agent.run("Open the page")
    assert result.status == RunStatus.MODEL_DONE
    assert result.actions == 1 and result.calls == 2
    assert result.input_tokens == 200 and result.reserved_tokens == 0
    assert device.execute.call_count == 1
    assert events[-1]["status"] == "model_done"


def test_counted_scroll_stops_exactly_without_extra_call():
    agent, device, provider, _ = setup_run(
        ["SCROLL_DOWN"] * 5,
        policy=Policy((APP,)),
        config=RunConfig(target_scrolls=5, max_steps=5, scroll_pause=0),
    )
    result = agent.run("Scroll five times")
    assert result.status == RunStatus.COMPLETED
    assert result.scrolls == result.actions == provider.decide.call_count == 5
    assert device.execute.call_count == 5


def test_unknown_action_never_executes_but_usage_is_settled():
    agent, device, _, _ = setup_run(["SEND_MESSAGE"])
    result = agent.run("Read")
    assert result.status == RunStatus.ERROR
    assert result.reserved_tokens == 0 and result.input_tokens == 100
    device.execute.assert_not_called()


@pytest.mark.parametrize("fresh", [Screen("another.app", ("Other",)), Screen(APP, ("Changed",))])
def test_changed_screen_rejects_stale_tap(fresh):
    agent, device, _, events = setup_run(
        ["TAP_0"], config=RunConfig(max_steps=1), snapshots=[SCREEN, fresh]
    )
    result = agent.run("Navigate")
    assert result.status == RunStatus.STEP_LIMIT
    assert any(e["event"] == "skipped" for e in events)
    device.execute.assert_not_called()


def test_scroll_revalidates_foreground_package():
    agent, device, _, _ = setup_run(
        ["SCROLL_DOWN"],
        config=RunConfig(max_steps=1),
        snapshots=[SCREEN, Screen("other.app", ("Other",))],
    )
    agent.run("Scroll")
    device.execute.assert_not_called()


def test_video_caption_changes_do_not_block_scroll():
    agent, device, _, _ = setup_run(
        ["SCROLL_DOWN"],
        config=RunConfig(max_steps=1, target_scrolls=1),
        policy=Policy((APP,)),
        snapshots=[SCREEN, Screen(APP, ("Different caption",))],
    )
    assert agent.run("Scroll").status == RunStatus.COMPLETED
    assert device.execute.call_count == 1


def test_budget_prevents_network_call():
    agent, device, provider, _ = setup_run([], config=RunConfig(budget_usd=Decimal("0.001")))
    assert agent.run("Open").status == RunStatus.BUDGET_LIMIT
    provider.decide.assert_not_called()
    device.execute.assert_not_called()


def test_provider_error_retains_reservation_without_retry():
    agent, device, provider, _ = setup_run(
        [], provider_error=ProviderError("Rate limit", status=429)
    )
    result = agent.run("Open")
    assert result.status == RunStatus.ERROR
    assert result.reserved_tokens == 65536
    assert provider.decide.call_count == 1
    device.execute.assert_not_called()


def test_invalid_usage_stops_before_action():
    agent, device, provider, _ = setup_run([])
    provider.decide.side_effect = [Decision("TAP_0", True, "test")]
    result = agent.run("Open")
    assert result.status == RunStatus.ERROR and result.reserved_tokens == 65536
    device.execute.assert_not_called()


def test_budget_reservation_violation_stops():
    agent, device, provider, _ = setup_run([])
    provider.decide.side_effect = [Decision("TAP_0", 70000, "test")]
    result = agent.run("Open")
    assert result.status == RunStatus.BUDGET_LIMIT and result.input_tokens == 70000
    device.execute.assert_not_called()


def test_loop_guard():
    agent, device, _, _ = setup_run(["WAIT"] * 3)
    assert agent.run("Open").status == RunStatus.REPEATED
    assert device.execute.call_count == 2


def test_large_payload_rejected_before_network():
    agent, device, provider, _ = setup_run([], config=RunConfig(max_payload_bytes=20))
    assert agent.run("Open").status == RunStatus.ERROR
    provider.decide.assert_not_called()


def test_device_error_does_not_claim_execution():
    agent, device, _, _ = setup_run(["TAP_0"])
    device.execute.side_effect = DeviceError("Device disconnected")
    result = agent.run("Open")
    assert result.status == RunStatus.ERROR and result.actions == 0


def test_cancellation_is_reported():
    agent, _, _, _ = setup_run([], provider_error=KeyboardInterrupt())
    assert agent.run("Open").status == RunStatus.CANCELLED


def test_trace_contains_no_goal_or_screen_text():
    agent, _, _, events = setup_run(["DONE"])
    agent.run("A private goal")
    assert "A private goal" not in str(events)
    assert "Feed" not in str(events)
    assert "Open" not in str(events)


def test_stop_is_not_success():
    agent, device, _, _ = setup_run(["STOP"])
    assert agent.run("Open").status == RunStatus.STOPPED
    device.execute.assert_not_called()
