"""Modules the tenant stack can create. Keep this list aligned with tenants/stack."""

import json

CATALOG = ("sql", "portal", "openai", "speech", "communication")
DEFAULT_RESOURCES = ["sql", "portal"]


def resources_from_definition(definition) -> list[str]:
    if isinstance(definition, str):
        definition = json.loads(definition)
    if not isinstance(definition, dict) or "resources" not in definition:
        return list(DEFAULT_RESOURCES)
    selected = definition.get("resources")
    if not isinstance(selected, list):
        raise ValueError("Template resources must be a list")
    unknown = [name for name in selected if name not in CATALOG]
    if unknown or len(selected) != len(set(selected)):
        raise ValueError("Template resources are not in the module catalog")
    return [name for name in CATALOG if name in selected]


def synthetic_members_from_definition(definition) -> int:
    if isinstance(definition, str):
        definition = json.loads(definition)
    raw = definition.get("syntheticMembers", 250) if isinstance(definition, dict) else 250
    try:
        count = int(raw)
    except (TypeError, ValueError):
        raise ValueError("syntheticMembers must be a number") from None
    if count < 10 or count > 1000:
        raise ValueError("syntheticMembers must be from 10 to 1000")
    return count
