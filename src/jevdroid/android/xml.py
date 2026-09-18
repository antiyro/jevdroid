"""Bounded, text-only parsing of Android accessibility hierarchies."""

import re
from xml.etree.ElementTree import Element as XMLNode
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from jevdroid.errors import DeviceError, EmptyScreen
from jevdroid.models import Element, Screen


def parse_xml(xml: str) -> Screen:
    if len(xml.encode()) > 2_000_000:
        raise DeviceError("Android hierarchy exceeds the 2 MB parsing limit.")
    try:
        root = fromstring(xml)
    except (ParseError, DefusedXmlException) as exc:
        raise DeviceError("Invalid Android hierarchy XML.") from exc
    nodes: list[XMLNode] = []

    def visit(node: XMLNode, depth: int = 0) -> None:
        if depth > 100:
            raise DeviceError("Android hierarchy is too deeply nested.")
        if node.get("password") == "true" or node.get("visible-to-user") == "false":
            return
        nodes.append(node)
        for child in node:
            visit(child, depth + 1)

    visit(root)
    allowed = {id(node) for node in nodes}
    text: list[str] = []
    elements: list[Element] = []
    seen: set[tuple[int, int, int, int]] = set()
    package = next((n.get("package") for n in nodes if n.get("package")), "unknown")
    for node in nodes:
        label = (node.get("text") or node.get("content-desc") or "").strip()
        if label and len(text) < 80:
            text.append(label[:160])
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if (
            not match
            or node.get("clickable") != "true"
            or node.get("enabled") == "false"
            or len(elements) >= 60
        ):
            continue
        x1, y1, x2, y2 = map(int, match.groups())
        box = (x1, y1, x2, y2)
        if x2 <= x1 or y2 <= y1 or box in seen:
            continue
        if not label:
            label = " / ".join(
                filter(
                    None,
                    (
                        (n.get("text") or n.get("content-desc") or "").strip()
                        for n in node.iter()
                        if id(n) in allowed
                    ),
                )
            )
        resource_id = node.get("resource-id", "")[:160]
        label = label or resource_id or node.get("class", "element")
        elements.append(
            Element(len(elements), label[:160], box, resource_id, node.get("checkable") == "true")
        )
        seen.add(box)
    if not text and not elements:
        raise EmptyScreen("No readable elements; unlock the device or wait for loading.")
    try:
        rotation = int(root.get("rotation", "0"))
    except ValueError as exc:
        raise DeviceError("Invalid screen rotation.") from exc
    return Screen(package or "unknown", tuple(text), tuple(elements), rotation)
