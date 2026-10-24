"""Demo record: the API-facing state of one factory run across M1..M4."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.schemas.blueprint import Blueprint
from orchestrator.schemas.requirements import Requirements


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DemoStatus(str, Enum):
    """Lifecycle. Only `deploying`/`destroying` are 'busy' states (work in progress)."""

    PLANNED = "planned"  # M1 + M2 done: requirements + blueprint exist
    GENERATED = "generated"  # M3 done: Terraform instance dir exists and validates
    DEPLOYING = "deploying"  # M4 apply running
    DEPLOYED = "deployed"  # M4 done: resources live
    DESTROYING = "destroying"
    DESTROYED = "destroyed"
    FAILED = "failed"  # last operation failed; see `error` and `failed_stage`

    @property
    def is_busy(self) -> bool:
        return self in (DemoStatus.DEPLOYING, DemoStatus.DESTROYING)


class PlanSummary(BaseModel):
    """What `terraform plan` intends to do, in numbers and addresses."""

    add: int = 0
    change: int = 0
    destroy: int = 0
    resources: list[str] = Field(default_factory=list, description="Addresses with pending changes.")
    created_at: datetime = Field(default_factory=_now)

    @property
    def has_deletions(self) -> bool:
        return self.destroy > 0


class DemoEvent(BaseModel):
    """One line in the demo's activity trail."""

    at: datetime = Field(default_factory=_now)
    stage: str
    message: str


class Demo(BaseModel):
    """Everything the API knows about one demo."""

    demo_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: DemoStatus = DemoStatus.PLANNED
    intent: str
    requirements: Requirements | None = None
    blueprint: Blueprint | None = None
    instance_dir: str | None = Field(None, description="Instance folder name under terraform/instances.")
    plan: PlanSummary | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    failed_stage: str | None = None
    error: str | None = None
    events: list[DemoEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def log(self, stage: str, message: str) -> None:
        self.events.append(DemoEvent(stage=stage, message=message))
