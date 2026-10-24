"""M3b data agents: deterministic synthetic data for the five healthcare domains.

Generation is deterministic Python (seeded), not LLM output: it is free, reproducible,
guarantees referential integrity, and can never leak real PHI. Claude's job in this
project is deciding *what* to build; this package fills it.
"""

from __future__ import annotations

from datetime import date

from orchestrator.agents.data_agents.authorization import AuthorizationAgent
from orchestrator.agents.data_agents.base import DataAgent, Dataset, GenerationContext
from orchestrator.agents.data_agents.care_management import CareManagementAgent
from orchestrator.agents.data_agents.claims import ClaimsAgent
from orchestrator.agents.data_agents.member import MemberAgent
from orchestrator.agents.data_agents.provider import ProviderAgent
from orchestrator.agents.data_agents.schema import TABLES, Row, TableSpec, tables_for
from orchestrator.schemas.blueprint import Blueprint
from orchestrator.schemas.requirements import HealthcareDomain

# Dependency order: members and providers first, then the domains that reference them.
AGENTS: tuple[DataAgent, ...] = (
    MemberAgent(),
    ProviderAgent(),
    ClaimsAgent(),
    AuthorizationAgent(),
    CareManagementAgent(),
)


def build_context(blueprint: Blueprint, *, seed: int, today: date | None = None) -> GenerationContext:
    """Derive generation parameters from the blueprint's data plan and requirements."""
    return GenerationContext(
        seed=seed,
        today=today or date.today(),
        history_months=blueprint.requirements.data_scale.history_months,
        counts={e.domain: e.record_count for e in blueprint.data_plan},
    )


def generate_dataset(ctx: GenerationContext) -> Dataset:
    """Run every agent whose domain is in ``ctx.counts``, in dependency order."""
    dataset = Dataset()
    for agent in AGENTS:
        if agent.domain in ctx.counts:
            dataset.tables.update(agent.generate(ctx, dataset))
    return dataset


__all__ = [
    "AGENTS",
    "TABLES",
    "Dataset",
    "GenerationContext",
    "HealthcareDomain",
    "Row",
    "TableSpec",
    "build_context",
    "generate_dataset",
    "tables_for",
]
