"""Capability catalog loading and blueprint rule checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.schemas import Blueprint, BlueprintDraft, Requirements
from orchestrator.tools.catalog import CapabilityCatalog

BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprints"


@pytest.fixture(scope="module")
def catalog() -> CapabilityCatalog:
    return CapabilityCatalog.load()


def load_example(name: str) -> dict[str, Any]:
    return json.loads((BLUEPRINT_DIR / name).read_text(encoding="utf-8"))


def validate(catalog: CapabilityCatalog, data: dict[str, Any]) -> list[str]:
    reqs = Requirements.model_validate(data["requirements"])
    draft = BlueprintDraft.model_validate({k: v for k, v in data.items() if k in BlueprintDraft.model_fields})
    return catalog.validate_blueprint(draft, reqs)


def test_catalog_loads(catalog: CapabilityCatalog) -> None:
    assert "resource_group" in catalog.types
    assert "postgresql_flexible" in catalog.types
    assert "PerGB2018" in catalog.render_for_prompt()


@pytest.mark.parametrize("name", ["example-claims-dashboard.json", "example-prior-auth.json"])
def test_examples_pass_catalog_rules(catalog: CapabilityCatalog, name: str) -> None:
    assert validate(catalog, load_example(name)) == []


def test_unknown_resource_type(catalog: CapabilityCatalog) -> None:
    data = load_example("example-claims-dashboard.json")
    data["resources"][2]["type"] = "oracle_exadata"
    assert any("unknown type" in e for e in validate(catalog, data))


def test_disallowed_sku(catalog: CapabilityCatalog) -> None:
    data = load_example("example-claims-dashboard.json")
    data["resources"][2]["sku"] = "MO_Standard_E64s_v3"
    assert any("sku" in e and "not allowed" in e for e in validate(catalog, data))


def test_missing_resource_group_dependency(catalog: CapabilityCatalog) -> None:
    data = load_example("example-claims-dashboard.json")
    data["resources"][3]["depends_on"] = []  # key vault no longer under rg
    assert any("must list 'rg'" in e for e in validate(catalog, data))


def test_two_resource_groups(catalog: CapabilityCatalog) -> None:
    data = load_example("example-claims-dashboard.json")
    data["resources"].append(
        {"id": "rg2", "type": "resource_group", "name": "rg2", "purpose": "extra", "depends_on": []}
    )
    errors = validate(catalog, data)
    assert any("exactly one" in e for e in errors)


def test_data_plan_missing_domain(catalog: CapabilityCatalog) -> None:
    data = load_example("example-claims-dashboard.json")
    data["data_plan"] = [e for e in data["data_plan"] if e["domain"] != "claims"]
    assert any("Missing: ['claims']" in e for e in validate(catalog, data))


def test_wrong_store_for_domain(catalog: CapabilityCatalog) -> None:
    data = load_example("example-prior-auth.json")
    for entry in data["data_plan"]:
        if entry["domain"] == "member":
            entry["target_resource_id"] = "docs"  # cosmos is not allowed for member
    assert any("allowed store types" in e for e in validate(catalog, data))


def test_member_count_must_match_requirements(catalog: CapabilityCatalog) -> None:
    data = load_example("example-claims-dashboard.json")
    for entry in data["data_plan"]:
        if entry["domain"] == "member":
            entry["record_count"] = 1
    assert any("member record_count" in e for e in validate(catalog, data))


def test_blueprint_model_accepts_valid_example() -> None:
    Blueprint.model_validate(load_example("example-prior-auth.json"))
