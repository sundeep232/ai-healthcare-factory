"""M2 output: a versioned Blueprint describing the Azure resources and data to build.

Two layers:
  * BlueprintDraft: what Claude produces (no ids/timestamps it could hallucinate).
  * Blueprint: the draft plus system-assigned identity, version, and the
    Requirements it was derived from. This is what gets stored and handed to M3.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orchestrator.schemas.requirements import HealthcareDomain, Requirements

RESOURCE_ID_PATTERN = r"^[a-z][a-z0-9_]{1,40}$"
INSTANCE_SLUG_PATTERN = r"^[a-z][a-z0-9-]{2,23}$"


class ResourceSpec(BaseModel):
    """One Azure resource, expressed as a catalog capability (not raw HCL)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=RESOURCE_ID_PATTERN, description="Unique id within the blueprint.")
    type: str = Field(min_length=2, description="Capability type from the catalog.")
    name: str = Field(min_length=2, max_length=60, description="Logical name for the resource.")
    purpose: str = Field(min_length=3, max_length=200, description="Why this resource is needed.")
    sku: str | None = Field(None, description="SKU/tier from the catalog's allowed list.")
    config: dict[str, Any] = Field(default_factory=dict, description="Capability options.")
    depends_on: list[str] = Field(default_factory=list, description="Ids of prerequisite resources.")


class DataPlanEntry(BaseModel):
    """Where one domain's synthetic data lands, and how much of it."""

    model_config = ConfigDict(extra="forbid")

    domain: HealthcareDomain
    target_resource_id: str = Field(pattern=RESOURCE_ID_PATTERN)
    record_count: int = Field(ge=1, le=10_000_000)


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    """Return True if the dependency graph contains a cycle (iterative DFS)."""
    white, grey, black = 0, 1, 2
    color: dict[str, int] = {node: white for node in graph}
    for start in graph:
        if color[start] != white:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        color[start] = grey
        while stack:
            node, idx = stack.pop()
            deps = graph[node]
            if idx < len(deps):
                stack.append((node, idx + 1))
                nxt = deps[idx]
                if color[nxt] == grey:
                    return True
                if color[nxt] == white:
                    color[nxt] = grey
                    stack.append((nxt, 0))
            else:
                color[node] = black
    return False


class BlueprintDraft(BaseModel):
    """The plan itself. Structural integrity is enforced here; catalog rules elsewhere."""

    model_config = ConfigDict(extra="forbid")

    instance_slug: str = Field(
        pattern=INSTANCE_SLUG_PATTERN,
        description="Short lowercase slug used in Azure resource names.",
    )
    summary: str = Field(min_length=10, max_length=600)
    resources: list[ResourceSpec] = Field(min_length=1, max_length=40)
    data_plan: list[DataPlanEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_integrity(self) -> BlueprintDraft:
        ids = [r.id for r in self.resources]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate resource ids: {dupes}")

        known = set(ids)
        graph: dict[str, list[str]] = {}
        for res in self.resources:
            if res.id in res.depends_on:
                raise ValueError(f"resource '{res.id}' depends on itself")
            missing = [d for d in res.depends_on if d not in known]
            if missing:
                raise ValueError(f"resource '{res.id}' depends on unknown ids: {missing}")
            graph[res.id] = list(res.depends_on)
        if _has_cycle(graph):
            raise ValueError("resource dependencies contain a cycle")

        seen_domains: set[HealthcareDomain] = set()
        for entry in self.data_plan:
            if entry.target_resource_id not in known:
                raise ValueError(
                    f"data_plan for '{entry.domain.value}' targets unknown resource "
                    f"'{entry.target_resource_id}'"
                )
            if entry.domain in seen_domains:
                raise ValueError(f"data_plan lists domain '{entry.domain.value}' more than once")
            seen_domains.add(entry.domain)
        return self


class Blueprint(BlueprintDraft):
    """A stored, versioned blueprint (draft + identity + source requirements)."""

    blueprint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: int = Field(1, ge=1)
    parent_version: int | None = Field(None, ge=1, description="Set when derived from a prior version (M7).")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    requirements: Requirements

    @model_validator(mode="after")
    def _check_version_lineage(self) -> Blueprint:
        if self.parent_version is not None and self.parent_version >= self.version:
            raise ValueError("parent_version must be lower than version")
        return self
