"""Capability catalog loader and blueprint rule checker.

The catalog is the single source of truth for what the factory can build. It is
(1) rendered into the M2 prompt so Claude plans within it, and (2) used to
deterministically validate Claude's output, since prompts alone aren't a guarantee.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.config import DEFAULT_CATALOG_PATH
from orchestrator.schemas.blueprint import BlueprintDraft
from orchestrator.schemas.requirements import Requirements

RESOURCE_GROUP_TYPE = "resource_group"


class Capability(BaseModel):
    """One buildable Azure capability."""

    model_config = ConfigDict(extra="forbid")

    type: str
    terraform_type: str
    description: str
    use_when: str
    skus: list[str] = Field(default_factory=list)
    config: dict[str, str] = Field(default_factory=dict)
    max_per_blueprint: int | None = None


class CatalogFile(BaseModel):
    """On-disk shape of capabilities.json."""

    model_config = ConfigDict(extra="forbid")

    catalog_version: str
    description: str
    capabilities: list[Capability]
    domain_stores: dict[str, list[str]]


class CapabilityCatalog:
    """In-memory catalog with prompt rendering and blueprint validation."""

    def __init__(self, data: CatalogFile) -> None:
        self._data = data
        self._by_type: dict[str, Capability] = {c.type: c for c in data.capabilities}
        if len(self._by_type) != len(data.capabilities):
            raise ValueError("catalog contains duplicate capability types")
        for domain, stores in data.domain_stores.items():
            unknown = [s for s in stores if s not in self._by_type]
            if unknown:
                raise ValueError(f"domain_stores['{domain}'] references unknown types: {unknown}")

    @classmethod
    def load(cls, path: Path | None = None) -> CapabilityCatalog:
        """Load and validate the catalog JSON (defaults to capability-catalog/)."""
        catalog_path = path or DEFAULT_CATALOG_PATH
        raw: Any = json.loads(catalog_path.read_text(encoding="utf-8"))
        return cls(CatalogFile.model_validate(raw))

    @property
    def version(self) -> str:
        return self._data.catalog_version

    @property
    def types(self) -> list[str]:
        return list(self._by_type)

    def get(self, type_: str) -> Capability | None:
        return self._by_type.get(type_)

    def render_for_prompt(self) -> str:
        """Compact JSON of the catalog for inclusion in the M2 system prompt."""
        payload = {
            "capabilities": [
                c.model_dump(exclude={"terraform_type"}) for c in self._data.capabilities
            ],
            "domain_stores": self._data.domain_stores,
        }
        return json.dumps(payload, indent=2)

    def validate_blueprint(self, draft: BlueprintDraft, requirements: Requirements) -> list[str]:
        """Return human-readable rule violations (empty list means valid)."""
        errors: list[str] = []

        # 1. Every resource must be a known capability with an allowed SKU.
        for res in draft.resources:
            cap = self._by_type.get(res.type)
            if cap is None:
                errors.append(
                    f"resource '{res.id}': unknown type '{res.type}'. "
                    f"Allowed types: {self.types}"
                )
                continue
            if cap.skus and res.sku not in cap.skus:
                errors.append(
                    f"resource '{res.id}' ({res.type}): sku '{res.sku}' not allowed. "
                    f"Allowed: {cap.skus}"
                )

        # 2. Per-type instance limits.
        counts = Counter(r.type for r in draft.resources)
        for cap in self._data.capabilities:
            if cap.max_per_blueprint is not None and counts[cap.type] > cap.max_per_blueprint:
                errors.append(
                    f"type '{cap.type}': {counts[cap.type]} used, "
                    f"max {cap.max_per_blueprint} per blueprint"
                )

        # 3. Exactly one resource group, and everything else sits under it.
        rgs = [r for r in draft.resources if r.type == RESOURCE_GROUP_TYPE]
        if len(rgs) != 1:
            errors.append(f"exactly one '{RESOURCE_GROUP_TYPE}' is required, found {len(rgs)}")
        else:
            rg_id = rgs[0].id
            for res in draft.resources:
                if res.type != RESOURCE_GROUP_TYPE and rg_id not in res.depends_on:
                    errors.append(f"resource '{res.id}' must list '{rg_id}' in depends_on")

        # 4. Data plan must cover exactly the requested domains.
        planned = {e.domain for e in draft.data_plan}
        wanted = set(requirements.domains)
        if planned != wanted:
            errors.append(
                "data_plan domains must match requirements. "
                f"Missing: {sorted(d.value for d in wanted - planned)}; "
                f"unexpected: {sorted(d.value for d in planned - wanted)}"
            )

        # 5. Each domain must land in an allowed store type, and counts must agree.
        by_id = {r.id: r for r in draft.resources}
        for entry in draft.data_plan:
            target = by_id.get(entry.target_resource_id)
            allowed = self._data.domain_stores.get(entry.domain.value, [])
            if target is not None and target.type not in allowed:
                errors.append(
                    f"data_plan '{entry.domain.value}' targets '{target.id}' "
                    f"({target.type}); allowed store types: {allowed}"
                )
            if (
                entry.domain.value == "member"
                and entry.record_count != requirements.data_scale.member_count
            ):
                errors.append(
                    f"member record_count must equal requirements.data_scale.member_count "
                    f"({requirements.data_scale.member_count}), got {entry.record_count}"
                )
        return errors
