"""Translations: strings.json, en.json and ko.json describe the same keys."""

import json
import re
from pathlib import Path

import pytest

COMPONENT = Path(__file__).parents[3] / "custom_components" / "chirp"


def _load(name: str) -> dict:
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


def _keys(node, prefix=""):
    """Return every key path of a nested dict, with its placeholders."""
    if not isinstance(node, dict):
        return {(prefix, tuple(sorted(re.findall(r"{(\w+)}", node))))}
    result = set()
    for key, value in node.items():
        result |= _keys(value, f"{prefix}.{key}" if prefix else key)
    return result


def test_strings_match_english():
    assert _load("strings.json") == _load("translations/en.json")


@pytest.mark.parametrize("language", ["en", "ko"])
def test_translation_keys_and_placeholders_match(language):
    assert _keys(_load(f"translations/{language}.json")) == _keys(_load("strings.json"))


def test_every_translation_key_used_by_icons_exists():
    entity = _load("strings.json")["entity"]
    icons = _load("icons.json")["entity"]
    for platform, keys in icons.items():
        for key in keys:
            assert key in entity[platform], f"{platform}.{key}"


async def test_every_entity_translation_key_exists(hass, setup_entry):
    from homeassistant.helpers import entity_registry as er

    entity = _load("strings.json")["entity"]
    entries = er.async_entries_for_config_entry(
        er.async_get(hass), setup_entry.entry_id
    )
    assert len(entries) > 80
    for reg in entries:
        assert reg.translation_key in entity[reg.domain], reg.unique_id
