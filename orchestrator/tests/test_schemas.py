"""Schema tests: Requirements and Blueprint integrity rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from orchestrator.schemas import Blueprint, BlueprintDraft, HealthcareDomain, Requirements

BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprints"


def base_requirements(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "demo_name": "Test Demo",
        "summary": "A demo used by the unit tests.",
        "target_audience": "Testers",
        "business_goals": ["Verify things"],
        "domains": ["member"],
    }
    data.update(overrides)
    return data


def base_draft(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "instance_slug": "test-demo",
        "summary": "A blueprint used by the unit tests.",
        "resources": [
            {"id": "rg", "type": "resource_group", "name": "rg", "purpose": "container"},
            {"id": "db", "type": "postgresql_flexible", "name": "db", "purpose": "data",
             "sku": "B_Standard_B1ms", "depends_on": ["rg"]},
        ],
        "data_plan": [{"domain": "member", "target_resource_id": "db", "record_count": 1000}],
    }
    data.update(overrides)
    return data


class TestRequirements:
    def test_defaults_applied(self) -> None:
        req = Requirements.model_validate(base_requirements())
        assert req.data_scale.member_count == 1000
        assert req.azure_region == "centralus"
        assert req.synthetic_data_only is True

    def test_claims_pulls_in_member_and_provider(self) -> None:
        req = Requirements.model_validate(base_requirements(domains=["claims"]))
        assert set(req.domains) == {
            HealthcareDomain.CLAIMS, HealthcareDomain.MEMBER, HealthcareDomain.PROVIDER
        }
        assert any("supporting data domain" in a for a in req.assumptions)

    def test_duplicate_domains_removed(self) -> None:
        req = Requirements.model_validate(base_requirements(domains=["member", "member"]))
        assert req.domains == [HealthcareDomain.MEMBER]

    def test_real_phi_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Requirements.model_validate(base_requirements(synthetic_data_only=False))

    def test_unknown_domain_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Requirements.model_validate(base_requirements(domains=["pharmacy"]))

    def test_member_count_bounds(self) -> None:
        with pytest.raises(ValidationError):
            Requirements.model_validate(base_requirements(data_scale={"member_count": 5}))

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Requirements.model_validate(base_requirements(surprise="x"))


class TestBlueprintDraft:
    def test_valid_draft(self) -> None:
        assert BlueprintDraft.model_validate(base_draft()).instance_slug == "test-demo"

    def test_duplicate_resource_ids(self) -> None:
        draft = base_draft()
        draft["resources"].append(dict(draft["resources"][0]))
        with pytest.raises(ValidationError, match="duplicate resource ids"):
            BlueprintDraft.model_validate(draft)

    def test_unknown_dependency(self) -> None:
        draft = base_draft()
        draft["resources"][1]["depends_on"] = ["nope"]
        with pytest.raises(ValidationError, match="unknown ids"):
            BlueprintDraft.model_validate(draft)

    def test_self_dependency(self) -> None:
        draft = base_draft()
        draft["resources"][1]["depends_on"] = ["db"]
        with pytest.raises(ValidationError, match="depends on itself"):
            BlueprintDraft.model_validate(draft)

    def test_dependency_cycle(self) -> None:
        draft = base_draft()
        draft["resources"][0]["depends_on"] = ["db"]  # rg -> db -> rg
        with pytest.raises(ValidationError, match="cycle"):
            BlueprintDraft.model_validate(draft)

    def test_data_plan_unknown_target(self) -> None:
        draft = base_draft(
            data_plan=[{"domain": "member", "target_resource_id": "ghost", "record_count": 10}]
        )
        with pytest.raises(ValidationError, match="unknown resource"):
            BlueprintDraft.model_validate(draft)

    def test_data_plan_duplicate_domain(self) -> None:
        entry = {"domain": "member", "target_resource_id": "db", "record_count": 10}
        with pytest.raises(ValidationError, match="more than once"):
            BlueprintDraft.model_validate(base_draft(data_plan=[entry, dict(entry)]))

    def test_bad_slug(self) -> None:
        with pytest.raises(ValidationError):
            BlueprintDraft.model_validate(base_draft(instance_slug="Bad Slug!"))


class TestBlueprint:
    def test_parent_version_must_be_lower(self) -> None:
        with pytest.raises(ValidationError, match="parent_version"):
            Blueprint.model_validate(
                {**base_draft(), "requirements": base_requirements(), "version": 2, "parent_version": 2}
            )

    def test_identity_generated(self) -> None:
        bp = Blueprint.model_validate({**base_draft(), "requirements": base_requirements()})
        assert bp.version == 1 and bp.blueprint_id and bp.created_at.tzinfo is not None

    @pytest.mark.parametrize("path", sorted(BLUEPRINT_DIR.glob("example-*.json")), ids=lambda p: p.name)
    def test_example_blueprints_are_valid(self, path: Path) -> None:
        Blueprint.model_validate(json.loads(path.read_text(encoding="utf-8")))
