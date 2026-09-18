import pytest

from jevdroid import ActionKind, Element, Policy, RunConfig, Screen
from jevdroid.android.xml import parse_xml
from jevdroid.errors import DeviceError, EmptyScreen


def test_xml_parent_label_and_sensitive_subtrees():
    screen = parse_xml("""<hierarchy rotation="1">
    <node package="org.example.app" clickable="true" bounds="[0,0][400,100]">
      <node text="Display"/>
      <node password="true" text="secret"><node text="nested secret"/></node>
      <node visible-to-user="false"><node text="hidden"/></node>
    </node>
    <node text="Disabled" enabled="false" clickable="true" bounds="[0,100][400,200]"/>
    </hierarchy>""")
    assert screen.rotation == 1 and screen.package == "org.example.app"
    assert len(screen.elements) == 1 and screen.elements[0].label == "Display"
    assert "secret" not in str(screen) and "hidden" not in str(screen)


@pytest.mark.parametrize("xml", ["bad", '<!DOCTYPE a [<!ENTITY x "boom">]><a>&x;</a>'])
def test_invalid_and_entity_xml_rejected(xml):
    with pytest.raises(DeviceError):
        parse_xml(xml)


def test_empty_xml():
    with pytest.raises(EmptyScreen):
        parse_xml("<hierarchy/>")


def test_oversized_xml():
    with pytest.raises(DeviceError):
        parse_xml("x" * 2_000_001)


def test_scroll_profile_never_offers_taps_or_back():
    screen = Screen("org.example.app", elements=(Element(0, "Like", (0, 0, 10, 10)),))
    policy = Policy((screen.package,), allow_taps=True, allow_back=True)
    kinds = {a.kind for a in policy.actions(screen, scroll_only=True)}
    assert kinds == {ActionKind.WAIT, ActionKind.STOP, ActionKind.SCROLL_DOWN}


def test_foreign_application_only_offers_launch_and_terminal_choices():
    policy = Policy(("org.example.app",), allow_taps=True)
    actions = policy.actions(Screen("foreign.app"))
    assert {a.kind for a in actions} == {
        ActionKind.LAUNCH,
        ActionKind.WAIT,
        ActionKind.STOP,
        ActionKind.DONE,
    }


def test_checkable_excluded_by_default():
    screen = Screen(
        "org.example.app", elements=(Element(0, "Toggle", (0, 0, 10, 10), checkable=True),)
    )
    assert all(
        a.kind != ActionKind.TAP for a in Policy((screen.package,), allow_taps=True).actions(screen)
    )
    assert any(
        a.kind == ActionKind.TAP
        for a in Policy((screen.package,), allow_taps=True, allow_checkable=True).actions(screen)
    )


@pytest.mark.parametrize("package", ["foo;rm", "--help", "$(whoami)", "", "a/b"])
def test_package_injection_rejected(package):
    with pytest.raises(ValueError):
        Policy((package,))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"budget_usd": "NaN"},
        {"budget_usd": -1},
        {"input_price_per_million": "Infinity"},
        {"max_steps": 0},
        {"max_steps": True},
        {"target_scrolls": 0},
        {"max_steps": 2, "target_scrolls": 3},
        {"scroll_pause": float("nan")},
    ],
)
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        RunConfig(**kwargs)
