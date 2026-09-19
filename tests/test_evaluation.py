import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from benchmarks import run as decision_runner
from benchmarks.episodes import SimulatedAndroid
from benchmarks.run import evaluate_one, presentation, summarize
from jevdroid import Action, ActionKind, Decision, Policy, RunConfig
from jevdroid.budget import Budget
from jevdroid.engine import INSTRUCTIONS
from jevdroid.errors import DeviceError

CASE = {
    "id": "private-grading-id",
    "category": "grading-only",
    "goal": "Open the blue item",
    "text": ["Choose a color"],
    "labels": ["Red", "Blue", "Green"],
    "expected": "TAP_1",
    "history": [],
}


def test_reordered_presentation_preserves_ground_truth():
    screen, expected, order = presentation(CASE, 1, 42)
    assert order != [0, 1, 2]
    assert screen.elements[int(expected.removeprefix("TAP_"))].label == "Blue"


def test_grading_metadata_is_not_sent_to_provider():
    provider = Mock()
    provider.decide.return_value = Decision("TAP_1", 100, "fixture")
    config = RunConfig()
    record = evaluate_one(provider, CASE, 0, 42, config, Budget(config))
    state = provider.decide.call_args.args[0]
    assert "expected" not in state and "category" not in state and "id" not in state
    assert "private-grading-id" not in str(state)
    assert record["correct"] is True


def test_partial_results_do_not_claim_full_coverage():
    summary = summarize(
        [
            {
                "case_id": "a",
                "category": "logic",
                "correct": True,
                "api_seconds": 0.5,
                "estimated_usd": "0.001",
            },
            {
                "case_id": "a",
                "category": "logic",
                "correct": False,
                "api_seconds": 0.7,
                "estimated_usd": "0.001",
            },
            {"case_id": "b", "error_type": "ProviderError"},
        ],
        10,
    )
    assert summary["accuracy"] == 0.5 and summary["coverage"] == 0.2
    assert summary["errors"] == 1 and summary["both_presentations_correct"] == 0


def episode_fixture(name):
    suite = Path(__file__).parents[1] / "benchmarks" / "episodes.json"
    return next(e for e in json.loads(suite.read_text())["episodes"] if e["id"] == name)


def tap(device, index):
    screen = device.snapshot()
    action = next(
        a
        for a in Policy((screen.package,), allow_taps=True).actions(screen)
        if a.id == f"TAP_{index}"
    )
    device.execute(action, screen)


def test_simulator_recovers_from_wrong_branch_and_reaches_goal():
    scenario = episode_fixture("invoice-verification")
    device = SimulatedAndroid(scenario)
    tap(device, 1)  # Photos is the wrong branch.
    device.execute(Action("BACK", ActionKind.BACK, "Back"), device.snapshot())
    assert device.node == "files"
    tap(device, 0)
    tap(device, 1)
    assert device.node == scenario["success"]
    assert "Total due: $165" in device.snapshot().text


def test_simulator_rejects_stale_tap_without_transition():
    device = SimulatedAndroid(episode_fixture("invoice-verification"))
    stale = device.snapshot()
    tap(device, 0)
    with pytest.raises(DeviceError, match="Stale"):
        device.execute(Action("TAP_0", ActionKind.TAP, "Tap", stale.elements[0]), stale)
    assert device.node == "downloads"


def test_all_simulated_goals_are_reachable_without_forbidden_transitions():
    suite = Path(__file__).parents[1] / "benchmarks" / "episodes.json"
    for episode in json.loads(suite.read_text())["episodes"]:
        visited = set()
        pending = [episode["start"], episode["launch"]]
        while pending:
            node = pending.pop()
            if node in visited or node in episode["forbidden"]:
                continue
            visited.add(node)
            pending.extend(episode["nodes"][node].get("on_tap", {}).values())
        assert episode["success"] in visited


def test_resume_preserves_wrong_answers_and_only_retries_unanswered_trial(tmp_path, monkeypatch):
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps({"name": "resume-test", "cases": [CASE]}))
    config = RunConfig()
    provider = Mock()
    provider.decide.return_value = Decision("TAP_0", 100, "fixture")
    wrong = evaluate_one(provider, CASE, 0, 42, config, Budget(config))
    assert wrong["correct"] is False
    error = {"case_id": CASE["id"], "variant": 1, "error_type": "ProviderError"}
    previous = tmp_path / "previous.json"
    previous.write_text(
        json.dumps(
            {
                "suite_sha256": hashlib.sha256(suite.read_bytes()).hexdigest(),
                "instructions_sha256": hashlib.sha256(INSTRUCTIONS.encode()).hexdigest(),
                "seed": 42,
                "status": "stopped_on_error",
                "estimated_usd_including_reservation": wrong["estimated_usd"],
                "reserved_tokens": 0,
                "records": [wrong, error],
            }
        )
    )
    output = tmp_path / "resumed.json"
    gateway = MagicMock()
    expected = presentation(CASE, 1, 42)[1]
    gateway.__enter__.return_value.decide.return_value = Decision(expected, 100, "fixture")
    monkeypatch.setattr(decision_runner, "JevProvider", lambda key: gateway)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "local-test-placeholder")
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchmarks.run",
            "--suite",
            str(suite),
            "--output",
            str(output),
            "--resume-from",
            str(previous),
            "--interval",
            "0",
        ],
    )
    assert decision_runner.main() == 0
    report = json.loads(output.read_text())
    gateway.__enter__.return_value.decide.assert_called_once()
    assert report["records"][:2] == [wrong, error]
    assert report["records"][2]["variant"] == 1
    assert report["summary"]["accuracy"] == 0.5
    assert report["summary"]["coverage"] == 1
