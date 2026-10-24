"""M1 output: structured Requirements extracted from a business user's intent."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HealthcareDomain(str, Enum):
    """The five synthetic-data domains (one data agent each)."""

    MEMBER = "member"
    PROVIDER = "provider"
    CLAIMS = "claims"
    AUTHORIZATION = "authorization"
    CARE_MANAGEMENT = "care_management"


# Referential integrity: these domains reference rows in others, so the others
# must be generated too (a claim needs a member and a provider, etc.).
DOMAIN_DEPENDENCIES: dict[HealthcareDomain, frozenset[HealthcareDomain]] = {
    HealthcareDomain.CLAIMS: frozenset({HealthcareDomain.MEMBER, HealthcareDomain.PROVIDER}),
    HealthcareDomain.AUTHORIZATION: frozenset(
        {HealthcareDomain.MEMBER, HealthcareDomain.PROVIDER}
    ),
    HealthcareDomain.CARE_MANAGEMENT: frozenset({HealthcareDomain.MEMBER}),
}


class DataScale(BaseModel):
    """How much synthetic data to generate."""

    model_config = ConfigDict(extra="forbid")

    member_count: int = Field(1000, ge=100, le=100_000, description="Synthetic members.")
    history_months: int = Field(12, ge=1, le=60, description="Months of claims/auth history.")


class Experience(BaseModel):
    """Which user-facing pieces the demo needs."""

    model_config = ConfigDict(extra="forbid")

    web_ui: bool = Field(True, description="A browser UI for the demo audience.")
    api: bool = Field(True, description="A backend API serving the demo data.")
    analytics_dashboard: bool = Field(False, description="Charts / KPIs over the data.")


class Requirements(BaseModel):
    """Structured, validated requirements for one demo environment."""

    model_config = ConfigDict(extra="forbid")

    demo_name: str = Field(min_length=3, max_length=80, description="Short human-friendly name.")
    summary: str = Field(min_length=10, max_length=600, description="One-paragraph restatement.")
    target_audience: str = Field(min_length=2, max_length=200, description="Who the demo is for.")
    business_goals: list[str] = Field(min_length=1, max_length=8)
    domains: list[HealthcareDomain] = Field(min_length=1)
    data_scale: DataScale = Field(default_factory=DataScale)
    experience: Experience = Field(default_factory=Experience)
    azure_region: str = Field("centralus", min_length=3, max_length=40)
    ttl_days: int = Field(14, ge=1, le=90, description="Days before the demo auto-expires.")
    # Hard guardrail: the platform never loads real PHI/PII.
    synthetic_data_only: Literal[True] = True
    assumptions: list[str] = Field(
        default_factory=list, description="Defaults the model chose where intent was silent."
    )
    open_questions: list[str] = Field(
        default_factory=list, description="Ambiguities worth confirming with the user."
    )

    @model_validator(mode="after")
    def _dedupe_and_complete_domains(self) -> Requirements:
        """Remove duplicate domains and add any required dependency domains."""
        ordered: list[HealthcareDomain] = list(dict.fromkeys(self.domains))
        added: list[HealthcareDomain] = []
        for domain in list(ordered):
            for dep in sorted(DOMAIN_DEPENDENCIES.get(domain, ()), key=lambda d: d.value):
                if dep not in ordered:
                    ordered.append(dep)
                    added.append(dep)
        self.domains = ordered
        if added:
            names = ", ".join(d.value for d in added)
            self.assumptions.append(
                f"Added required supporting data domain(s) for referential integrity: {names}."
            )
        return self
